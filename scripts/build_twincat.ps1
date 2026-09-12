# Run with Windows PowerShell 5.1: powershell.exe -NoProfile -File scripts/build_twincat.ps1
# Exports the current library and builds consumers. Does not activate a runtime.
param([string]$McpRoot, [switch]$CaptureDependencies)
$ErrorActionPreference = 'Stop'
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
. (Join-Path $PSScriptRoot 'prepare_generated_tmc.ps1')
. (Join-Path $PSScriptRoot 'installed_reference_profile.ps1')
if ($PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'Use powershell.exe (Windows PowerShell 5.1) for the .NET Framework COM helper.'
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release-v2')).Path
$artifacts = Join-Path $repo 'artifacts'
if ($CaptureDependencies) {
    $artifacts = Join-Path $artifacts ('dependency-candidate-' + [Guid]::NewGuid().ToString('N'))
}
New-Item -ItemType Directory -Force $artifacts | Out-Null
[Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
Add-Type -ReferencedAssemblies @(
    (Join-Path $bin 'Interop.EnvDTE.dll'),
    (Join-Path $bin 'Interop.EnvDTE80.dll'),
    (Join-Path $bin 'Interop.TCatSysManagerLib.dll')
) -TypeDefinition @'
public static class TcForgeBuild {
    public static string DependencyCapture(object project, object references) {
        return "<TcForgeDependencyCapture>" + ((TCatSysManagerLib.ITcSmTreeItem)project).ProduceXml(false) +
            "<LibrarySignatures>" + ((TCatSysManagerLib.ITcPlcLibraryManager2)references).ProduceAllLibrarySignatures() +
            "</LibrarySignatures></TcForgeDependencyCapture>";
    }
    public static void SelectWindowsTarget(object obj) {
        var dte = (EnvDTE.DTE)obj;
        var configs = dte.Solution.SolutionBuild.SolutionConfigurations;
        for (int index = 1; index <= configs.Count; index++) {
            var cfg = (EnvDTE80.SolutionConfiguration2)configs.Item(index);
            if (cfg == null) continue;
            if (cfg.Name == "Release" && cfg.PlatformName == "TwinCAT RT (x64)") {
                cfg.Activate(); return;
            }
        }
        throw new System.Exception("Release|TwinCAT RT (x64) configuration is missing");
    }
    public static void Install(object refs, string path) {
        var manager = (TCatSysManagerLib.ITcPlcLibraryManager)refs;
        foreach (TCatSysManagerLib.ITcPlcLibRepository repo in manager.Repositories) {
            if (repo.Name == "System") { manager.InstallLibrary(repo.Name, path, true); return; }
        }
        throw new System.Exception("System library repository is missing");
    }
}
'@
$version = (Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json).xaeBaseline
if (-not $version) { throw 'toolchain.json must specify xaeBaseline' }
function Confirm-EffectiveDependencies($instance, [string]$solutionName, [string]$plcName) {
    $node = $instance.GetSystemManager().LookupTreeItem("TIPC^$plcName^$plcName Project")
    $references = $instance.GetSystemManager().LookupTreeItem("TIPC^$plcName^$plcName Project^References")
    $capture = Join-Path $artifacts ($solutionName + '-dependencies.xml')
    [IO.File]::WriteAllText($capture, [TcForgeBuild]::DependencyCapture($node, $references), [Text.UTF8Encoding]::new($false))
    if ($CaptureDependencies) {
        Write-Output "Dependency candidate capture only: $capture"
        return
    }
    & python (Join-Path $PSScriptRoot 'dependency_lock.py') check --lock (Join-Path $repo 'dependencies.lock.json') --project $solutionName --xml $capture
    if ($LASTEXITCODE -ne 0) { throw ($solutionName + ': effective dependency lock check failed') }
}
$solution = Join-Path $repo 'TwinCAT/TcForge.Library.sln'
$library = Join-Path $artifacts 'TcForge.library'
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running. Run build/activation/tests sequentially.' }
[TcAutomation.Core.MessageFilter]::Register()
$vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $version, $null)
$buildToken = Join-Path $artifacts ('build-token-' + [Guid]::NewGuid().ToString('N') + '.json')
$profiles = @{}
$completed = $false
try {
    foreach ($profile in Get-ChildItem (Join-Path $repo 'TwinCAT') -Recurse -File | Where-Object { $_.Extension -in @('.sln', '.tsproj', '.plcproj', '.TcTTO') }) {
        $profiles[$profile.FullName] = [IO.File]::ReadAllBytes($profile.FullName)
    }
    if (-not $CaptureDependencies) {
        & python (Join-Path $PSScriptRoot 'build_evidence.py') begin-build --helper-root (Resolve-Path $McpRoot).Path --output $buildToken
        if ($LASTEXITCODE -ne 0) { throw 'Could not snapshot build source/toolchain identity' }
    }
    $vs.Load()
    $vs.LoadSolution()
    [TcForgeBuild]::SelectWindowsTarget($vs.Dte)
    $effectiveVersion = $vs.EffectiveTwinCATVersion
    $check = [TcAutomation.Commands.CheckAllObjectsCommand]::ExecuteInSession($vs, 'TcForge')
    [ordered]@{ RequestedXaeVersion = $version; EffectiveXaeVersion = $effectiveVersion; Result = $check } |
        ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $artifacts 'TcForge-library-check-all.json')
    if (-not $check.Success -or $check.WarningCount -ne 0) { throw ('Library all-objects check failed or produced warnings: ' + $check.Message + ' ' + $check.ErrorMessage) }
    Confirm-EffectiveDependencies $vs 'TcForge.Library' 'TcForge'
    # Export is not a compilation gate. All three consumers below must compile successfully.
    $export = [TcAutomation.Commands.GenerateLibraryCommand]::ExecuteInSession($vs, $solution, 'TcForge', $library, $true, $false)
    if (-not $export.Success) { throw $export.ErrorMessage }
    $refs = $vs.GetSystemManager().LookupTreeItem('TIPC^TcForge^TcForge Project^References')
    [TcForgeBuild]::Install($refs, $library)
    Set-TcForgeInstalledReferences -TwinCATRoot (Join-Path $repo 'TwinCAT')
    foreach ($name in @('TcForge.Tests', 'TcForge', 'TcForge.Simulation')) {
        $profileName = if ($name -eq 'TcForge') { 'TcForge.Example' } else { $name }
        $solution = Join-Path $repo ('TwinCAT/' + $profileName + '.sln')
        $vs.Close()
        $vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $version, $null)
        $vs.Load()
        Move-TcForgeGeneratedTmc -Repo $repo -ProjectFile ([TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($solution))
        $vs.LoadSolution()
        [TcForgeBuild]::SelectWindowsTarget($vs.Dte)
        $effectiveVersion = $vs.EffectiveTwinCATVersion
        $result = [TcAutomation.Commands.BuildCommand]::ExecuteInSession($vs, $true)
        $result | Add-Member -NotePropertyName RequestedXaeVersion -NotePropertyValue $version
        $result | Add-Member -NotePropertyName EffectiveXaeVersion -NotePropertyValue $effectiveVersion
        $result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $artifacts ($name + '-build.json'))
        Write-Output $result.BuildOutput
        if (-not $result.Success -or $result.WarningCount -ne 0) { throw ($name + ': build failed or produced warnings: ' + $result.Summary + ' ' + $result.ErrorMessage) }
        $plcName = @{ 'TcForge.Tests' = 'Testing'; 'TcForge' = 'TcForgeExample'; 'TcForge.Simulation' = 'Simulation' }[$name]
        Confirm-EffectiveDependencies $vs $name $plcName
    }
    Get-FileHash $library -Algorithm SHA256 | Format-List
    $completed = $true
} finally {
    try { $vs.Close() } finally {
        try {
            # XAE can rewrite profile metadata. Restore exact offline bytes before
            # source-bound evidence is finalized; no activation occurs in this script.
            foreach ($profilePath in $profiles.Keys) { [IO.File]::WriteAllBytes($profilePath, $profiles[$profilePath]) }
            if ($completed -and -not $CaptureDependencies) {
                & python (Join-Path $PSScriptRoot 'build_evidence.py') finish-build --token $buildToken --library $library --dependencies (Join-Path $repo 'dependencies.lock.json') --output (Join-Path $artifacts 'build-evidence.json')
                if ($LASTEXITCODE -ne 0) { throw 'Build completed but source/artifact evidence validation failed' }
            }
        } finally {
            [TcAutomation.Core.MessageFilter]::Revoke()
            $mutex.ReleaseMutex()
            $mutex.Dispose()
        }
    }
}
