# Builds the combined source-reference workspace. Never exports, installs or activates.
param([string]$McpRoot, [string]$WorkspaceRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
. (Join-Path $PSScriptRoot 'prepare_generated_tmc.ps1')
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1.' }
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
$repo = if ($WorkspaceRoot) { (Resolve-Path $WorkspaceRoot).Path } else { (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release-v2')).Path
$output = Join-Path $repo ('artifacts/development-build-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $output | Out-Null
$baseline = Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json
[Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
Add-Type -ReferencedAssemblies @((Join-Path $bin 'Interop.EnvDTE.dll'), (Join-Path $bin 'Interop.EnvDTE80.dll'), (Join-Path $bin 'Interop.TCatSysManagerLib.dll')) -TypeDefinition @'
public static class TcForgeDevelopment {
    public static void SelectPlatform(object value) {
        var configs = ((EnvDTE.DTE)value).Solution.SolutionBuild.SolutionConfigurations;
        for (int i = 1; i <= configs.Count; i++) {
            var cfg = (EnvDTE80.SolutionConfiguration2)configs.Item(i);
            if (cfg.Name == "Release" && cfg.PlatformName == "TwinCAT RT (x64)") { cfg.Activate(); return; }
        }
        throw new System.Exception("Release|TwinCAT RT (x64) is missing.");
    }
    public static void Bind(object reference, string task) {
        ((TCatSysManagerLib.ITcPlcTaskReference)reference).LinkedTask = "TIRT^" + task;
    }
}
'@
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running.' }
[TcAutomation.Core.MessageFilter]::Register()
$solution = Join-Path $repo 'TwinCAT/TcForge.sln'
$vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $baseline.xaeBaseline, $null)
$profiles = @{}
try {
    foreach ($file in Get-ChildItem (Join-Path $repo 'TwinCAT') -Recurse -File | Where-Object { $_.Extension -in @('.sln','.tsproj','.plcproj','.TcTTO','.TcPOU','.TcDUT','.TcIO','.TcGVL') }) {
        $profiles[$file.FullName] = [IO.File]::ReadAllBytes($file.FullName)
    }
    $vs.Load()
    Move-TcForgeGeneratedTmc -Repo $repo -ProjectFile (Join-Path $repo 'TwinCAT/TcForge.tsproj')
    $vs.LoadSolution()
    [TcForgeDevelopment]::SelectPlatform($vs.Dte)
    $sm = $vs.GetSystemManager()
    foreach ($entry in @(
        @('TcForgeExample','PlcTask','PlcTask'),
        @('Testing','Testing^Testing','Testing'),
        @('Simulation','Simulation^Simulation','Simulation'),
        @('Simulation','Simulation^OwnershipWitness','OwnershipWitness'))) {
        [TcForgeDevelopment]::Bind($sm.LookupTreeItem(('TIPC^{0}^{0} Project^{1}' -f $entry[0],$entry[1])), $entry[2])
    }
    foreach ($plc in @('TcForgeExample','Testing','Simulation')) {
        [IO.File]::WriteAllText((Join-Path $output ($plc + '-loaded.xml')), $sm.LookupTreeItem("TIPC^$plc^$plc Project").ProduceXml($false))
    }
    $check = [TcAutomation.Commands.CheckAllObjectsCommand]::ExecuteInSession($vs, 'TcForge')
    $check | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $output 'library-check.json')
    if (-not $check.Success -or $check.WarningCount -ne 0) { throw 'Library all-objects check failed.' }
    $build = [TcAutomation.Commands.BuildCommand]::ExecuteInSession($vs, $true)
    $build | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $output 'build.json')
    foreach ($plcFile in @('Testing.plcproj','Simulation.plcproj','TcForgeExample/TcForgeExample.plcproj')) {
        Copy-Item -LiteralPath (Join-Path $repo ('TwinCAT/' + $plcFile)) -Destination (Join-Path $output ([IO.Path]::GetFileName($plcFile)))
    }
    if (-not $build.Success -or $build.WarningCount -ne 0) { throw ($build.Summary + ' ' + $build.BuildOutput) }
    foreach ($plc in @('TcForgeExample','Testing','Simulation')) {
        $xml = $sm.LookupTreeItem("TIPC^$plc^$plc Project").ProduceXml($false)
        [IO.File]::WriteAllText((Join-Path $output ($plc + '-references.xml')), $xml)
        [xml]$doc = $xml
        $libraries = if ($plc -eq 'TcForgeExample') { @('TcForge') } else { @('TcForge','TcForgeExample') }
        foreach ($library in $libraries) {
            $reference = @($doc.SelectNodes("//IECProjectDef/References/PlaceholderReference[PlaceholderName='$library']"))
            if ($reference.Count -ne 1) { throw "$plc must resolve exactly one $library reference." }
            # Bracketed names are TwinCAT's project-library identity, not an installed artifact.
            if ([string]$reference[0].EffectiveResolution.LibraryName -ne "[$library]") {
                throw "$plc did not resolve the $library source project. Inspect the captured reference."
            }
        }
    }
    Write-Output "Verified combined source-reference build: $output"
} finally {
    try { $vs.Close() } finally {
        try { foreach ($path in $profiles.Keys) { [IO.File]::WriteAllBytes($path, $profiles[$path]) } }
        finally { [TcAutomation.Core.MessageFilter]::Revoke(); $mutex.ReleaseMutex(); $mutex.Dispose() }
    }
}
