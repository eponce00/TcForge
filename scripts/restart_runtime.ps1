# Restart only: no build, activation, download or boot-project generation.
# Readiness is independently checked by wait_runtime_ready.py.
param(
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Solution,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$McpRoot
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1' }
if (Test-Path -LiteralPath $Output) { throw 'Use a new output path' }
$Output=[IO.Path]::GetFullPath($Output)
if (-not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($Output))) { throw 'Output parent directory must exist' }
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
$Solution = (Resolve-Path -LiteralPath $Solution).Path
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release')).Path
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
$registered = $false
$vs = $null
$profiles = @{}
$result = @{ Dispatched=$false; RuntimeVerified=$false; Target=$Target; Operation='StartRestartTwinCAT' }
try {
    try { $acquired=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired=$true }
    if (-not $acquired) { throw 'Another TcForge XAE operation is running' }
    [Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
    [TcAutomation.Core.MessageFilter]::Register()
    $registered=$true
    foreach ($file in Get-ChildItem (Split-Path $Solution) -Recurse -File | Where-Object { $_.Extension -in @('.sln','.tsproj','.plcproj','.TcTTO') }) {
        $profiles[$file.FullName]=[IO.File]::ReadAllBytes($file.FullName)
    }
    $project=[TcAutomation.Core.TcFileUtilities]::FindTwinCATProjectFile($Solution)
    $version=[TcAutomation.Core.TcFileUtilities]::GetTcVersion($project)
    $vs=[TcAutomation.Core.VisualStudioInstance]::new($Solution,$version,$null)
    $vs.Load()
    $vs.LoadSolution()
    $sm=$vs.GetSystemManager()
    $sm.SetTargetNetId($Target)
    $sm.StartRestartTwinCAT()
    $result.Dispatched=$true
} catch {
    $result.Error=$_.Exception.GetType().Name
    throw
} finally {
    try { if ($null -ne $vs) { $vs.Close() } } finally {
        foreach ($path in $profiles.Keys) { [IO.File]::WriteAllBytes($path,$profiles[$path]) }
        if ($registered) { [TcAutomation.Core.MessageFilter]::Revoke() }
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
        $result | ConvertTo-Json | Set-Content -LiteralPath $Output -Encoding UTF8
    }
}
