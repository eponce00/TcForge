# Process-local native DLL search paths. Long-running hosts may predate installation
# and therefore inherit an older PATH even when the machine PATH is already correct.
$tcForgeCommonRoot = Join-Path ${env:ProgramFiles(x86)} 'Beckhoff/TwinCAT'
$tcForgeCommon64 = Join-Path $tcForgeCommonRoot 'Common64'
$tcForgeCommon32 = Join-Path $tcForgeCommonRoot 'Common32'
if (-not (Test-Path -LiteralPath (Join-Path $tcForgeCommon64 'TcAmsServer.dll'))) {
    throw 'TwinCAT Common64/TcAmsServer.dll is missing. Install the TwinCAT ADS/engineering components.'
}
$env:PATH = $tcForgeCommon64 + ';' + $tcForgeCommon32 + ';' + $env:PATH
