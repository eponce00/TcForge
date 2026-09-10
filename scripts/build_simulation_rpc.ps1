param([string]$McpRoot)
$ErrorActionPreference = 'Stop'
if (-not $McpRoot) { $McpRoot = Join-Path $PSScriptRoot '../../twincat-mcp' }
$rpcBin = (Resolve-Path (Join-Path $McpRoot 'TcAutomation/bin/Release')).Path
$output = Join-Path $PSScriptRoot '../artifacts/simulation-rpc'
New-Item -ItemType Directory -Force $output | Out-Null
$refs = @(Get-ChildItem -LiteralPath $rpcBin -Filter '*.dll' | ForEach-Object {
    try {
        [Reflection.AssemblyName]::GetAssemblyName($_.FullName) | Out-Null
        '/reference:' + $_.FullName
    } catch { }
})
$refs += '/reference:C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.7.2\Facades\netstandard.dll'
$refs += '/reference:System.Web.Extensions.dll'
$compiler = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\Roslyn\csc.exe'
$executable = Join-Path $output 'SimulationRpc.exe'
& $compiler /nologo /target:exe /platform:x64 "/out:$executable" @refs (Join-Path $PSScriptRoot 'simulation_rpc.cs')
if ($LASTEXITCODE -ne 0) { throw 'Simulation RPC transport compilation failed' }
Get-ChildItem -LiteralPath $rpcBin -Filter '*.dll' | Copy-Item -Destination $output -Force
Copy-Item -LiteralPath (Join-Path $rpcBin 'TcAutomation.exe.config') -Destination "$executable.config" -Force
Write-Output $executable
