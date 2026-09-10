"""Qualify an actual system restart during motion on an explicit isolated runtime.

Requires the installed tcforge_sim package and existing simulation RPC executable.
Prewarms XAE before motion so its startup cannot consume the actuator timeout.
This restarts the selected system; it does not build, activate or change PLC code.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

from tcforge_sim.live import AssemblySession, RpcTransport
from tcforge_sim.models import TwoPositionCylinder


HELPER = r"""param([Parameter(Mandatory=$true)][string]$Settings)
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath $Settings -Raw | ConvertFrom-Json
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
$registered = $false
$vs = $null
try {
    try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw 'Another TcForge XAE operation is running' }
    [Reflection.Assembly]::LoadFrom($cfg.automation) | Out-Null
    [TcAutomation.Core.MessageFilter]::Register()
    $registered = $true
    $project = [TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($cfg.solution)
    $version = [TcAutomation.Core.TcFileUtilities]::GetTcVersion($project)
    $vs = [TcAutomation.Core.VisualStudioInstance]::new($cfg.solution, $version, $null)
    $vs.Load()
    $vs.LoadSolution()
    # No activation or build. Warm all required COM access before the motion trigger.
    $sm = $vs.GetSystemManager()
    $sm.SetTargetNetId($cfg.target)
    $plc = $null
    if ($cfg.operation -eq 'cold-reset') {
        $plc = $sm.LookupTreeItem('TIPC^Simulation^Simulation Project')
        $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><LoginCmd>true</LoginCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
        $loginDeadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            [xml]$status = $plc.ProduceXml($false)
            if ($status.TreeItem.IECProjectDef.OnlineSettings.LoggedIn -eq 'true') { break }
            if ([DateTime]::UtcNow -gt $loginDeadline) {
                [IO.File]::WriteAllText($cfg.onlineSettings, $status.OuterXml)
                throw 'PLC engineering login did not become active; reset was not issued'
            }
            Start-Sleep -Milliseconds 100
        } while ($true)
        [IO.File]::WriteAllText($cfg.onlineSettings, $status.OuterXml)
    }
    [IO.File]::WriteAllText($cfg.ready, 'ready')
    $deadline = [DateTime]::UtcNow.AddSeconds($cfg.triggerTimeout)
    while (-not (Test-Path -LiteralPath $cfg.trigger)) {
        if (Test-Path -LiteralPath $cfg.cancel) { throw 'Restart canceled before trigger' }
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Motion trigger timed out' }
        Start-Sleep -Milliseconds 10
    }
    if (Test-Path -LiteralPath $cfg.cancel) { throw 'Restart canceled at trigger' }
    [IO.File]::WriteAllText($cfg.started, [DateTime]::UtcNow.ToString('o'))
    if ($cfg.operation -eq 'cold-reset') {
        $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><ResetColdCmd>true</ResetColdCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
        $stateDeadline = [DateTime]::UtcNow.AddSeconds(15)
        do {
            [xml]$resetStatus = $plc.ProduceXml($false)
            if ($resetStatus.TreeItem.IECProjectDef.OnlineSettings.PlcAppState -eq 'Stop') { break }
            if ([DateTime]::UtcNow -gt $stateDeadline) { throw 'Cold reset did not reach STOP' }
            Start-Sleep -Milliseconds 50
        } while ($true)
        [IO.File]::WriteAllText($cfg.onlineSettings + '.stopped', $resetStatus.OuterXml)
        $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><StartCmd>true</StartCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
        $stateDeadline = [DateTime]::UtcNow.AddSeconds(15)
        do {
            [xml]$runStatus = $plc.ProduceXml($false)
            if ($runStatus.TreeItem.IECProjectDef.OnlineSettings.PlcAppState -eq 'Run') { break }
            if ([DateTime]::UtcNow -gt $stateDeadline) { throw 'Cold reset Start did not reach RUN' }
            Start-Sleep -Milliseconds 50
        } while ($true)
        [IO.File]::WriteAllText($cfg.onlineSettings + '.running', $runStatus.OuterXml)
        $result = @{ Success=$true; Operation='ResetColdCmd/StartCmd'; TargetNetId=$cfg.target; StopVerified=$true; RunVerified=$true }
    } else {
        $result = [TcAutomation.Commands.RestartCommand]::ExecuteInSession($vs, $cfg.solution, $cfg.target)
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $cfg.result -Encoding UTF8
    if (-not $result.Success) { throw $result.ErrorMessage }
} catch {
    @{ Success=$false; ErrorMessage=$_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $cfg.result -Encoding UTF8
    throw
} finally {
    try { if ($null -ne $vs) { $vs.Close() } } finally {
        if ($registered) { [TcAutomation.Core.MessageFilter]::Revoke() }
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(args, evidence, trace):
    control = args.output / ('control-' + uuid.uuid4().hex)
    control.mkdir()
    paths = {name: control / name for name in ('ready', 'trigger', 'cancel', 'started', 'result')}
    settings = dict(automation=str(args.automation), solution=str(args.solution), target=args.target,
                    triggerTimeout=60, operation=args.operation, onlineSettings=str(control / 'online-settings.xml'), **{name: str(path) for name, path in paths.items()})
    script = control / 'restart.ps1'
    script.write_text(HELPER, encoding='utf-8')
    config = control / 'settings.json'
    config.write_text(json.dumps(settings), encoding='utf-8')
    evidence['control_directory'] = str(control)
    rpc = session = process = None
    log = (args.output / 'restart-helper.log').open('w', encoding='utf-8')
    original_error = None
    try:
        helper_environment = os.environ.copy()
        common = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Beckhoff' / 'TwinCAT'
        helper_environment['PATH'] = str(common / 'Common64') + ';' + str(common / 'Common32') + ';' + helper_environment.get('PATH', '')
        process = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-File',
                                    str(script), '-Settings', str(config)], stdout=log,
                                   stderr=subprocess.STDOUT, env=helper_environment, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.perf_counter() + args.warmup_timeout
        while not paths['ready'].exists():
            require(process.poll() is None, 'XAE warmup failed; inspect restart-helper.log')
            require(time.perf_counter() < deadline, 'XAE warmup exceeded its bound')
            time.sleep(0.1)
        evidence['helper_ready'] = True
        if args.lifecycle_state:
            from lifecycle_fixture import capture
            evidence['persistent_before'] = capture(args.target, args.port, args.lifecycle_state)

        rpc = RpcTransport(args.transport, args.target, args.port)
        session = AssemblySession(rpc, trace, TwoPositionCylinder(travel_s=0.5))
        session.until(lambda s: s['state'] == 0, command=4)
        session.tick()
        require(session.tick(5)['response'] == 0, 'Initial explicit Reset rejected')
        session.tick()
        evidence['home'] = session.until(lambda s: s['state'] == 16, command=1)
        session.until(lambda s: s['advance'] == 1 and 0.15 <= session.plant.position <= 0.8,
                      command=2)
        session.plant.jammed = True
        before = session.tick()
        require(before['advance'] == 1 and not before['retract'] and not before['faulted'],
                'Restart precondition is not healthy active advance')
        require(0 < session.plant.position < 1, 'Plant is not jammed mid-travel')
        evidence['before'] = before
        evidence['position_at_restart'] = session.plant.position
        old_boot, old_session, old_frame = session.boot, session.session, session.sequence
        plant = session.plant
        paths['trigger'].write_text('restart', encoding='ascii')
        trigger_time = time.perf_counter()
        evidence['trigger_wall_time'] = time.time()
        last = before
        last_success_time = trigger_time
        # Keep the watchdog fed until actual loss. A timeout/fault before loss fails
        # qualification: an earlier healthy command alone is not in-motion evidence.
        while True:
            require(time.perf_counter() - trigger_time < args.restart_timeout,
                    'Restart did not interrupt the simulation endpoint within its bound')
            try:
                current = session.tick()
            except Exception as exc:
                evidence['endpoint_loss'] = {'type': type(exc).__name__, 'message': str(exc),
                                             'wall_time': time.time()}
                break
            last, last_success_time = current, time.perf_counter()
            require(current['advance'] == 1 and not current['retract'] and not current['faulted'],
                    'Motion ended or faulted before endpoint loss; in-motion acceptance is inconclusive')
            time.sleep(0.01)
        evidence['last_before_loss'] = last
        evidence['last_exchange_after_trigger_s'] = last_success_time - trigger_time
        evidence['last_exchange_to_detected_loss_s'] = time.perf_counter() - last_success_time
        evidence['frame_before_loss'] = session.sequence
        require(paths['started'].exists(), 'Endpoint failed before the restart API was invoked')
        rpc.close()
        rpc = None
        session = None  # Never release or replay this old session after restart.

        deadline = time.perf_counter() + args.reconnect_timeout
        failures = []
        after = None
        old_boot_motion_lost = False
        while time.perf_counter() < deadline:
            candidate = None
            try:
                candidate = RpcTransport(args.transport, args.target, args.port)
                observed = candidate.snapshot()
                if observed['boot'] != old_boot and observed['boot'] > 0 and observed['owner'] > 0:
                    rpc, after = candidate, observed
                    break
                failures.append({'time': time.time(), 'snapshot': observed})
                if observed['boot'] == old_boot and (
                        not observed['advance'] or observed['retract'] or observed['faulted']):
                    old_boot_motion_lost = True
            except Exception as exc:
                failures.append({'time': time.time(), 'error': str(exc)})
            if candidate:
                candidate.close()
            time.sleep(0.1)
        evidence['reconnect_observations'] = failures
        require(not old_boot_motion_lost,
                'Old boot was observed with motion stopped during reconnect; in-motion acceptance is inconclusive')
        require(after is not None, 'No initialized new boot identity observed before reconnect bound')
        evidence['after'] = after
        if args.lifecycle_state:
            from lifecycle_fixture import capture, validate_restored
            evidence['persistent_after'] = capture(args.target, args.port)
            evidence['persistent_validation'] = validate_restored(evidence['persistent_before'], evidence['persistent_after'], args.lifecycle_state)
        require(after['session'] == 0 and not after['advance'] and not after['retract'] and after['inhibited'],
                'Restart retained a session, coil command or uninhibited intent')
        stale_claim = rpc.call('claim', old_session, old_boot)
        stale_exchange = rpc.call('exchange', old_session, old_boot, old_frame + 1,
                                  before['cycle'], 0, 0, 1, 1, 2)
        evidence['stale_requests'] = {'claim': stale_claim, 'exchange': stale_exchange}
        require(stale_claim == 34 and stale_exchange == 34, 'Old boot requests were not rejected')
        unchanged = rpc.snapshot()
        require(unchanged['session'] == 0 and unchanged['applied'] == after['applied'] and
                not unchanged['advance'] and not unchanged['retract'], 'Stale requests mutated new runtime')

        # Preserve the simulated physical position across the PLC restart.
        plant.jammed = False
        session = AssemblySession(rpc, trace, plant)
        reconnected = session.tick()
        evidence['reconnected'] = reconnected
        require(not reconnected['advance'] and not reconnected['retract'],
                'New simulator connection resumed old motion')
        session.until(lambda s: s['state'] == 0, command=4)
        session.tick()
        require(session.tick(5)['response'] == 0, 'Post-restart explicit Reset rejected')
        session.tick()
        evidence['recovered_home'] = session.until(lambda s: s['state'] == 16, command=1)
        session.until(lambda s: s['advance'] == 1, command=2)
        session.until(lambda s: s['retract'] == 1)
        evidence['recovered_cycle'] = session.until(lambda s: s['state'] == 16)
        require(plant.position == 0.0, 'Explicit recovered cycle did not retract the plant')
        process.wait(timeout=args.restart_timeout)
        require(process.returncode == 0, 'Restart helper returned failure')
        result = json.loads(paths['result'].read_text(encoding='utf-8-sig'))
        evidence['restart_result'] = result
        require(result.get('Success') is True, 'Restart API did not report success')
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        cleanup_errors = []
        if session and rpc:
            try:
                session.close()
                time.sleep(0.03)
                evidence['released'] = rpc.snapshot()
                require(not evidence['released']['advance'] and not evidence['released']['retract'],
                        'Released fixture has energized outputs')
            except Exception as exc:
                cleanup_errors.append(str(exc))
        if rpc:
            try:
                rpc.close()
            except Exception as exc:
                cleanup_errors.append('Close transport: ' + str(exc))
        paths['cancel'].write_text('cancel', encoding='ascii')
        if process and process.poll() is None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # Only the helper process tree created by this script is terminated.
                killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                        capture_output=True, text=True, timeout=10)
                cleanup_errors.append('Helper cleanup exceeded bound; its process tree was terminated: ' +
                                      killed.stdout + killed.stderr)
        if process:
            evidence['helper_exit_code'] = process.poll()
        log.close()
        if paths['result'].exists() and 'restart_result' not in evidence:
            try:
                evidence['restart_result'] = json.loads(paths['result'].read_text(encoding='utf-8-sig'))
            except Exception as exc:
                cleanup_errors.append('Could not parse helper result: ' + str(exc))
        if args.operation == 'cold-reset' and paths['started'].exists():
            try:
                from lifecycle_fixture import connect
                directory, pyads, connection = connect(args.target, args.port)
                try:
                    if connection.read_state()[0] == pyads.ADSSTATE_STOP:
                        connection.write_control(pyads.ADSSTATE_RUN, 0, 0, pyads.PLCTYPE_BYTE)
                        evidence['cleanup_restored_run'] = True
                finally:
                    connection.close()
                    directory.close()
            except Exception as exc:
                cleanup_errors.append('Cold reset RUN cleanup: ' + str(exc))
        if args.lifecycle_state:
            try:
                from lifecycle_fixture import clear_outputs
                evidence['persistent_cleanup'] = clear_outputs(args.target, args.port)
            except Exception as exc:
                cleanup_errors.append('Lifecycle fixture cleanup: ' + str(exc))
        evidence['cleanup_errors'] = cleanup_errors
        if cleanup_errors and original_error is None:
            raise RuntimeError('; '.join(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lifecycle-state', choices=('seed', 'safe', 'reset'), help='Also qualify actual fixture persistence')
    parser.add_argument('--operation', choices=('system-restart', 'cold-reset'), default='system-restart')
    parser.add_argument('--target', required=True, help='Dedicated runtime AMS Net ID')
    parser.add_argument('--port', required=True, type=int, help='Deployed simulation PLC ADS port')
    parser.add_argument('--solution', required=True, type=Path)
    parser.add_argument('--automation', required=True, type=Path, help='Existing TcAutomation.exe')
    parser.add_argument('--transport', required=True, type=Path, help='Existing SimulationRpc.exe')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--warmup-timeout', type=float, default=180)
    parser.add_argument('--restart-timeout', type=float, default=60)
    parser.add_argument('--reconnect-timeout', type=float, default=60)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Windows PowerShell 5.1 and TwinCAT XAE are required')
    if not 1 <= args.port <= 65535:
        parser.error('ADS port must be between 1 and 65535')
    for key in ('warmup_timeout', 'restart_timeout', 'reconnect_timeout'):
        value = getattr(args, key)
        if not math.isfinite(value) or value <= 0 or value > 600:
            parser.error(key + ' must be finite, positive and at most 600 seconds')
    for key in ('solution', 'automation', 'transport'):
        value = getattr(args, key).resolve(strict=True)
        if not value.is_file():
            parser.error(key + ' must identify an existing file')
        setattr(args, key, value)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {'scope': args.operation + ' during simulated advance; persistence=' + str(args.lifecycle_state) + '; excludes power-loss durability',
                'target': args.target, 'port': args.port, 'solution': str(args.solution),
                'started_at': time.time(), 'passed': False}
    suite = ET.Element('testsuite', name='TcForge in-motion system restart', tests='1')
    case = ET.SubElement(suite, 'testcase', name=args.operation + 'DuringAdvance', classname='TcForge.Simulation')
    start = time.perf_counter()
    try:
        with (args.output / 'restart-trace.jsonl').open('w', encoding='utf-8') as trace:
            run(args, evidence, trace)
        evidence['passed'] = True
    except Exception as exc:
        evidence['failure'] = traceback.format_exc()
        ET.SubElement(case, 'failure', message=str(exc)).text = evidence['failure']
    finally:
        case.set('time', str(time.perf_counter() - start))
        suite.set('failures', '0' if evidence['passed'] else '1')
        (args.output / 'restart-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        ET.ElementTree(suite).write(args.output / 'restart-junit.xml', encoding='utf-8', xml_declaration=True)
    print('PASS' if evidence['passed'] else 'FAIL', args.operation + 'DuringAdvance', flush=True)
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
