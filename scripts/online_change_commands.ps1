# Reusable operations for an existing, exclusively owned XAE engineering session.
# Caller selects the PLC context, preserves compile information and verifies the
# runtime outcome. These functions never log in, download, activate or restart.
function Get-TcForgeOnlineChangeCommand {
    param([Parameter(Mandatory=$true)]$Dte,
          [Parameter(Mandatory=$true)]$Plc)
    [xml]$status = $Plc.ProduceXml($false)
    if ($status.TreeItem.IECProjectDef.OnlineSettings.LoggedIn -ne 'true') {
        throw 'Online Change requires an already logged-in, matching PLC project.'
    }
    foreach ($name in @('PLC.OnlineChangenone', 'OtherContextMenus.Plc2Projects.OnlineChange')) {
        try { $command = $Dte.Commands.Item($name) } catch { continue }
        if ($command.IsAvailable) { return $name }
    }
    throw 'Online Change unavailable. Preserve compile information and check the selected PLC; no download fallback is permitted.'
}

function Invoke-TcForgeOnlineChange {
    param([Parameter(Mandatory=$true)]$Dte,
          [Parameter(Mandatory=$true)]$Plc,
          [Parameter(Mandatory=$true)][string]$ExpectedCommand)
    $command = Get-TcForgeOnlineChangeCommand -Dte $Dte -Plc $Plc
    if ($command -ne $ExpectedCommand) { throw 'Online Change command context changed after preflight.' }
    $Dte.ExecuteCommand($command, '')
    # Command return is not evidence that the runtime applied the delta. A modal,
    # rejection or no-op must not become a successful qualification result.
    return @{ Operation = 'OnlineChange'; Command = $command; Dispatched = $true; RuntimeVerified = $false }
}
