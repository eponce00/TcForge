"""Actual online-change qualification on the isolated Simulation runtime.

Requires exclusive checkout access. Back up source, prepare an edit
before motion, require OnlineChangeCnt increment with retained lifecycle state, then restore
exact source bytes and reactivate the baseline even if qualification fails.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

from lifecycle_fixture import capture, clear_outputs, connect

SOURCES = [
    "https://infosys.beckhoff.com/content/1033/tc3_userinterface/2531444363.html",
    "https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2528041355.html",
    "https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242732427.html",
]

HELPER = r"""param([string]$Settings)
$ErrorActionPreference='Stop'
$cfg=Get-Content -LiteralPath $Settings -Raw | ConvertFrom-Json
. $cfg.commands
. $cfg.generatedTmc
$mutex=[Threading.Mutex]::new($false,'Local\TcForge.Xae')
$acquired=$false; $registered=$false; $vs=$null
$profiles=@{}
try {
 try {$acquired=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$acquired=$true}
 if (-not $acquired) {throw 'Another TcForge XAE operation is running'}
 foreach($profile in Get-ChildItem (Split-Path $cfg.solution) -Recurse -File | Where-Object {$_.Extension -in @('.sln','.tsproj','.plcproj','.TcTTO')}) {
  $profiles[$profile.FullName]=[IO.File]::ReadAllBytes($profile.FullName)
 }
 [Reflection.Assembly]::LoadFrom($cfg.automation) | Out-Null
 $bin=Split-Path $cfg.automation
 Add-Type -ReferencedAssemblies @((Join-Path $bin 'Interop.TCatSysManagerLib.dll'),(Join-Path $bin 'Interop.EnvDTE.dll'),(Join-Path $bin 'Interop.EnvDTE80.dll')) -TypeDefinition @'
public static class OnlineChangeFixture {
 public static void ResolveAdsDependency(string bin) {
  // PowerShell does not read TcAutomation.exe.config's binding redirects.
  // Match the shipped redirect for ADS' older Unsafe reference in this owned process.
  var assembly=System.Reflection.Assembly.LoadFrom(System.IO.Path.Combine(bin,"System.Runtime.CompilerServices.Unsafe.dll"));
  System.AppDomain.CurrentDomain.AssemblyResolve += (sender,args) =>
   new System.Reflection.AssemblyName(args.Name).Name=="System.Runtime.CompilerServices.Unsafe" ? assembly : null;
 }
 public static void Edit(object pou, string kind) {
  if(kind=="declaration") {
   var d=(TCatSysManagerLib.ITcPlcDeclaration)pou;
   d.DeclarationText += "\r\nVAR\r\n    qualificationCopyMarker : UDINT;\r\nEND_VAR\r\n";
  } else {
   var i=(TCatSysManagerLib.ITcPlcImplementation)pou;
   i.ImplementationText += "\r\n// Qualification-only diagnostic task observation.\r\nownershipOwnerTask := Tc2_System.GETCURTASKINDEXEX();\r\n";
  }
 }
 public static void Select(object obj, string platform) {
  var d=(EnvDTE.DTE)obj;
  var configs=d.Solution.SolutionBuild.SolutionConfigurations;
  for(int index=1;index<=configs.Count;index++) {
   var c=(EnvDTE80.SolutionConfiguration2)configs.Item(index);
   if(c==null) continue;
   if(c.Name=="Release" && c.PlatformName==platform) { c.Activate(); return; }
  }
  throw new System.Exception("Requested Release platform is missing");
 }
}
'@
 if ($cfg.backend -eq 'mcp') {[OnlineChangeFixture]::ResolveAdsDependency($bin)}
 [TcAutomation.Core.MessageFilter]::Register(); $registered=$true
 $project=[TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($cfg.solution)
 $version=[TcAutomation.Core.TcFileUtilities]::GetTcVersion($project)
 $vs=[TcAutomation.Core.VisualStudioInstance]::new($cfg.solution,$version,$null)
 $vs.Load()
 Move-TcForgeGeneratedTmc -Repo $cfg.repo -ProjectFile $project
 $vs.LoadSolution()
 [OnlineChangeFixture]::Select($vs.Dte,$cfg.platform)
 $sm=$vs.GetSystemManager(); $sm.SetTargetNetId($cfg.target)
 $plc=$sm.LookupTreeItem('TIPC^Simulation^Simulation Project')
 $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><LoginCmd>true</LoginCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
 $deadline=[DateTime]::UtcNow.AddSeconds(30)
 do {
  [xml]$status=$plc.ProduceXml($false)
  [IO.File]::WriteAllText($cfg.beforeXml,$status.OuterXml)
  if ($status.TreeItem.IECProjectDef.OnlineSettings.LoggedIn -eq 'true') {break}
  if ([DateTime]::UtcNow -gt $deadline) {throw 'Engineering login not active'}
  Start-Sleep -Milliseconds 100
 } while ($true)
 function FindPou($node) {
  # ITcSmTreeItem is enumerable. A plain return expands its children and loses
  # a leaf POU entirely; keep each COM node as one pipeline object.
  if ([IO.Path]::GetFileNameWithoutExtension($node.Name) -eq 'MAIN') {return ,$node}
  for ($n=1;$n -le $node.ChildCount;$n++) {
   $child=$node.Child($n)
   $found=FindPou $child
   if ($null -ne $found) {return ,$found}
  }
  return $null
 }
 # Change the wrapper owned by the selected online Simulation application.
 $pou=$null
 try {$pou=$sm.LookupTreeItem('TIPC^Simulation^Simulation Project^Simulation^MAIN')} catch {}
 if ($null -eq $pou) {$pou=FindPou $plc}
 if ($null -eq $pou) {throw 'Simulation MAIN POU not found'}
 [OnlineChangeFixture]::Edit($pou,$cfg.kind)
 $vs.Dte.ExecuteCommand('File.SaveAll','')
 # Check only PLC objects before admitting motion. Do not use a full-system
 # SolutionBuild or Clean: Online Change generates/applies the actual delta.
 $check=[TcAutomation.Commands.CheckAllObjectsCommand]::ExecuteInSession($vs,'Simulation')
 $check | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $cfg.build -Encoding UTF8
 if (-not $check.Success -or $check.ErrorCount -ne 0 -or $check.WarningCount -ne 0) {throw 'Online-change PLC object check failed or warned'}
 if ($cfg.backend -eq 'mcp') {
  # The direct Automation Interface operation does not depend on a Visual
  # Studio menu command or the currently selected editor window.
  $chosen='TcAutomation.Commands.OnlineChangeCommand'
  @{Backend='mcp';Operation=$chosen;Available=$true} | ConvertTo-Json |
   Set-Content -LiteralPath $cfg.inventory -Encoding UTF8
 } else {
  $vs.Dte.ItemOperations.OpenFile($cfg.source) | Out-Null
  $chosen=Get-TcForgeOnlineChangeCommand -Dte $vs.Dte -Plc $plc
  @{Backend='fixture';Command=$chosen;Available=$true} | ConvertTo-Json |
   Set-Content -LiteralPath $cfg.inventory -Encoding UTF8
 }
 [IO.File]::WriteAllText($cfg.ready,'ready')
 $deadline=[DateTime]::UtcNow.AddSeconds(60)
 while (-not (Test-Path -LiteralPath $cfg.trigger)) {
  if ((Test-Path -LiteralPath $cfg.cancel) -or [DateTime]::UtcNow -gt $deadline) {throw 'Online-change trigger canceled or timed out'}
  Start-Sleep -Milliseconds 10
 }
 if (Test-Path -LiteralPath $cfg.cancel) {throw 'Online change canceled'}
 [IO.File]::WriteAllText($cfg.started,[DateTime]::UtcNow.ToString('o'))
 # VisualStudioInstance sets SilentMode. Never click or bypass a confirmation.
 if ($cfg.backend -eq 'mcp') {
  $expected=[uint32](Get-Content -LiteralPath $cfg.trigger -Raw)
  $dispatch=[TcAutomation.Commands.OnlineChangeCommand]::ExecuteInSession(
   $vs,$cfg.target,'Simulation',$cfg.contextFile,854,'MAIN.lifecycle.cycles',$expected,10000)
 } else {
  $dispatch=Invoke-TcForgeOnlineChange -Dte $vs.Dte -Plc $plc -ExpectedCommand $chosen
 }
 [xml]$status=$plc.ProduceXml($false)
 [IO.File]::WriteAllText($cfg.afterXml,$status.OuterXml)
 $dispatch.TargetNetId=$cfg.target
 $dispatch | ConvertTo-Json | Set-Content -LiteralPath $cfg.result -Encoding UTF8
} catch {
 @{Success=$false;ErrorMessage=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $cfg.result -Encoding UTF8
 throw
} finally {
 try {if($null -ne $vs){$vs.Close()}} finally {
  try {foreach($path in $profiles.Keys){[IO.File]::WriteAllBytes($path,$profiles[$path])}} finally {
   if($registered){[TcAutomation.Core.MessageFilter]::Revoke()}
   if($acquired){$mutex.ReleaseMutex()};$mutex.Dispose()
  }
 }
}
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_change(before, after, count_before, count_after, mode, policy="recover"):
    require(mode in ("idle", "moving"), "Unknown scenario")
    require(policy in ("recover", "preserve"), "Unknown online-change policy")
    require(
        count_after == count_before + 1,
        "Exactly one actual OnlineChangeCnt increment required",
    )
    if policy == "preserve":
        require(
            before["boot"] > 0 and after["boot"] == before["boot"],
            "Compatible edit changed session epoch",
        )
        require(
            before["session"] > 0 and after["session"] == before["session"],
            "Compatible edit lost session",
        )
        require(
            not after["faulted"] and after["inhibited"] == before["inhibited"],
            "Compatible edit interrupted operation",
        )
        if mode == "moving":
            for snapshot in (before, after):
                require(
                    snapshot["clamp_advance"]
                    and not snapshot["clamp_retract"]
                    and not snapshot["faulted"],
                    "Healthy advance required on both sides of compatible edit",
                )
        return
    # This field is a protocol epoch, deliberately rotated on online change.
    # Actual online change is proven separately by the runtime counter and retained fixture.
    require(
        before["boot"] > 0 and after["boot"] > 0 and after["boot"] != before["boot"],
        "Online change did not invalidate the old protocol epoch",
    )
    require(after["session"] == 0, "Old simulator session survived online change")
    require(
        count_after == count_before + 1,
        "Exactly one actual OnlineChangeCnt increment required",
    )
    if mode == "moving":
        require(
            bool(before["clamp_advance"]) != bool(before["clamp_retract"])
            and not before["faulted"],
            "No healthy active motion precondition",
        )
    require(
        not after["clamp_advance"]
        and not after["clamp_retract"]
        and after["inhibited"],
        "Online change retained motion intent",
    )


def validate_retained(before, after):
    for field in (
        "applicationMarker",
        "markerAtInitialization",
        "completedSequence",
        "diagnosticLastFault",
        "alarmActive",
        "alarmLatched",
        "alarmAcked",
    ):
        require(after[field] == before[field], field + " changed across online change")
    require(
        after["cycles"] > before["cycles"], "Runtime cycle history did not continue"
    )


def environment():
    env = os.environ.copy()
    common = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Beckhoff"
        / "TwinCAT"
    )
    env["PATH"] = (
        str(common / "Common64")
        + ";"
        + str(common / "Common32")
        + ";"
        + env.get("PATH", "")
    )
    return env


def wait_process(process, timeout):
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
        )
        process.wait(timeout=15)
        raise


