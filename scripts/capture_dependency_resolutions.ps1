# Read-only engineering capture; does not build, activate, or update the dependency lock.
param([string]$McpRoot = (Join-Path $PSScriptRoot '../../twincat-mcp'))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
. (Join-Path $PSScriptRoot 'installed_reference_profile.ps1')
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release-v2')).Path
[Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
Add-Type -ReferencedAssemblies (Join-Path $bin 'Interop.TCatSysManagerLib.dll') -TypeDefinition @'
public static class TcForgeDependencyCapture {
    public static string Signatures(object references) {
        return ((TCatSysManagerLib.ITcPlcLibraryManager2)references).ProduceAllLibrarySignatures();
    }
}
'@
$version = (Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json).xaeBaseline
$destination = Join-Path $repo 'artifacts/dependency-capture'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$projects = [ordered]@{ 'TcForge.Library' = 'TcForge'; 'TcForge.Tests' = 'Testing'; 'TcForge' = 'TcForgeExample'; 'TcForge.Simulation' = 'Simulation' }
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running.' }
$vs = $null
$profiles = @{}
[TcAutomation.Core.MessageFilter]::Register()
try {
    foreach ($file in Get-ChildItem (Join-Path $repo 'TwinCAT') -Recurse -File | Where-Object { $_.Extension -in @('.sln','.tsproj','.plcproj','.TcTTO') }) {
        $profiles[$file.FullName] = [IO.File]::ReadAllBytes($file.FullName)
    }
    Set-TcForgeInstalledReferences -TwinCATRoot (Join-Path $repo 'TwinCAT')
    foreach ($entry in $projects.GetEnumerator()) {
        $profile = if ($entry.Key -eq 'TcForge') { 'TcForge.Example' } else { $entry.Key }
        $solution = Join-Path $repo ('TwinCAT/' + $profile + '.sln')
        $vs = [TcAutomation.Core.VisualStudioInstance]::new($solution, $version, $null)
        $vs.Load(); $vs.LoadSolution()
        $effective = $vs.EffectiveTwinCATVersion
        $plc = $entry.Value
        $node = $vs.GetSystemManager().LookupTreeItem("TIPC^$plc^$plc Project")
        [IO.File]::WriteAllText((Join-Path $destination ($entry.Key + '.xml')), $node.ProduceXml($false), [Text.UTF8Encoding]::new($false))
        $refs = $vs.GetSystemManager().LookupTreeItem("TIPC^$plc^$plc Project^References")
        [IO.File]::WriteAllText((Join-Path $destination ($entry.Key + '-signatures.xml')), [TcForgeDependencyCapture]::Signatures($refs), [Text.UTF8Encoding]::new($false))
        & python (Join-Path $PSScriptRoot 'dependency_lock.py') combine --xml (Join-Path $destination ($entry.Key + '.xml')) --signatures (Join-Path $destination ($entry.Key + '-signatures.xml')) --output (Join-Path $destination ($entry.Key + '.xml'))
        if ($LASTEXITCODE -ne 0) { throw 'Failed to combine actual dependency capture' }
        Write-Output ($entry.Key + ': captured references under XAE ' + $effective)
        $vs.Close(); $vs = $null
    }
} finally {
    try { if ($vs) { $vs.Close() } } finally {
        try { foreach ($path in $profiles.Keys) { [IO.File]::WriteAllBytes($path, $profiles[$path]) } }
        finally {
            [TcAutomation.Core.MessageFilter]::Revoke()
            $mutex.ReleaseMutex(); $mutex.Dispose()
        }
    }
}
