# Explicit artifact qualification only. Callers must restore original profile bytes
# after XAE closes, or operate on a disposable consumer copy.
function Set-TcForgeInstalledReferences {
    param([Parameter(Mandatory=$true)][string]$TwinCATRoot)
    foreach ($relative in @('Testing.plcproj','Simulation.plcproj','TcForgeExample/TcForgeExample.plcproj','TcForgeReference.plcproj')) {
        $path = Join-Path $TwinCATRoot $relative
        $text = [IO.File]::ReadAllText($path)
        $pattern = '(?s)(<PlaceholderReference Include="TcForge">\s*<DefaultResolution>)\[TcForge\](, [^<]+</DefaultResolution>)'
        if ([regex]::Matches($text, $pattern).Count -ne 1) { throw "Expected one TcForge source reference in $path" }
        [IO.File]::WriteAllText($path, [regex]::Replace($text, $pattern, '${1}TcForge${2}'), [Text.UTF8Encoding]::new($false))
    }
}
