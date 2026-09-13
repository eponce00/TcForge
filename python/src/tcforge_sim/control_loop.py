"""Drive a generic first-order plant through the bench PLC's PID fixture.

The fixture is test-only and has no physical IO mapping. Payload fields are
written before requestFrame; an uncertain frame commit is never replayed.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET

from .models import FirstOrderAnalog


SYMBOL = "MAIN.controlLoopFixture."
GOOD = 2
BAD = 1


@dataclass(frozen=True)
class LoopSnapshot:
    frame: int
    cv: float
    ready: bool
    watchdog_expired: bool
    watchdog_trips: int
    owner_task: int
    cycle: int


class ControlLoopTransport:
    """One framed writer for the isolated Testing PLC instance."""

    def __init__(self, connection, *, clock=time.perf_counter, sleep=time.sleep):
        self.connection = connection
        self.clock = clock
        self.sleep = sleep
        self.frame = int(self._read("appliedFrame"))
        self.last_commit_at = None
        self.failed = False

    def _read(self, field):
        return self.connection.read_by_name(SYMBOL + field)

    def _write(self, field, value):
        self.connection.write_by_name(SYMBOL + field, value)

    def snapshot(self):
        names = [
            "appliedFrame",
            "outputCv",
            "ready",
            "watchdogExpired",
            "watchdogTrips",
            "ownerTask",
            "cycleCounter",
        ]
        values = self.connection.read_list_by_name([SYMBOL + name for name in names])

        def value(name):
            return values[SYMBOL + name]

        state = LoopSnapshot(
            frame=int(value("appliedFrame")),
            cv=float(value("outputCv")),
            ready=bool(value("ready")),
            watchdog_expired=bool(value("watchdogExpired")),
            watchdog_trips=int(value("watchdogTrips")),
            owner_task=int(value("ownerTask")),
            cycle=int(value("cycleCounter")),
        )
        if not math.isfinite(state.cv) or not 0.0 <= state.cv <= 100.0:
            raise RuntimeError("PLC returned a nonfinite or unbounded CV")
        if state.owner_task <= 0 or state.cycle <= 0:
            raise RuntimeError("Control fixture is not executing in a PLC task")
        return state

    def exchange(self, *, pv, quality, setpoint, enable, timeout=0.35):
        if self.failed:
            raise RuntimeError("Uncertain control frame; do not replay this session")
        if not math.isfinite(pv) or not math.isfinite(setpoint):
            raise ValueError("PV and setpoint must be finite")
        if quality not in (GOOD, BAD) or type(enable) is not bool:
            raise ValueError("Quality and enable must have explicit valid values")
        if not 0 < timeout < 0.5:
            raise ValueError("Frame timeout must be shorter than the PLC watchdog")

        next_frame = (self.frame + 1) & 0xFFFFFFFF
        try:
            # requestFrame is the commit marker; the PLC never consumes a
            # partial payload. A write timeout after it is an uncertain result.
            payload = {
                SYMBOL + "requestEnable": enable,
                SYMBOL + "requestPv": pv,
                SYMBOL + "requestQuality": quality,
                SYMBOL + "requestSetpoint": setpoint,
            }
            results = self.connection.write_list_by_name(payload)
            if set(results) != set(payload) or any(
                result != "no error" for result in results.values()
            ):
                raise RuntimeError("PLC rejected a control payload field")
            self._write("requestFrame", next_frame)
            self.last_commit_at = self.clock()

            # Initial ADS symbol discovery can occur during the payload writes.
            # Bound the acknowledgement phase from the actual commit, not from
            # the first metadata lookup.
            deadline = self.last_commit_at + timeout
            while self.clock() < deadline:
                applied = int(self._read("appliedFrame"))
                if applied == next_frame:
                    state = self.snapshot()
                    if state.frame != next_frame:
                        raise RuntimeError("PLC frame changed during snapshot")
                    self.frame = next_frame
                    return state
                if applied != self.frame:
                    raise RuntimeError("PLC applied an unexpected control frame")
                self.sleep(0.005)
            raise TimeoutError("PLC did not acknowledge the committed control frame")
        except Exception:
            self.failed = True
            raise


@contextmanager
def ads_connection(target, port):
    dll_handle = None
    if os.name == "nt":
        common = (
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Beckhoff/TwinCAT/Common64"
        )
        if common.is_dir():
            dll_handle = os.add_dll_directory(str(common))
    try:
        import pyads

        with pyads.Connection(target, port) as connection:
            connection.set_timeout(2000)
            yield connection
    finally:
        if dll_handle is not None:
            dll_handle.close()


def run(transport, trace_path, report_path):
    plant = FirstOrderAnalog(tau_s=0.4, initial=0.0, low=0.0, high=100.0)
    suite = ET.Element("testsuite", name="TcForge.ControlLoop", tests="5")
    last_cv = None
    last_sample = None
    observed_trips = None

    with trace_path.open("w", encoding="utf-8") as trace:

        def exchange(enable, quality=GOOD, setpoint=60.0):
            nonlocal last_cv, last_sample, observed_trips
            now = time.perf_counter()
            if last_sample is not None:
                elapsed = now - last_sample
                plant.step(last_cv, elapsed)

            sent_pv = plant.value
            state = transport.exchange(
                pv=sent_pv,
                quality=quality,
                setpoint=setpoint,
                enable=enable,
            )
            completed = time.perf_counter()
            if last_sample is not None:
                # The previous CV acts through payload transmission. Once the
                # PLC commits this frame, the new CV acts while ADS returns it.
                committed = min(max(transport.last_commit_at, now), completed)
                if committed > now:
                    plant.step(last_cv, committed - now)
                if completed > committed:
                    plant.step(state.cv, completed - committed)
            if observed_trips is not None and state.watchdog_trips != observed_trips:
                raise TimeoutError("PLC feed watchdog tripped during normal exchange")
            observed_trips = state.watchdog_trips
            last_cv = state.cv
            last_sample = completed
            trace.write(
                json.dumps(
                    dict(
                        event="frame",
                        frame=state.frame,
                        pv=sent_pv,
                        plant_pv=plant.value,
                        cv=state.cv,
                        ready=state.ready,
                        quality=quality,
                        enable=enable,
                        cycle=state.cycle,
                        watchdog_trips=state.watchdog_trips,
                        roundtrip_s=completed - now,
                    )
                )
                + "\n"
            )
            trace.flush()
            return state

        def check(name, action):
            case = ET.SubElement(suite, "testcase", name=name)
            started = time.perf_counter()
            try:
                action()
                print("PASS", name, flush=True)
            except Exception as exc:
                ET.SubElement(case, "failure", message=str(exc)).text = traceback.format_exc()
                print("FAIL", name, str(exc), flush=True)
                raise
            finally:
                case.set("time", str(time.perf_counter() - started))

        def settle(tolerance, timeout):
            deadline = time.perf_counter() + timeout
            consecutive = 0
            while time.perf_counter() < deadline:
                time.sleep(0.05)
                state = exchange(True)
                if state.ready and abs(plant.value - 60.0) <= tolerance:
                    consecutive += 1
                    if consecutive >= 5:
                        return
                else:
                    consecutive = 0
            raise AssertionError(f"Closed loop did not settle: PV={plant.value:.2f}")

        def startup_and_settle():
            state = exchange(False, setpoint=0.0)
            if state.cv != 0.0 or state.ready:
                raise AssertionError("Disabled fixture did not start at safe CV")
            settle(tolerance=3.0, timeout=12.0)

        def quality_loss():
            state = exchange(True, quality=BAD)
            if state.ready or state.cv != 0.0:
                raise AssertionError("Bad measurement did not remove CV in its frame")

        def quality_recovery():
            state = exchange(True)
            if not state.ready or not 0.0 <= state.cv <= 100.0:
                raise AssertionError("Fresh good measurement did not recover regulation")
            settle(tolerance=5.0, timeout=12.0)

        def feed_watchdog():
            nonlocal last_cv, last_sample, observed_trips
            before = last_cv
            started = time.perf_counter()
            time.sleep(0.65)
            elapsed = time.perf_counter() - started
            state = transport.snapshot()
            if (not state.watchdog_expired or state.ready or state.cv != 0.0
                    or state.watchdog_trips <= observed_trips):
                raise AssertionError("Lost simulator feed did not fail OFF")
            observed_trips = state.watchdog_trips

            # The last output can act only until the 500 ms watchdog expires.
            plant.step(before, min(elapsed, 0.5))
            if elapsed > 0.5:
                plant.step(0.0, elapsed - 0.5)
            last_cv = 0.0
            last_sample = time.perf_counter()
            trace.write(json.dumps(dict(event="watchdog", cv=state.cv,
                                        frame=state.frame,
                                        watchdog_trips=state.watchdog_trips)) + "\n")
            state = exchange(True)
            if not state.ready or state.watchdog_expired:
                raise AssertionError("Fresh frame did not recover after watchdog")

        def explicit_disable():
            state = exchange(False)
            if state.ready or state.cv != 0.0:
                raise AssertionError("Explicit disable did not return safe CV")

        try:
            check("startup_and_settle", startup_and_settle)
            check("quality_loss_off", quality_loss)
            check("quality_recovery", quality_recovery)
            check("feed_watchdog_and_recovery", feed_watchdog)
            check("explicit_disable", explicit_disable)
        finally:
            if not transport.failed:
                try:
                    transport.exchange(pv=plant.value, quality=GOOD, setpoint=0.0, enable=False)
                except Exception:
                    pass
            report_path.parent.mkdir(parents=True, exist_ok=True)
            suite.set("tests", str(len(suite.findall("testcase"))))
            suite.set("failures", str(len(suite.findall(".//failure"))))
            ET.indent(suite)
            ET.ElementTree(suite).write(report_path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Dedicated bench AMS Net ID")
    parser.add_argument("--port", type=int, default=853)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be within 1..65535")

    args.output.mkdir(parents=True, exist_ok=True)
    with ads_connection(args.target, args.port) as connection:
        run(
            ControlLoopTransport(connection),
            args.output / "control-loop.jsonl",
            args.output / "control-loop-junit.xml",
        )


if __name__ == "__main__":
    main()