def activate(args, path):
    script = Path(__file__).resolve().with_name("activate_simulation.ps1")
    with path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(script),
                "-Target",
                args.target,
                "-Platform",
                args.platform,
                "-McpRoot",
                str(args.mcp_root),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        require(
            wait_process(process, args.timeout) == 0,
            "Baseline activation failed: " + str(path),
        )


def cycle_command(snapshot):
    # Ready intentionally inhibits output commands between cycles.
    require(
        not snapshot["faulted"]
        and snapshot["healthy"]
        and (snapshot["state"] == 16 or not snapshot["inhibited"]),
        "Cyclic operation became unhealthy before online change",
    )
    return 2 if snapshot["state"] == 16 else 0


def run(args, evidence):
    from tcforge_sim.live import RpcTransport, AssemblySession
    from tcforge_sim.models import AssemblyPlant

    root = Path(__file__).resolve().parents[1]
    source = root / "TwinCAT/Simulation/MAIN.TcPOU"
    baseline = source.read_bytes()
    control = args.output / ("control-" + uuid.uuid4().hex)
    control.mkdir()
    (control / "MAIN.original.TcPOU").write_bytes(baseline)
    evidence["control_directory"] = str(control)
    evidence["source_sha256"] = hashlib.sha256(baseline).hexdigest()
    evidence["automation_sha256"] = hashlib.sha256(
        args.automation.read_bytes()
    ).hexdigest()
    paths = {
        key: control / key
        for key in (
            "ready",
            "trigger",
            "cancel",
            "started",
            "result",
            "build",
            "beforeXml",
            "afterXml",
            "inventory",
        )
    }
    settings = dict(
        automation=str(args.automation),
        solution=str(root / "TwinCAT/TcForge.Simulation.sln"),
        backend=args.command_backend,
        source=str(source),
        contextFile=str(source),
        target=args.target,
        platform=args.platform,
        kind=args.kind,
        commands=str(root / "scripts/online_change_commands.ps1"),
        generatedTmc=str(root / "scripts/prepare_generated_tmc.ps1"),
        repo=str(root),
        **{key: str(p) for key, p in paths.items()},
    )
    config = control / "settings.json"
    config.write_text(json.dumps(settings), encoding="utf-8")
    script = control / "online-change.ps1"
    script.write_text(HELPER, encoding="utf-8")
    process = rpc = session = conn = directory = None
    count_handle = None
    prepared = False
    original_error = None
    try:
        activate(args, control / "baseline-before.log")
        prepared = True
        with (
            (control / "helper.log").open("w", encoding="utf-8") as log,
            (control / "trace.jsonl").open("w", encoding="utf-8") as trace,
        ):
            process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(script),
                    "-Settings",
                    str(config),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment(),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            deadline = time.perf_counter() + args.timeout
            while not paths["ready"].exists():
                require(
                    process.poll() is None,
                    "Online-change preparation failed; inspect helper.log",
                )
                require(
                    time.perf_counter() < deadline,
                    "Online-change preparation timed out",
                )
                time.sleep(0.1)
            evidence["persistent_before"] = capture(args.target, 854, "safe")
            directory, pyads, conn = connect(args.target, 854)
            count_handle = conn.get_handle("MAIN.lifecycle.onlineChangeCount")
            conn.write_by_name(
                "MAIN.simulation.recoverOnOnlineChange",
                args.policy == "recover",
                pyads.PLCTYPE_BOOL,
            )
            rpc = RpcTransport(args.transport, args.target, 854)
            cycling = args.kind == "declaration" and args.mode == "moving"
            # Longer normal strokes reduce idle-boundary ambiguity while staying
            # below the reference machine's six-second movement timeout.
            evidence["travel_seconds"] = 2.0 if cycling else 0.5
            session = AssemblySession(
                rpc, trace, AssemblyPlant(travel_s=evidence["travel_seconds"])
            )
            session.until(lambda s: s["state"] == 0, command=4)
            session.tick()
            require(session.tick(5)["response"] == 0, "Initial Reset rejected")
            session.tick()
            if args.mode == "moving":
                session.until(lambda s: s["state"] == 16, command=1)
                session.until(
                    lambda s: s["clamp_advance"]
                    and 0.15 <= session.plant.clamp.position <= 0.8,
                    command=2,
                )
                session.plant.clamp.jammed = not cycling
            before = session.tick()
            evidence["before"] = before
            count_before = conn.read_by_name(
                "", pyads.PLCTYPE_UDINT, handle=count_handle
            )
            evidence["count_before"] = count_before
            old_session, old_frame = session.session, session.sequence
            plant = session.plant
            paths["trigger"].write_text(str(count_before), encoding="ascii")
            deadline = time.perf_counter() + args.change_timeout
            observations = []
            evidence["observations"] = observations
            after = None
            preceding = before
            next_command = 0
            while time.perf_counter() < deadline:
                current = None
                if session:
                    try:
                        current = session.tick(next_command)
                        old_frame = session.sequence
                    except Exception as exc:
                        evidence["old_session_rejection"] = str(exc)
                        old_frame = session.sequence
                        session = None  # Never replay an uncertain old-epoch frame.
                        rpc.close()
                        rpc = None
                try:
                    if rpc is None:
                        rpc = RpcTransport(args.transport, args.target, 854)
                    # tick already returns a confirmed PLC snapshot. Another
                    # synchronous RPC here needlessly consumes the IO feed budget.
                    if current is None:
                        current = rpc.snapshot()
                    if count_handle is None:
                        count_handle = conn.get_handle(
                            "MAIN.lifecycle.onlineChangeCount"
                        )
                    try:
                        count = conn.read_by_name(
                            "", pyads.PLCTYPE_UDINT, handle=count_handle
                        )
                    except pyads.ADSError as exc:
                        if (
                            exc.err_code == 1809
                        ):  # Symbol version changed: read-only handle recovery.
                            try:
                                conn.release_handle(count_handle)
                            except pyads.ADSError:
                                pass
                            count_handle = None
                        raise
                except Exception as exc:
                    observations.append(dict(transient_error=str(exc)))
                    if rpc:
                        rpc.close()
                        rpc = None
                    time.sleep(0.05)
                    continue
                observations.append(dict(snapshot=current, count=count))
                if args.mode == "moving" and current["boot"] == before["boot"]:
                    if cycling:
                        next_command = cycle_command(current)
                    else:
                        require(
                            current["clamp_advance"]
                            and not current["clamp_retract"]
                            and not current["faulted"],
                            "Motion ended in the old epoch before online change; acceptance is inconclusive",
                        )
                if count != count_before and (
                    args.policy == "preserve" or current["boot"] != before["boot"]
                ):
                    after = current
                    break
                if count == count_before:
                    preceding = current
                if process.poll() is not None and process.returncode != 0:
                    raise AssertionError("Online-change helper failed")
            evidence["observations"] = observations
            require(
                after is not None,
                "OnlineChangeCnt never incremented; command or confirmation did not apply",
            )
            # A count read may straddle a scan; read the current published snapshot.
            after = rpc.snapshot()
            evidence["after"] = after
            evidence["count_after"] = count
            if cycling:
                # Use the last observed pre-change frame, not motion that occurred
                # seconds earlier at dispatch. An idle boundary is inconclusive.
                evidence["at_dispatch"] = before
                before = preceding
                evidence["before"] = before
            validate_change(before, after, count_before, count, args.mode, args.policy)
            if args.policy == "preserve":
                require(
                    session is not None and not session.failed,
                    "Compatible edit lost the IO feed",
                )
                plant.clamp.jammed = False
                if args.mode == "moving":
                    session.until(lambda s: s["clamp_retract"])
                    evidence["continued_cycle"] = session.until(
                        lambda s: s["state"] == 16
                    )
                # Runtime behavior is proven. Release the IO owner before waiting
                # for XAE to close; engineering-process shutdown is outside the
                # cyclic feed contract and can pause the Python process briefly.
                evidence["session_release"] = session.close()
                session = None
                deadline = time.perf_counter() + args.timeout
                while process.poll() is None:
                    require(
                        time.perf_counter() < deadline, "Online helper did not finish"
                    )
                    time.sleep(0.01)
                require(process.returncode == 0, "Online-change helper failed")
                result = json.loads(paths["result"].read_text(encoding="utf-8-sig"))
                require(
                    paths["started"].exists() and result.get("Dispatched") is True,
                    "No online-change dispatch evidence",
                )
                evidence["command_result"] = result
                evidence["persistent_after_change"] = capture(args.target, 854)
                validate_retained(
                    evidence["persistent_before"], evidence["persistent_after_change"]
                )
                return
            stale_claim = rpc.call("claim", old_session, before["boot"])
            stale_exchange = rpc.call(
                "exchange",
                old_session,
                before["boot"],
                old_frame + 1,
                before["cycle"],
                0,
                0,
                1,
                1,
                2,
            )
            evidence["stale_requests"] = dict(
                claim=stale_claim, exchange=stale_exchange
            )
            require(
                stale_claim == 34 and stale_exchange == 34,
                "Old-epoch requests were not rejected",
            )
            unchanged = rpc.snapshot()
            require(
                unchanged["session"] == 0
                and unchanged["applied"] == after["applied"]
                and not unchanged["clamp_advance"]
                and not unchanged["clamp_retract"],
                "Stale requests mutated new epoch",
            )
            session = None
            require(
                paths["started"].exists(),
                "Counter changed before requested online command",
            )
            # No new simulator session exists yet; old commands cannot be replayed.
            deadline = time.perf_counter() + args.timeout
            while process.poll() is None:
                require(time.perf_counter() < deadline, "Online helper did not finish")
                time.sleep(0.01)
            require(
                process.returncode == 0,
                "Online-change helper did not finish successfully",
            )
            result = json.loads(paths["result"].read_text(encoding="utf-8-sig"))
            evidence["command_result"] = result
            require(
                result.get("Dispatched") is True
                and result.get("Operation") == "OnlineChange",
                "No online command dispatch evidence",
            )
            if args.command_backend == "mcp":
                require(
                    result.get("Success") is True
                    and result.get("RuntimeVerified") is True,
                    "MCP online-change runtime verification did not pass",
                )
            evidence["persistent_after_change"] = capture(args.target, 854)
            validate_retained(
                evidence["persistent_before"], evidence["persistent_after_change"]
            )
            plant.clamp.jammed = False
            session = AssemblySession(rpc, trace, plant)
            reconnected = session.tick()
            evidence["reconnected"] = reconnected
            require(
                not reconnected["clamp_advance"] and not reconnected["clamp_retract"],
                "New connection resumed old motion",
            )
            session.until(lambda s: s["state"] == 0, command=4)
            session.tick()
            require(session.tick(5)["response"] == 0, "Recovery Reset rejected")
            session.tick()
            evidence["recovered_home"] = session.until(
                lambda s: s["state"] == 16, command=1
            )
            session.until(lambda s: s["clamp_advance"], command=2)
            session.until(lambda s: s["clamp_retract"])
            evidence["recovered_cycle"] = session.until(lambda s: s["state"] == 16)
            session.close()
            session = None
            evidence["persistent_after"] = capture(args.target, 854)
            validate_retained(
                evidence["persistent_before"], evidence["persistent_after"]
            )
    except BaseException as exc:
        original_error = exc
        # Preserve the cause while potentially lengthy baseline restoration runs.
        evidence["failure"] = traceback.format_exc()
        (args.output / "online-change-evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        raise
    finally:
        paths["cancel"].write_text("cancel", encoding="ascii")
        errors = []
        if conn and count_handle is not None:
            try:
                conn.release_handle(count_handle)
            except Exception:
                pass  # It may have been invalidated by the tested online change.
        if session:
            try:
                session.close()
            except Exception as exc:
                errors.append("Session release: " + str(exc))
        for resource in (rpc, conn, directory):
            if resource:
                try:
                    resource.close()
                except Exception as exc:
                    errors.append("Transport cleanup: " + str(exc))
        if process and process.poll() is None:
            try:
                wait_process(process, 20)
            except Exception as exc:
                errors.append("Helper shutdown: " + str(exc))
        # Restore only after the XAE helper has exited and released file ownership.
        if paths["result"].exists():
            try:
                evidence["command_result"] = json.loads(
                    paths["result"].read_text(encoding="utf-8-sig")
                )
            except (OSError, ValueError) as exc:
                errors.append("Command receipt: " + str(exc))
        source.write_bytes(baseline)
        evidence["source_restored"] = source.read_bytes() == baseline
        if prepared:
            try:
                activate(args, control / "baseline-after.log")
                evidence["baseline_restored"] = True
                evidence["cleanup"] = clear_outputs(args.target, 854)
            except Exception as exc:
                errors.append("Baseline restoration: " + str(exc))
        evidence["cleanup_errors"] = errors
        if errors and original_error is None:
            raise RuntimeError("; ".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--platform", required=True, choices=("TwinCAT RT (x64)", "TwinCAT OS (x64)")
    )
    parser.add_argument(
        "--kind", required=True, choices=("implementation", "declaration")
    )
    parser.add_argument("--mode", required=True, choices=("idle", "moving"))
    parser.add_argument(
        "--policy",
        choices=("recover", "preserve"),
        default="recover",
        help="Preserve is experimental qualification of compatible implementation edits only",
    )
    parser.add_argument("--mcp-root", type=Path, default=root.parent / "twincat-mcp")
    parser.add_argument(
        "--command-backend", choices=("fixture", "mcp"), default="fixture"
    )
    parser.add_argument(
        "--automation", type=Path, help="Optional isolated MCP assembly build"
    )
    parser.add_argument(
        "--transport",
        type=Path,
        default=root / "artifacts/simulation-rpc/SimulationRpc.exe",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument(
        "--change-timeout",
        type=float,
        default=30,
        help="Engineering compilation/application deadline; does not change IO or motion timeouts",
    )
    args = parser.parse_args()
    if args.policy == "preserve" and args.kind != "implementation":
        parser.error(
            "Declaration/layout preservation has not been qualified; use recover policy"
        )
    if os.name != "nt":
        parser.error("Windows XAE required")
    for key in ("timeout", "change_timeout"):
        if not math.isfinite(getattr(args, key)) or not 0 < getattr(args, key) <= 900:
            parser.error("Invalid timeout")
    args.mcp_root = args.mcp_root.resolve(strict=True)
    args.automation = (
        args.automation
        or args.mcp_root / "TcAutomation/bin/Release-v2/TcAutomation.exe"
    ).resolve(strict=True)
    args.transport = args.transport.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = dict(
        target=args.target,
        kind=args.kind,
        mode=args.mode,
        policy=args.policy,
        command_backend=args.command_backend,
        passed=False,
        sources=SOURCES,
    )
    suite = ET.Element("testsuite", name="TcForge actual online change", tests="1")
    case = ET.SubElement(suite, "testcase", name=args.kind + "_" + args.mode)
    try:
        run(args, evidence)
        evidence["passed"] = True
    except Exception as exc:
        evidence["failure"] = traceback.format_exc()
        ET.SubElement(case, "failure", message=str(exc)).text = evidence["failure"]
    suite.set("failures", "0" if evidence["passed"] else "1")
    (args.output / "online-change-evidence.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    ET.ElementTree(suite).write(
        args.output / "online-change-junit.xml", encoding="utf-8", xml_declaration=True
    )
    print("PASS" if evidence["passed"] else "FAIL", args.kind, args.mode, flush=True)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
