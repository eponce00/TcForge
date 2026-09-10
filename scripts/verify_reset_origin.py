"""Verify actual ResetOriginCmd and application removal before same-source reload.

Dedicated unmapped Simulation runtime only. Deletes its PLC application, then invokes
activate_simulation.ps1 to reload the unchanged source. Fresh-deployment values alone
are insufficient evidence. This does not test abrupt power-loss durability.
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

from lifecycle_fixture import capture, clear_outputs, connect, validate_seeded

SOURCES = [
    'https://infosys.beckhoff.com/content/1033/tc3_userinterface/2531471243.html',
    'https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2527625355.html',
    'https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242730891.html',
]

HELPER = r"""param([string]$Settings)
$ErrorActionPreference='Stop'
$cfg=Get-Content -LiteralPath $Settings -Raw | ConvertFrom-Json
$mutex=[Threading.Mutex]::new($false,'Local\TcForge.Xae')
$acquired=$false; $registered=$false; $vs=$null
try {
    try {$acquired=$mutex.WaitOne(0)} catch [Threading.AbandonedMutexException] {$acquired=$true}
    if (-not $acquired) {throw 'Another TcForge XAE operation is running'}
    [Reflection.Assembly]::LoadFrom($cfg.automation) | Out-Null
    [TcAutomation.Core.MessageFilter]::Register(); $registered=$true
    $project=[TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($cfg.solution)
    $version=[TcAutomation.Core.TcFileUtilities]::GetTcVersion($project)
    $vs=[TcAutomation.Core.VisualStudioInstance]::new($cfg.solution,$version,$null)
    $vs.Load(); $vs.LoadSolution()
    $sm=$vs.GetSystemManager(); $sm.SetTargetNetId($cfg.target)
    $plc=$sm.LookupTreeItem('TIPC^Simulation^Simulation Project')
    $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><LoginCmd>true</LoginCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do {
        [xml]$status=$plc.ProduceXml($false)
        [IO.File]::WriteAllText($cfg.beforeXml,$status.OuterXml)
        if ($status.TreeItem.IECProjectDef.OnlineSettings.LoggedIn -eq 'true') {break}
        if ([DateTime]::UtcNow -gt $deadline) {throw 'Engineering login not confirmed; reset not issued'}
        Start-Sleep -Milliseconds 100
    } while ($true)
    [IO.File]::WriteAllText($cfg.ready,'ready')
    $deadline=[DateTime]::UtcNow.AddSeconds(60)
    while (-not (Test-Path -LiteralPath $cfg.trigger)) {
        if ((Test-Path -LiteralPath $cfg.cancel) -or [DateTime]::UtcNow -gt $deadline) {throw 'Origin trigger canceled or timed out'}
        Start-Sleep -Milliseconds 50
    }
    if (Test-Path -LiteralPath $cfg.cancel) {throw 'Origin canceled'}
    [IO.File]::WriteAllText($cfg.started,[DateTime]::UtcNow.ToString('o'))
    $plc.ConsumeXml('<TreeItem><IECProjectDef><OnlineSettings><Commands><ResetOriginCmd>true</ResetOriginCmd></Commands></OnlineSettings></IECProjectDef></TreeItem>')
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do {
        [xml]$status=$plc.ProduceXml($false)
        [IO.File]::WriteAllText($cfg.afterXml,$status.OuterXml)
        if ($status.TreeItem.IECProjectDef.OnlineSettings.LoggedIn -eq 'false') {break}
        if ([DateTime]::UtcNow -gt $deadline) {throw 'Origin did not log engineering out'}
        Start-Sleep -Milliseconds 100
    } while ($true)
    @{Success=$true; Operation='ResetOriginCmd'; TargetNetId=$cfg.target} | ConvertTo-Json | Set-Content -LiteralPath $cfg.result -Encoding UTF8
} catch {
    @{Success=$false; ErrorMessage=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $cfg.result -Encoding UTF8
    throw
} finally {
    try {if ($null -ne $vs) {$vs.Close()}} finally {
        if ($registered) {[TcAutomation.Core.MessageFilter]::Revoke()}
        if ($acquired) {$mutex.ReleaseMutex()}; $mutex.Dispose()
    }
}
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def online_status(xml):
    node = ET.fromstring(xml).find('./IECProjectDef/OnlineSettings')
    require(node is not None, 'Engineering OnlineSettings absent')
    return {child.tag: child.text for child in node if child.tag != 'Commands'}


def validate_origin_transition(before_xml, after_xml, result, removal, target):
    require(result.get('Success') is True and result.get('Operation') == 'ResetOriginCmd',
            'Actual ResetOriginCmd did not report success')
    require(result.get('TargetNetId') == target, 'Reset result target mismatch')
    require(online_status(before_xml).get('LoggedIn') == 'true', 'No prior engineering login')
    require(online_status(after_xml).get('LoggedIn') == 'false', 'Origin did not log engineering out')
    require(removal.get('symbol_error_code') in (6, 1808), 'No verified application/symbol removal')
    require(removal.get('system_ads_state') == 5, 'System port not independently healthy in RUN')


def validate_initialized(before, after):
    validate_seeded(before, 'seed')
    for field in ('applicationMarker', 'markerAtInitialization', 'completedSequence', 'diagnosticLastFault'):
        require(after[field] == 0, field + ' was not initialized')
    for field in ('defaultOutput', 'restoreOutput', 'alarmActive', 'alarmLatched', 'alarmAcked', 'diagnosticFaulted'):
        require(after[field] is False, field + ' survived origin')
    for field in ('defaultInhibited', 'restoreInhibited', 'analogInhibited'):
        require(after[field] is True, field + ' did not inhibit startup')
    require(after['analogRaw'] == 17, 'Analog fallback was not initialized')
    require(after['cycles'] > 0, 'Reloaded fixture is not running')


def source_hashes(root):
    # Generated boot artifacts and target configuration may change during activation.
    suffixes = {'.tcpou', '.tcdut', '.tcgvl', '.tctto'}
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.suffix.lower() in suffixes}


def prove_removed(target, port):
    removal = {}
    directory, pyads, conn = connect(target, 10000)
    try:
        removal['system_ads_state'] = conn.read_state()[0]
    finally:
        conn.close(); directory.close()
    directory, pyads, conn = connect(target, port)
    try:
        try:
            conn.read_by_name('MAIN.lifecycle.applicationMarker', pyads.PLCTYPE_UINT)
        except pyads.ADSError as exc:
            removal['symbol_error_code'] = exc.err_code
            removal['symbol_error'] = str(exc)
        else:
            raise AssertionError('Lifecycle symbol still exists after ResetOrigin; refusing deployment')
    finally:
        conn.close(); directory.close()
    require(removal.get('symbol_error_code') in (6, 1808), 'Unexpected ADS failure; not application removal evidence')
    return removal


def run(args, evidence):
    activation=Path(__file__).resolve().with_name('activate_simulation.ps1')
    require(args.solution == activation.parent.parent/'TwinCAT'/'TcForge.Simulation.sln',
            'Activation helper only supports canonical simulation solution')
    control=args.output / ('control-' + uuid.uuid4().hex); control.mkdir()
    paths={key: control / key for key in ('ready','trigger','cancel','started','result','beforeXml','afterXml')}
    settings=dict(automation=str(args.automation),solution=str(args.solution),target=args.target,
                  **{key:str(path) for key,path in paths.items()})
    script=control/'origin.ps1'; script.write_text(HELPER,encoding='utf-8')
    config=control/'settings.json'; config.write_text(json.dumps(settings),encoding='utf-8')
    evidence['control_directory']=str(control)
    baseline=source_hashes(args.solution.parent)
    require(baseline, 'No PLC source manifest')
    evidence['source_sha256']=baseline
    environment=os.environ.copy()
    common=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Beckhoff'/'TwinCAT'
    environment['PATH']=str(common/'Common64')+';'+str(common/'Common32')+';'+environment.get('PATH','')
    process=None
    try:
        with (control/'helper.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-File',str(script),'-Settings',str(config)],
                                     stdout=log,stderr=subprocess.STDOUT,env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.perf_counter()+args.timeout
            while not paths['ready'].exists():
                require(process.poll() is None, 'Origin helper failed during login')
                require(time.perf_counter()<deadline, 'Origin helper login timed out')
                time.sleep(.1)
            evidence['before']=capture(args.target,args.port,'seed')
            paths['trigger'].write_text('origin',encoding='ascii')
            process.wait(timeout=args.timeout)
        require(process.returncode == 0,'Origin helper failed; inspect helper.log')
        result=json.loads(paths['result'].read_text(encoding='utf-8-sig'))
        evidence['origin_result']=result
        evidence['removal']=prove_removed(args.target,args.port)
        validate_origin_transition(paths['beforeXml'].read_text(), paths['afterXml'].read_text(),
                                   result,evidence['removal'],args.target)
        evidence['removal_verified_before_reload']=True
        require(source_hashes(args.solution.parent)==baseline,'Source changed before reload')
        with (control/'reload.log').open('w',encoding='utf-8') as log:
            reload=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-File',str(activation),
                                   '-Target',args.target,'-Platform',args.platform,'-McpRoot',str(args.mcp_root)],
                                  stdout=log,stderr=subprocess.STDOUT,env=environment,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                reload.wait(timeout=args.reload_timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(reload.pid),'/T','/F'],capture_output=True,timeout=15)
                raise
        require(reload.returncode==0,'Same-source reload failed; inspect reload.log')
        require(source_hashes(args.solution.parent)==baseline,'PLC source changed during reload')
        evidence['after']=capture(args.target,args.port)
        validate_initialized(evidence['before'],evidence['after'])
        evidence['cleanup']=clear_outputs(args.target,args.port)
    finally:
        paths['cancel'].write_text('cancel',encoding='ascii')
        if process and process.poll() is None:
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
        if evidence.get('before') and not evidence.get('cleanup'):
            try:
                evidence['failure_cleanup']=clear_outputs(args.target,args.port)
            except Exception as exc:
                evidence['failure_cleanup_error']=str(exc)
        if paths['started'].exists() and not evidence.get('removal_verified_before_reload'):
            evidence['recovery_note']='Reset may have deleted application; automatic reload intentionally withheld without removal proof.'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    root=Path(__file__).resolve().parents[1]
    parser.add_argument('--target',required=True)
    parser.add_argument('--port',type=int,default=854)
    parser.add_argument('--platform',required=True,choices=('TwinCAT OS (x64)','TwinCAT RT (x64)'))
    parser.add_argument('--solution',type=Path,default=root/'TwinCAT'/'TcForge.Simulation.sln')
    parser.add_argument('--mcp-root',type=Path,default=root.parent/'twincat-mcp')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=240)
    parser.add_argument('--reload-timeout',type=float,default=600)
    args=parser.parse_args()
    if os.name!='nt': parser.error('Windows XAE required')
    if args.port != 854: parser.error('Canonical simulation activation uses port 854')
    for key in ('timeout','reload_timeout'):
        if not math.isfinite(getattr(args,key)) or not 0<getattr(args,key)<=900: parser.error('Timeout must be finite and between 0 and 900 seconds')
    args.solution=args.solution.resolve(strict=True); args.mcp_root=args.mcp_root.resolve(strict=True)
    args.automation=(args.mcp_root/'TcAutomation/bin/Release/TcAutomation.exe').resolve(strict=True)
    args.output=args.output.resolve(); args.output.mkdir(parents=True,exist_ok=True)
    evidence=dict(target=args.target,port=args.port,sources=SOURCES,passed=False,scope='Actual Reset origin, removal before reload, persistent initialization; no power-loss guarantee')
    suite=ET.Element('testsuite',name='TcForge Reset origin',tests='1')
    case=ET.SubElement(suite,'testcase',name='ResetOriginClearsPersistentState')
    try:
        run(args,evidence); evidence['passed']=True
    except Exception as exc:
        evidence['failure']=traceback.format_exc()
        ET.SubElement(case,'failure',message=str(exc)).text=evidence['failure']
    suite.set('failures','0' if evidence['passed'] else '1')
    (args.output/'origin-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    ET.ElementTree(suite).write(args.output/'origin-junit.xml',encoding='utf-8',xml_declaration=True)
    print('PASS' if evidence['passed'] else 'FAIL','ResetOriginClearsPersistentState',flush=True)
    return 0 if evidence['passed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
