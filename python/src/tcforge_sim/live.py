"""Wall-clock assembly simulation through the PLC-owned exchange, never raw writes."""
import json
import math
import queue
import secrets
import subprocess
import threading
import time
from pathlib import Path

from .models import TwoPositionCylinder


class RpcTransport:
    def __init__(self, executable: Path, target: str, port: int):
        self.process = subprocess.Popen([str(executable), target, str(port)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        try:
            # Initial identity/signature discovery is read-only and occurs before
            # claiming an IO session. It is not a cyclic feed deadline.
            if not self._response(timeout=30).get('ready'):
                raise RuntimeError('Simulation transport did not identify the application')
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _response(self, timeout=5):
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise TimeoutError('Uncertain RPC outcome; session must be reconciled') from None
        if line is None:
            raise RuntimeError('Simulation transport exited: ' + self.process.stderr.read())
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    def call(self, operation: str, *args):
        self.process.stdin.write(' '.join([operation, *map(str, args)]) + '\n')
        self.process.stdin.flush()
        return self._response()['value']

    def snapshot(self):
        deadline = time.perf_counter() + 1
        while time.perf_counter() < deadline:
            raw = self.call('snapshot')
            if raw == '22':
                time.sleep(0.001)
                continue
            values = list(map(int, raw.split(',')))
            names = ('result', 'boot', 'cycle', 'applied', 'advance', 'retract', 'state',
                     'faulted', 'inhibited', 'response', 'session', 'owner', 'healthy')
            if len(values) != len(names) or values[0] != 0:
                raise RuntimeError('Invalid snapshot schema')
            return dict(zip(names, values))
        raise TimeoutError('Snapshot remained busy')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class AssemblySession:
    def __init__(self, rpc: RpcTransport, trace, model=None):
        self.rpc, self.trace = rpc, trace
        self.plant = model or TwoPositionCylinder(0.2)
        self.session = secrets.randbits(63) or 1
        self.boot = rpc.snapshot()['boot']
        self.sequence = 0
        self.last_time = time.perf_counter()
        self.failed = False
        self.shutdown_confirmed = True  # Independent simulated isolation input, controlled by scenarios.
        self.quality_good = True
        result = rpc.call('claim', self.session, self.boot)
        if result != 0:
            raise RuntimeError(f'Session claim rejected: {result}')

    def record(self, event, **fields):
        self.trace.write(json.dumps({'event': event, 'wall_time': time.time(),
                                    'boot': self.boot, 'session': self.session, **fields}) + '\n')
        self.trace.flush()

    def tick(self, command=0):
        if self.failed:
            raise RuntimeError('Session failed; do not replay uncertain frames')
        try:
            before = self.rpc.snapshot()
            if before['boot'] != self.boot or before['session'] != self.session:
                raise RuntimeError('PLC session lost or runtime restarted')
            now = time.perf_counter()
            dt = now - self.last_time
            if dt > 0.2:
                raise TimeoutError('Simulation scheduling delay exceeds live budget')
            feedback = self.plant.step(bool(before['advance']), bool(before['retract']), dt)
            frame = self.sequence + 1
            self.record('exchange_attempt', dt=dt, frame=frame, command=command,
                        position=self.plant.position, jammed=self.plant.jammed,
                        inputs={'advanced': feedback.advanced, 'retracted': feedback.retracted,
                                'shutdown_confirmed': self.shutdown_confirmed,
                                'quality_good': self.quality_good}, plc=before)
            # Only BUSY is retryable: it guarantees this frame was not admitted.
            deadline = time.perf_counter() + 0.15
            while True:
                result = self.rpc.call('exchange', self.session, self.boot, frame, before['cycle'],
                                       int(feedback.advanced), int(feedback.retracted),
                                       int(self.shutdown_confirmed), int(self.quality_good), command)
                if result != 22 or time.perf_counter() >= deadline:
                    break
                time.sleep(0.001)
            if result != 1:
                raise RuntimeError(f'Input frame rejected: {result}')
            self.record('exchange_admitted', frame=frame)
            while time.perf_counter() < deadline:
                after = self.rpc.snapshot()
                if after['boot'] != self.boot or after['session'] != self.session:
                    raise RuntimeError('Session changed while applying frame')
                if after['applied'] == frame:
                    self.sequence, self.last_time = frame, now
                    self.record('exchange_applied', dt=dt, frame=frame, command=command,
                                position=self.plant.position, jammed=self.plant.jammed, plc=after)
                    return after
                time.sleep(0.002)
            raise TimeoutError('Frame was admitted but consumption is unconfirmed')
        except Exception as exc:
            self.failed = True
            try:
                self.record('session_failed', next_frame=self.sequence + 1,
                            error_type=type(exc).__name__, error=str(exc))
            except Exception:
                pass  # Preserve the original failure even when the evidence sink fails.
            raise

    def until(self, predicate, timeout=3, command=0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Scenario timeout must be finite and positive')
        state = None
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            state = self.tick(command)
            command = 0
            if predicate(state):
                return state
            time.sleep(0.01)
        raise AssertionError(f'PLC condition timed out; last snapshot: {state}')

    def close(self):
        # Release only this session. Timeout/crash also has a PLC-side watchdog.
        return self.rpc.call('release', self.session, self.boot)
