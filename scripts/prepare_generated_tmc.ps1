# Retire only ignored PLC-generated symbol files before opening an offline XAE
# project. Keep every compile-info file: those are required for online changes.
function Move-TcForgeGeneratedTmc {
    param([Parameter(Mandatory=$true)][string]$Repo,
          [Parameter(Mandatory=$true)][string]$ProjectFile)
    $root = [IO.Path]::GetFullPath($Repo).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $project = [IO.Path]::GetFullPath($ProjectFile)
    if (-not $project.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Project is outside repository' }
    [xml]$xml = Get-Content -LiteralPath $project -Raw
    foreach ($node in $xml.SelectNodes('//*[@TmcFilePath]')) {
        $path = [IO.Path]::GetFullPath((Join-Path (Split-Path $project) $node.TmcFilePath))
        if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($path) -ne '.tmc') {
            throw 'Generated TMC path escapes the repository or has an unexpected extension'
        }
        if (-not (Test-Path -LiteralPath $path)) { continue }
        & git -C $Repo check-ignore --quiet -- $path
        if ($LASTEXITCODE -ne 0) { throw "Refusing to retire a non-ignored TMC: $path" }
        [xml]$tmc = Get-Content -LiteralPath $path -Raw
        if ($tmc.TcModuleClass.GeneratedBy -ne 'TwinCAT XAE Plc') { throw "TMC is not PLC-generated: $path" }
        $backup = Join-Path $root ('artifacts/generated-tmc-' + [Guid]::NewGuid().ToString('N') + '-' + [IO.Path]::GetFileName($path))
        Move-Item -LiteralPath $path -Destination $backup
        Write-Output "Retained generated symbols at $backup; compiler login information preserved."
    }
}
