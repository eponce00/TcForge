# Execute on the Windows bench through authenticated SSH, using its local router.
param([Parameter(Mandatory=$true)][string]$ExpectedNetId)
$ErrorActionPreference='Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class LocalTcConfig {
    [StructLayout(LayoutKind.Sequential, Pack=1)]
    public struct Address {
        [MarshalAs(UnmanagedType.ByValArray, SizeConst=6)] public byte[] NetId;
        public ushort Port;
    }
    const string Dll=@"C:\TwinCAT\Common64\TcAdsDll.dll";
    [DllImport(Dll)] public static extern int AdsPortOpenEx();
    [DllImport(Dll)] public static extern int AdsPortCloseEx(int port);
    [DllImport(Dll)] public static extern int AdsGetLocalAddressEx(int port, out Address address);
    [DllImport(Dll)] public static extern int AdsSyncSetTimeoutEx(int port, uint timeout);
    [DllImport(Dll)] public static extern int AdsSyncReadStateReqEx(int port, ref Address address, out ushort state, out ushort device);
    [DllImport(Dll)] public static extern int AdsSyncWriteControlReqEx(int port, ref Address address, ushort state, ushort device, uint length, IntPtr data);
}
'@
$port=[LocalTcConfig]::AdsPortOpenEx()
if ($port -le 0) {throw 'Local ADS port unavailable'}
try {
    [LocalTcConfig+Address]$address=New-Object LocalTcConfig+Address
    $code=[LocalTcConfig]::AdsGetLocalAddressEx($port,[ref]$address)
    if ($code -ne 0) {throw "Local address error $code"}
    $netId=$address.NetId -join '.'
    if ($netId -ne $ExpectedNetId) {throw 'Local AMS identity does not match the requested bench'}
    $address.Port=10000
    $null=[LocalTcConfig]::AdsSyncSetTimeoutEx($port,2000)
    [UInt16]$state=0; [UInt16]$device=0
    $code=[LocalTcConfig]::AdsSyncReadStateReqEx($port,[ref]$address,[ref]$state,[ref]$device)
    $initialDeadline=[DateTime]::UtcNow.AddSeconds(120)
    while ($code -ne 0) {
        if ([DateTime]::UtcNow -ge $initialDeadline) {throw "Local read-state error $code"}
        Start-Sleep -Milliseconds 500
        $null=[LocalTcConfig]::AdsPortCloseEx($port)
        $port=[LocalTcConfig]::AdsPortOpenEx()
        if ($port -le 0) {continue}
        $null=[LocalTcConfig]::AdsSyncSetTimeoutEx($port,2000)
        $code=[LocalTcConfig]::AdsSyncReadStateReqEx($port,[ref]$address,[ref]$state,[ref]$device)
    }
    $before=$state
    $dispatch=0
    if ($state -ne 15) {
        $dispatch=[LocalTcConfig]::AdsSyncWriteControlReqEx($port,[ref]$address,16,$device,0,[IntPtr]::Zero)
    }
    $deadline=[DateTime]::UtcNow.AddSeconds(180)
    do {
        # Re-register during the transition; a disabled system port is not
        # evidence that CONFIG is ready for file changes.
        if ($port -gt 0) { $null=[LocalTcConfig]::AdsPortCloseEx($port) }
        $port=[LocalTcConfig]::AdsPortOpenEx()
        if ($port -le 0) {
            if ([DateTime]::UtcNow -ge $deadline) {throw 'Local ADS router did not accept a new client'}
            Start-Sleep -Milliseconds 200
            continue
        }
        $null=[LocalTcConfig]::AdsSyncSetTimeoutEx($port,2000)
        $code=[LocalTcConfig]::AdsSyncReadStateReqEx($port,[ref]$address,[ref]$state,[ref]$device)
        if ($code -eq 0 -and $state -eq 15) {break}
        if ([DateTime]::UtcNow -ge $deadline) {throw "Local CONFIG not observed; ADS error $code"}
        Start-Sleep -Milliseconds 200
    } while ($true)
    @{netId=$netId;before=$before;after=$state;dispatchError=$dispatch;verified=$true} | ConvertTo-Json -Compress
} finally {
    if ($port -gt 0) { $null=[LocalTcConfig]::AdsPortCloseEx($port) }
}
