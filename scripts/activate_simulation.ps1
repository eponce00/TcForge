# Builds, activates and restarts the isolated simulation on the explicitly named target.
# This replaces the target's active TwinCAT configuration. Use a dedicated test runtime.
param([Parameter(Mandatory=$true)][string]$Target, [Parameter(Mandatory=$true)][ValidateSet("TwinCAT OS (x64)", "TwinCAT RT (x64)")][string]$Platform, [string]$McpRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
. (Join-Path $PSScriptRoot 'prepare_generated_tmc.ps1')
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
if ($PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'Use powershell.exe (Windows PowerShell 5.1) for the .NET Framework COM helper.'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release')).Path
$artifacts = Join-Path $repo 'artifacts'
$python = Join-Path $repo 'artifacts/sim-venv/Scripts/python.exe'
$transport = Join-Path $repo 'artifacts/simulation-rpc/SimulationRpc.exe'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $transport)) {
    throw 'Install the simulation Python environment and build_simulation_rpc.ps1 first.'
}

New-Item -ItemType Directory -Force $artifacts | Out-Null
[Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
Add-Type -ReferencedAssemblies @(
    (Join-Path $bin 'Interop.EnvDTE.dll'),
    (Join-Path $bin 'Interop.EnvDTE80.dll'),
    (Join-Path $bin 'Interop.TCatSysManagerLib.dll')
) -TypeDefinition @'
public static class TcForgeBuild {
    public static void EnableBoot(object plc) {
        ((TCatSysManagerLib.ITcPlcProject)plc).BootProjectAutostart = true;
    }
    public static void SelectTarget(object obj, string platform) {
        var dte = (EnvDTE.DTE)obj;
        var configs = dte.Solution.SolutionBuild.SolutionConfigurations;
        for (int index = 1; index <= configs.Count; index++) {
            var cfg = (EnvDTE80.SolutionConfiguration2)configs.Item(index);
            if (cfg == null) continue;
            if (cfg.Name == "Release" && cfg.PlatformName == platform) {
                cfg.Activate(); return;
            }
        }
        throw new System.Exception("Requested Release configuration is missing");
    }

}
'@

$solution = Join-Path $repo 'TwinCAT/TcForge.Simulation.sln'
$version = (Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json).xaeBaseline
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running. Run build/activation/tests sequentially.' }
[TcAutomation.Core.MessageFilter]::Register()
$vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $version, $null)
$profiles = @{}
try {
    foreach ($profile in Get-ChildItem (Join-Path $repo 'TwinCAT') -Recurse -File | Where-Object { $_.Extension -in @('.sln', '.tsproj', '.plcproj', '.TcTTO') }) {
        $profiles[$profile.FullName] = [IO.File]::ReadAllBytes($profile.FullName)
    }
    $vs.Load()
    Move-TcForgeGeneratedTmc -Repo $repo -ProjectFile ([TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($solution))
    $vs.LoadSolution()
    [TcForgeBuild]::SelectTarget($vs.Dte, $Platform)
    $sm = $vs.GetSystemManager()
    $sm.SetTargetNetId($Target)
    $build = [TcAutomation.Commands.BuildCommand]::ExecuteInSession($vs, $true)
    $build | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $artifacts 'simulation-activation-build.json')
    if (-not $build.Success) { throw $build.Summary }
    $task = $sm.LookupTreeItem('TIRT^Simulation')
    $task.ConsumeXml('<TreeItem><TaskDef><Disabled>false</Disabled><AutoStart>true</AutoStart></TaskDef></TreeItem>')
    [TcForgeBuild]::EnableBoot($sm.LookupTreeItem('TIPC^Simulation'))
    $automation = [TcAutomation.Core.AutomationInterface]::new($vs)
    $automation.SetDontCheckTarget($Target)
    $activation = [TcAutomation.Commands.ActivateCommand]::ExecuteInSession($vs, $solution, $Target)
    if (-not $activation.Success) { throw $activation.ErrorMessage }
    $restart = [TcAutomation.Commands.RestartCommand]::ExecuteInSession($vs, $solution, $Target)
    if (-not $restart.Success) { throw $restart.ErrorMessage }
    & $python -c 'import sys; from pathlib import Path; from tcforge_sim.live import RpcTransport; r=RpcTransport(Path(sys.argv[1]),sys.argv[2],854); s=r.snapshot(); r.close(); assert s[''boot''] > 0 and s[''owner''] > 0, s; print(s)' $transport $Target
    if ($LASTEXITCODE -ne 0) { throw 'Activation did not produce a running simulation endpoint on port 854.' }
    $restart | ConvertTo-Json
} finally {
    try { $vs.Close() } finally {
        try {
            foreach ($profilePath in $profiles.Keys) { [IO.File]::WriteAllBytes($profilePath, $profiles[$profilePath]) }
        } finally {
            [TcAutomation.Core.MessageFilter]::Revoke()
            $mutex.ReleaseMutex()
            $mutex.Dispose()
        }
    }
}
