# Qualifies fresh TcForge consumption on the existing engineering installation.
# No activation, System-library replacement, repository-file deletion, or OS setup.
param(
    [Parameter(Mandatory = $true)][string]$Library,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$McpRoot
)
$ErrorActionPreference = 'Stop'
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
. (Join-Path $PSScriptRoot 'initialize_twincat_environment.ps1')
if ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Use Windows PowerShell 5.1.' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$artifact = (Resolve-Path -LiteralPath $Library).Path
$artifactHash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
$destination = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $destination) { throw 'Output must be a new directory; previous evidence is never overwritten.' }
if ($destination.StartsWith((Join-Path $repo 'TwinCAT') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be outside the TwinCAT source tree.' }
$bin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release')).Path
$baseline = Get-Content (Join-Path $repo 'toolchain.json') -Raw | ConvertFrom-Json
[Reflection.Assembly]::LoadFrom((Join-Path $bin 'TcAutomation.exe')) | Out-Null
Add-Type -ReferencedAssemblies @((Join-Path $bin 'Interop.EnvDTE.dll'), (Join-Path $bin 'Interop.EnvDTE80.dll'), (Join-Path $bin 'Interop.TCatSysManagerLib.dll')) -TypeDefinition @'
using System.Collections.Generic;
using TCatSysManagerLib;
public class TcForgeRepositoryEntry { public string Name; public string Folder; public int Index; }
public static class TcForgeCleanInstall {
    public static TcForgeRepositoryEntry[] Repositories(object value) {
        var result = new List<TcForgeRepositoryEntry>();
        foreach (ITcPlcLibRepository repo in ((ITcPlcLibraryManager)value).Repositories)
            result.Add(new TcForgeRepositoryEntry { Name=repo.Name, Folder=repo.Folder, Index=result.Count });
        return result.ToArray();
    }
    public static void Insert(object value, string name, string root) { ((ITcPlcLibraryManager)value).InsertRepository(name, root, 0); }
    public static void Install(object value, string name, string library) { ((ITcPlcLibraryManager)value).InstallLibrary(name, library, false); }
    public static void Remove(object value, string name) { ((ITcPlcLibraryManager)value).RemoveRepository(name); }
    public static string Capture(object project, object references) {
        return "<TcForgeDependencyCapture>" + ((ITcSmTreeItem)project).ProduceXml(false) + "<LibrarySignatures>" +
            ((ITcPlcLibraryManager2)references).ProduceAllLibrarySignatures() + "</LibrarySignatures></TcForgeDependencyCapture>";
    }
    public static void SelectPlatform(object value) {
        var configs = ((EnvDTE.DTE)value).Solution.SolutionBuild.SolutionConfigurations;
        for (int i=1; i<=configs.Count; i++) {
            var cfg=(EnvDTE80.SolutionConfiguration2)configs.Item(i);
            if (cfg == null) continue;
            if (cfg.Name=="Release" && cfg.PlatformName=="TwinCAT RT (x64)") { cfg.Activate(); return; }
        }
        throw new System.Exception("Release|TwinCAT RT (x64) is missing.");
    }
}
'@
function Write-Record([string]$name, $value) {
    $value | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 (Join-Path $destination $name)
}
function Open-Consumer([string]$name) {
    $script:activePlc = $projects[$name]
    $script:vs = [TcAutomation.Core.VisualStudioInstance]::new((Join-Path $copyRoot ($name + '.sln')), $baseline.xaeBaseline, $null)
    $script:vs.Load(); $script:vs.LoadSolution()
    [TcForgeCleanInstall]::SelectPlatform($script:vs.Dte)
    if ($script:vs.EffectiveTwinCATVersion -ne $baseline.xaeBaseline) { throw 'Unexpected engineering version.' }
}
function Get-References([string]$plc) { return ,$script:vs.GetSystemManager().LookupTreeItem("TIPC^$plc^$plc Project^References") }
function System-TcForgeHashes([string]$systemRoot) {
    $files = [ordered]@{}
    $folder = Join-Path $systemRoot 'Home/TcForge'
    if (Test-Path -LiteralPath $folder) {
        foreach ($file in Get-ChildItem -LiteralPath $folder -Recurse -File | Sort-Object FullName) {
            $files[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        }
    }
    return $files
}
function Confirm-InstalledArtifact([string]$name, [string]$plc, [string]$stage) {
    $node = $script:vs.GetSystemManager().LookupTreeItem("TIPC^$plc^$plc Project")
    $refs = Get-References $plc
    $capture = [TcForgeCleanInstall]::Capture($node, $refs)
    $captureFile = Join-Path $destination ($name + '-' + $stage + '-dependencies.xml')
    [IO.File]::WriteAllText($captureFile, $capture, [Text.UTF8Encoding]::new($false))
    [xml]$xml = $capture
    $reference = @($xml.SelectNodes("//IECProjectDef/References/PlaceholderReference[PlaceholderName='TcForge']"))
    if ($reference.Count -ne 1) { throw 'Exactly one resolved TcForge placeholder is required.' }
    $resolved = [string]$reference[0].RelativePath
    if (-not [IO.Path]::IsPathRooted($resolved)) { throw 'XAE did not expose an absolute resolved library path.' }
    $resolved = [IO.Path]::GetFullPath($resolved)
    $prefix = $repositoryRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw ('Consumer resolved TcForge outside the fresh repository: ' + $resolved) }
    $resolvedHash = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash
    if ($resolvedHash -ne $artifactHash) { throw 'Resolved TcForge bytes differ from the requested artifact.' }
    & python (Join-Path $PSScriptRoot 'dependency_lock.py') check --lock (Join-Path $repo 'dependencies.lock.json') --project $name --xml $captureFile
    if ($LASTEXITCODE -ne 0) { throw 'Effective dependency lock mismatch.' }
    Write-Record ($name + '-' + $stage + '-resolution.json') ([ordered]@{ Path=$resolved; Sha256=$resolvedHash; EffectiveXaeVersion=$script:vs.EffectiveTwinCATVersion })
}
$mutex = [Threading.Mutex]::new($false, 'Local\TcForge.Xae')
$acquired = $false
try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { $mutex.Dispose(); throw 'Another TcForge XAE operation is running.' }
$vs = $null; $registrationAttempted = $false; $failure = $null; $cleanupFailure = $null
$repositoryName = 'TcForge-Qualification-' + [Guid]::NewGuid().ToString('N')
$repositoryRoot = Join-Path $destination 'repository'
$copyRoot = Join-Path $destination 'consumer/TwinCAT'
$projects = [ordered]@{ 'TcForge.Tests'='Testing'; 'TcForge'='TcForgeExample'; 'TcForge.Simulation'='Simulation' }
[TcAutomation.Core.MessageFilter]::Register()
try {
    New-Item -ItemType Directory -Path $repositoryRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $copyRoot -Force | Out-Null
    # Copy source/configuration only, including uncommitted new objects. Compiler
    # products, user settings and caches cannot seed the fresh consumer build.
    $sourceRoot = Join-Path $repo 'TwinCAT'
    $extensions = @('.tcpou','.tcdut','.tcgvl','.tcio','.tctto','.plcproj','.tsproj','.sln','.xti','.tclibcat','.tcvis','.tctxt','.tcgtlo','.tcvmo')
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -in $extensions }) {
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\','/')
        $target = Join-Path $copyRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target
    }
    Open-Consumer 'TcForge.Simulation'
    $refs = Get-References 'Simulation'
    $originalRepositories = @([TcForgeCleanInstall]::Repositories($refs))
    $originalJson = ConvertTo-Json -InputObject $originalRepositories -Depth 10 -Compress
    $system = @($originalRepositories | Where-Object Name -eq 'System')
    if ($system.Count -ne 1) { throw 'Exactly one existing System repository is required.' }
    $systemBefore = System-TcForgeHashes $system[0].Folder
    Write-Record 'repositories-before.json' $originalRepositories
    Write-Record 'system-tcforge-before.json' $systemBefore
    Write-Record 'recovery.json' ([ordered]@{ RepositoryName=$repositoryName; RepositoryRoot=$repositoryRoot; Library=$artifact; Sha256=$artifactHash; Scope='Fresh TcForge consumption on existing engineering installation' })
    if (@($originalRepositories | Where-Object Name -eq $repositoryName).Count) { throw 'Temporary repository name collision.' }
    $registrationAttempted = $true
    [TcForgeCleanInstall]::Insert($refs, $repositoryName, $repositoryRoot)
    $inserted = @([TcForgeCleanInstall]::Repositories($refs))
    if ($inserted[0].Name -ne $repositoryName -or [IO.Path]::GetFullPath($inserted[0].Folder).TrimEnd('\','/') -ne $repositoryRoot.TrimEnd('\','/')) { throw 'Temporary repository was not registered first at the requested path.' }
    [TcForgeCleanInstall]::Install($refs, $repositoryName, $artifact)
    $vs.Close(); $vs = $null
    foreach ($entry in $projects.GetEnumerator()) {
        Open-Consumer $entry.Key
        Confirm-InstalledArtifact $entry.Key $entry.Value 'before-build'
        $result = [TcAutomation.Commands.BuildCommand]::ExecuteInSession($vs, $true)
        Write-Record ($entry.Key + '-build.json') ([ordered]@{ RequestedXaeVersion=$baseline.xaeBaseline; EffectiveXaeVersion=$vs.EffectiveTwinCATVersion; Result=$result })
        if (-not $result.Success -or $result.ErrorCount -ne 0 -or $result.WarningCount -ne 0) { throw ('Fresh consumer build failed or warned: ' + $entry.Key) }
        Confirm-InstalledArtifact $entry.Key $entry.Value 'after-build'
        $vs.Close(); $vs = $null
    }
    if ((Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash -ne $artifactHash) { throw 'Requested artifact changed during qualification.' }
} catch { $failure = $_ } finally {
    try {
        if ($registrationAttempted) {
            if (-not $vs -or -not $vs.IsSolutionLoaded) { if ($vs) { $vs.Close() }; Open-Consumer 'TcForge.Simulation' }
            $refs = Get-References $script:activePlc
            $temporary = @([TcForgeCleanInstall]::Repositories($refs) | Where-Object Name -eq $repositoryName)
            if ($temporary.Count -eq 1) {
                if ([IO.Path]::GetFullPath($temporary[0].Folder).TrimEnd('\','/') -ne $repositoryRoot.TrimEnd('\','/')) { throw 'Refusing to remove a repository whose path changed.' }
                [TcForgeCleanInstall]::Remove($refs, $repositoryName)
            }
            $restored = @([TcForgeCleanInstall]::Repositories($refs))
            Write-Record 'repositories-after.json' $restored
            if ((ConvertTo-Json -InputObject $restored -Depth 10 -Compress) -ne $originalJson) { throw 'Repository configuration differs after removal; see recovery.json.' }
            $systemAfter = System-TcForgeHashes $system[0].Folder
            Write-Record 'system-tcforge-after.json' $systemAfter
            if ((ConvertTo-Json $systemBefore -Compress) -ne (ConvertTo-Json $systemAfter -Compress)) { throw 'Existing System TcForge files changed during qualification.' }
        }
    } catch { $cleanupFailure = $_ } finally {
        try { if ($vs) { $vs.Close() } } finally { [TcAutomation.Core.MessageFilter]::Revoke(); $mutex.ReleaseMutex(); $mutex.Dispose() }
    }
}
if ($failure -or $cleanupFailure) {
    Write-Record 'result.json' ([ordered]@{ Success=$false; Error=[string]$failure; CleanupError=[string]$cleanupFailure })
    throw ('Fresh-consumer qualification failed: ' + $failure + ' Cleanup: ' + $cleanupFailure)
}
Write-Record 'result.json' ([ordered]@{ Success=$true; Library=$artifact; Sha256=$artifactHash; Repository=$repositoryRoot; Consumers=@($projects.Keys); RepositoryConfigurationRestored=$true; SystemTcForgeUnchanged=$true; Scope='Fresh TcForge consumption on existing engineering installation; no clean-OS qualification' })
Write-Output 'Fresh TcForge installation and all three consumer builds passed; temporary registration removed and evidence retained.'
