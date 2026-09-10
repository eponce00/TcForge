# OPC UA qualification

OPC UA's TCP endpoint and its ADS backend are different addresses. The bench
endpoint is `opc.tcp://192.168.1.224:4840`. Example uses ADS 851, Testing 853,
and Simulation 854. Activating one solution does not start the other solutions.
Browse success alone is insufficient: stale TMC symbols can remain visible while
the backend reports `Target port not found`. Check device error, PLC RUN, and a
nonzero cyclic owner before testing methods.

## Server configuration

Use filtered TMC import (AutoCfg 4041), the actual runtime's ADS port and its
`[BootDir]/Plc/Port_<port>.tmc`. Use a separate named device per runtime.
Keep SignAndEncrypt enabled, use Basic256Sha256 or a supported stronger policy,
and explicitly trust each client certificate. Disable
`AutomaticallyTrustAllClientCertificates`. Pin the server certificate obtained
through an independently authenticated channel. Client private keys stay on the
client. Certificate replacement requires renewing the corresponding trust entry.

The bench explicitly trusts the development PC's UAExpert and qualification
certificates. A replacement PC needs its own trusted certificate as well as a
valid user account. Administrator uses OS authentication and the same credential
as Windows/SSH. Store recovery credentials in the company password manager;
the developer's local DPAPI copy is not a portable recovery backup.

Use OS-authenticated users and namespace/node permissions for deployed clients.
Do not use Administrator for an ordinary HMI. A read-only user must not inherit
the default Users group's PLC write rights. Read/browse access is `0x0000000B`;
grant method execution only on the intended Operator methods, using node-level
AccessInfos. Configuration and raw output writes must remain inaccessible.
The exact commissioned roles depend on the application; the bench's temporary
read-only qualification account is removed after testing.

## Repeatable runner

Install `python -m pip install -e "./python[opcua]"`. The runner requires an
existing ADS route and a trusted certificate/private key. Passwords come from
environment variables, never command-line values or report files. For the current
Windows bench, retrieve the local encrypted credential into the process environment:

```powershell
$env:TCFORGE_OPCUA_PASSWORD = (Import-Clixml -LiteralPath "$env:LOCALAPPDATA/TcForge/bench/192.168.1.224-Administrator.credential.xml").GetNetworkCredential().Password
$certDir = "$env:LOCALAPPDATA/TcForge/bench/opcua"
try {
    artifacts/sim-venv/Scripts/python.exe scripts/verify_opcua.py `
      --endpoint opc.tcp://192.168.1.224:4840 --target 172.18.236.100.1.1 `
      --port 851 --fixture Example --namespace urn:BeckhoffAutomation:Ua:PLC1 `
      --certificate "$certDir/client.der" --key "$certDir/client.pem" `
      --server-certificate "$certDir/server.der" `
      --application-uri urn:tcforge:bench:qualification --user Administrator `
      --ads-dll-directory 'C:/Program Files (x86)/Beckhoff/TwinCAT/Common64' `
      --clients 16 --output artifacts/opcua-example-new-run
} finally {
    Remove-Item Env:TCFORGE_OPCUA_PASSWORD
}
```

Each output directory must be new. JSON and JUnit include setup/cleanup failure,
runner/certificate hashes, individual outcomes and explicit scope. A successful
run does not set production qualification metadata. Example mode requires its
outputs inhibited and checks sampled output state, not electrical pulse timing.

To restore the Example on a dedicated bench:

```powershell
powershell.exe -NoProfile -File scripts/activate_example.ps1 `
  -Target 172.18.236.100.1.1 -Platform 'TwinCAT RT (x64)'
```

This replaces the active target configuration. It enables task and boot
autostart, rejects warnings, preserves engineering profiles, and checks that the
actual cyclic counter advances. Keep UAExpert pointed at the Example device on
851; allow the OPC UA server to finish reloading symbols after activation.

Testing mode requires the Testing solution active on 853 and an OPC UA device
pointing at its filtered TMC. Set `--fixture Testing --port 853` and its namespace.
It controls only `MAIN.enableRpcPump` and the `MAIN.rpcOutput` source lock through
ADS. This lets the suite prove deferred execution, one pending command under
independent-client load, priority cancellation, source-lock enforcement and the
safe-command exception. Cleanup restores the lock, resumes the pump, and checks
ForceSafe completion/output off. Never map this fixture to physical outputs.

Optional `--observer-user` and `TCFORGE_OPCUA_OBSERVER_PASSWORD` exercise read
access and method denial for an already provisioned account. Omission is recorded
and does not imply role qualification. The runner does not change users, trust,
firewalls, or server configuration. Untrusted-certificate rejection, certificate
renewal and the complete commissioned permission matrix remain separate checks.

## Restart troubleshooting

Check the layers independently: TwinCAT RUN/cyclic execution over ADS, an OPC UA
TCP listener, then an authenticated session and PLC device status. An XAE restart
receipt alone does not verify OPC UA readiness. On the dedicated bench, a fresh
XAE-managed restart needed additional server startup time before authenticated
access recovered. Launching the server executable manually was not a verified
replacement for its TwinCAT-managed COM startup. Beckhoff describes this
[registration and startup relationship](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15622747659.html).

A separate Secure ADS reconnect failure after reboot was recovered using
Beckhoff's [Add-AdsRoute](https://infosys.beckhoff.com/content/1033/tc3_ads_ps_tcxaemgmt/11223580171.html)
with `-SelfSigned`, the existing expected peer `-FingerPrint`, credentials loaded
privately, and `-Force`. Certificate validation was retained. This recovery does
not establish the cause or prove unattended reconnect durability; that remains
an open bench issue in the progress tracker.

## Acceptance still required

Keep the Q4 restart/online-change, Q5 conflicting-task/application role matrix,
and Q6 physical IO/task-load gates in the progress tracker. A software restart
does not stand in for abrupt power loss. Local source hashes and unsigned reports
do not stand in for validation on a fresh engineering environment.

References: [Beckhoff security configuration](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_configurator/15555250187.html),
[PLC symbol configuration](https://infosys.beckhoff.com/content/1033/ts6100_tc2_opcua_server/15620470667.html).
