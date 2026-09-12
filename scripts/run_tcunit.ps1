# Rebuilds and runs TcUnit on a dedicated target using an explicit platform.
# This replaces the target's active TwinCAT configuration. Use a dedicated test runtime.
param([Parameter(Mandatory=$true)][string]$Target, [Parameter(Mandatory=$true)][ValidateSet("TwinCAT OS (x64)", "TwinCAT RT (x64)")][string]$Platform, [ValidateSet(1,10)][int]$CycleTimeMs = 10, [string]$McpRoot, [string]$BuildEvidence, [string]$RunDirectory, [string]$InstalledLibrary, [switch]$Development)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
. (Join-Path $PSScriptRoot 'prepare_generated_tmc.ps1')
. (Join-Path $PSScriptRoot 'installed_reference_profile.ps1')
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
if ($PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'Use powershell.exe (Windows PowerShell 5.1) for the .NET Framework COM helper.'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release-v2')).Path
$artifacts = Join-Path $repo 'artifacts'
New-Item -ItemType Directory -Force $artifacts | Out-Null
if (-not $BuildEvidence) { $BuildEvidence = Join-Path $artifacts 'build-evidence.json' }
if (-not $RunDirectory) { $RunDirectory = Join-Path $artifacts ('tcunit-' + $CycleTimeMs + 'ms-' + [Guid]::NewGuid().ToString('N')) }
if (Test-Path -LiteralPath $RunDirectory) { throw 'RunDirectory must be new; existing evidence is never overwritten.' }
New-Item -ItemType Directory -Path $RunDirectory | Out-Null
$RunDirectory = (Resolve-Path -LiteralPath $RunDirectory).Path
$runToken = Join-Path $RunDirectory 'run-token.json'
$runReport = Join-Path $RunDirectory 'tcunit.xml'
$runBuild = Join-Path $RunDirectory 'activation-build.json'
$lock = Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json
if ($Platform -ne $lock.platform) { throw 'Evidence workflow requires the qualified toolchain platform.' }
if (-not $Development -and -not $InstalledLibrary) {
    [xml]$libraryProject = Get-Content (Join-Path $repo 'TwinCAT/TcForge/TcForge.plcproj') -Raw
    $publisher = [string]($libraryProject.Project.PropertyGroup.Company | Where-Object { $_ } | Select-Object -First 1)
    $InstalledLibrary = Join-Path $env:ProgramData ('Beckhoff/TwinCAT/PlcEngineering/Managed Libraries/' + $publisher + '/TcForge/' + $lock.libraryVersion + '/TcForge.library')
}

if (-not $Development) {
$declaredBuild = Get-Content -LiteralPath $BuildEvidence -Raw | ConvertFrom-Json
$declaredHelperRoot = (Resolve-Path -LiteralPath ([string]$declaredBuild.helper.root)).Path
$selectedHelperRoot = (Resolve-Path -LiteralPath $McpRoot).Path
if ($selectedHelperRoot -ne $declaredHelperRoot) { throw 'Selected MCP helper root differs from build provenance.' }
}

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

$solution = Join-Path $repo 'TwinCAT/TcForge.Tests.sln'
$version = (Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json).xaeBaseline
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running. Run build/activation/tests sequentially.' }
[TcAutomation.Core.MessageFilter]::Register()
$vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $version, $null)
$plcTaskPath = Join-Path $repo 'TwinCAT/Testing/Testing.TcTTO'
$systemProjectPath = Join-Path $repo 'TwinCAT/TcForge.Tests.tsproj'
$originalPlcTaskBytes = [IO.File]::ReadAllBytes($plcTaskPath)
$originalSystemProjectBytes = [IO.File]::ReadAllBytes($systemProjectPath)
$originalPlcTask = [IO.File]::ReadAllText($plcTaskPath)
$originalSystemProject = [IO.File]::ReadAllText($systemProjectPath)
$originalSystemTask = [regex]::Match($originalSystemProject, '<Task\b[^>]*AmsPort="351"[^>]*>').Value
$utf8 = [Text.UTF8Encoding]::new($false)
$completed = $false
$referenceProfiles = @{}
foreach ($relative in @('Testing.plcproj','Simulation.plcproj','TcForgeExample/TcForgeExample.plcproj')) {
    $path = Join-Path $repo ('TwinCAT/' + $relative)
    $referenceProfiles[$path] = [IO.File]::ReadAllBytes($path)
}
try {
    if (-not $Development) {
    & python (Join-Path $PSScriptRoot 'build_evidence.py') begin-test --build $BuildEvidence --library (Join-Path $artifacts 'TcForge.library') --installed-library $InstalledLibrary --cycle-ms $CycleTimeMs --target $Target --output $runToken
    if ($LASTEXITCODE -ne 0) { throw 'Test build provenance validation failed before activation.' }
    Set-TcForgeInstalledReferences -TwinCATRoot (Join-Path $repo 'TwinCAT')
    }
    if (-not $originalSystemTask) { throw 'Testing system task definition is missing' }
    # PLC task periods use microseconds; system task periods use 100 ns units.
    # Both definitions must agree before the compiler resolves the task binding.
    $configuredPlcTask = [regex]::Replace($originalPlcTask, '<CycleTime>\d+</CycleTime>', ('<CycleTime>' + ($CycleTimeMs * 1000) + '</CycleTime>'))
    [IO.File]::WriteAllText($plcTaskPath, $configuredPlcTask, $utf8)
    $configuredSystemTask = [regex]::Replace($originalSystemTask, 'CycleTime="\d+"', ('CycleTime="' + ($CycleTimeMs * 10000) + '"'))
    $configuredSystemProject = $originalSystemProject.Replace($originalSystemTask, $configuredSystemTask)
    # The generated PLC context stores nanoseconds. Keep it coherent at load time.
    $configuredSystemProject = [regex]::Replace($configuredSystemProject, '<CycleTime>\d+</CycleTime>', ('<CycleTime>' + ($CycleTimeMs * 1000000) + '</CycleTime>'))
    [IO.File]::WriteAllText($systemProjectPath, $configuredSystemProject, $utf8)
    $vs.Load()
    Move-TcForgeGeneratedTmc -Repo $repo -ProjectFile $systemProjectPath
    $vs.LoadSolution()
    $vs.GetSystemManager().SetTargetNetId($Target)
    [TcForgeBuild]::SelectTarget($vs.Dte, $Platform)
    $task = $vs.GetSystemManager().LookupTreeItem('TIRT^Testing')
    $task.ConsumeXml("<TreeItem><TaskDef><CycleTime>" + ($CycleTimeMs * 10000) + "</CycleTime></TaskDef></TreeItem>")
    [xml]$taskDescription = $task.ProduceXml($false)
    if ([int]$taskDescription.TreeItem.TaskDef.CycleTime -ne ($CycleTimeMs * 10000)) { throw 'XAE did not apply the requested task period' }
    $build = [TcAutomation.Commands.BuildCommand]::ExecuteInSession($vs, $true)
    $build | Add-Member -NotePropertyName RequestedXaeVersion -NotePropertyValue $version
    $build | Add-Member -NotePropertyName EffectiveXaeVersion -NotePropertyValue $vs.EffectiveTwinCATVersion
    $build | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $runBuild
    if (-not $build.Success -or $build.WarningCount -ne 0) { throw ($build.Summary + ' ' + $build.BuildOutput) }
    $sm = $vs.GetSystemManager()
    if ($Development) {
        $xml = $sm.LookupTreeItem('TIPC^Testing^Testing Project').ProduceXml($false)
        [IO.File]::WriteAllText((Join-Path $RunDirectory 'source-reference.xml'), $xml)
        [xml]$resolved = $xml
        $reference = @($resolved.SelectNodes("//IECProjectDef/References/PlaceholderReference[PlaceholderName='TcForge']"))
        if ($reference.Count -ne 1 -or [string]$reference[0].EffectiveResolution.LibraryName -ne '[TcForge]') { throw 'Development tests require the TcForge source project.' }
        @{ scope='Development source-reference run; not installed-artifact release evidence'; target=$Target; cycleTimeMs=$CycleTimeMs } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $RunDirectory 'development.json')
    }
    $sm.LookupTreeItem('TIRT^Testing').ConsumeXml('<TreeItem><TaskDef><Disabled>false</Disabled><AutoStart>true</AutoStart></TaskDef></TreeItem>')
    [TcForgeBuild]::EnableBoot($sm.LookupTreeItem('TIPC^Testing'))
    $automation = [TcAutomation.Core.AutomationInterface]::new($vs)
    $automation.SetDontCheckTarget($Target)
    $activation = [TcAutomation.Commands.ActivateCommand]::ExecuteInSession($vs, $solution, $Target)
    if (-not $activation.Success) { throw $activation.ErrorMessage }
    $restart = [TcAutomation.Commands.RestartCommand]::ExecuteInSession($vs, $solution, $Target)
    if (-not $restart.Success) { throw $restart.ErrorMessage }
    # Keep ADS dependencies in the helper executable's configured process.
    # The exporter verifies every source test identity/result, not just totals.
    $deadline = [DateTime]::UtcNow.AddMinutes(2)
    do {
        $exportArgs = @('--target', $Target, '--helper', (Join-Path $bin 'TcAutomation.exe'), '--output', $runReport, '--expected-cycle-ms', $CycleTimeMs)
        if (-not $Development) { $exportArgs += @('--provenance-token', $runToken) }
        & python (Join-Path $PSScriptRoot 'export_tcunit_report.py') @exportArgs
        if ($LASTEXITCODE -eq 0) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'TcUnit individual result verification failed; see exporter diagnostics.' }
        Start-Sleep -Seconds 2
    } while ($true)
    $completed = $true

} finally {
    try { $vs.Close() } finally {
        try {
            [IO.File]::WriteAllBytes($plcTaskPath, $originalPlcTaskBytes)
            [IO.File]::WriteAllBytes($systemProjectPath, $originalSystemProjectBytes)
            foreach ($path in $referenceProfiles.Keys) { [IO.File]::WriteAllBytes($path, $referenceProfiles[$path]) }
            if ($completed -and -not $Development) {
                & python (Join-Path $PSScriptRoot 'build_evidence.py') finish-test --token $runToken --report $runReport --activation-build $runBuild
                if ($LASTEXITCODE -ne 0) { throw 'Test evidence failed validation after restoring the source profile.' }
            }
        } finally {
            [TcAutomation.Core.MessageFilter]::Revoke()
            $mutex.ReleaseMutex()
            $mutex.Dispose()
        }
    }
}
Write-Output ('Verified TcUnit results (Development=' + $Development + '): ' + $runReport)
