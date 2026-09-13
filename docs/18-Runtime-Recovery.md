# Runtime readiness and persistent-image qualification

A restart command being accepted does not prove the runtime is usable. The
readiness runner checks system RUN, PLC RUN and an advancing application counter.
When configured, it also opens an authenticated OPC UA session with pinned server
certificate and checks the PLC device error status. Two consecutive complete
probes must pass. Each attempt runs in a fresh process with a bounded deadline;
no route, service or application state is changed by the monitor.

On the dedicated bench, an orderly Windows reboot recovered without refreshing
Secure ADS routes. Complete Example/OPC UA readiness took about 197 seconds from
the start of monitoring (which began after the reboot command). This is one
observed reboot, not a universal startup bound or proof that the earlier TLS
failure cannot recur. Use the report's failed stage to distinguish ADS, cyclic
execution and OPC UA startup.

## Read-only readiness

Create a local JSON config, for example `artifacts/readiness.json`:

```json
{
  "target": "172.18.236.100.1.1",
  "fixture": "Example",
  "port": 851,
  "ads_dll_directory": "C:/Program Files (x86)/Beckhoff/TwinCAT/Common64"
}
```

Use `Simulation` and port `854` for the unmapped lifecycle fixture. Use
`Testing` and port `853` to check that the TcUnit task is advancing before
collecting its ADS results. This readiness check is read-only and never reboots
or reactivates the target.

Optional `opcua` configuration requires `endpoint`, `application_uri`, `certificate`,
`key`, `server_certificate`, `user`, `password_env` and `namespace`. Certificates
must already be trusted. Supply the password through the named process environment
variable; do not include it in the config or commit it.

```powershell
python scripts/wait_runtime_ready.py --config artifacts/readiness.json `
  --output artifacts/readiness-result.json --timeout 300
```

Example and Simulation activation scripts also use this monitor for cyclic
readiness. Their default activation check does not include OPC UA; supply the
optional configuration when that layer is required.

The output path must be new. Exit zero means all requested layers passed twice;
nonzero means readiness was not established within the budget. Reports retain
failed stages and numeric ADS errors, but not arbitrary server error text or
credentials. A hung probe is terminated within its attempt budget.

## Restart without deployment

On an authorized dedicated target:

```powershell
powershell.exe -NoProfile -File scripts/restart_runtime.ps1 `
  -Target 172.18.236.100.1.1 -Solution TwinCAT/TcForge.Example.sln `
  -Output artifacts/restart-dispatch.json
```

This uses `StartRestartTwinCAT` in an owned XAE session, preserves project files,
and serializes access with the other engineering scripts. It does not build,
activate a configuration, download PLC code or generate a boot project. Its
receipt deliberately leaves `RuntimeVerified` false. Run the readiness check
separately. See Beckhoff's
[Automation Interface](https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242753675.html).

## Controlled persistent images

`scripts/verify_persistent_images.py` is restricted to the unmapped Simulation
fixture on port 854. Install the Python `bench` extra on the engineering PC. The
runner requires an existing route, SSH account and independently verified SHA256
hex fingerprint of the SSH host public key.

Its local JSON config requires:

- `dedicated_unmapped_bench`: explicit `true` authorization for this fixture.
- `target`, `port` (854), `host`, and `solution` (Simulation solution path).
- `boot_directory`: the target's absolute Windows path ending in `Boot/Plc`.
- `ssh_user`, `ssh_password_env`, `ssh_sha256`, and `ads_dll_directory`.
- `corrupt_recovery`: explicitly `reinitialize` or `backup` for the qualified
  target/configuration. The tested 3.1.4026.17 bench reinitializes after the
  malformed-current-file case; backup-only loading is tested separately.

```powershell
python scripts/verify_persistent_images.py --config artifacts/images-config.json `
  --output artifacts/images-run
```

The runner seeds known persistent state, observes CONFIG before touching files,
backs up `Port_854.bootdata` and `Port_854.bootdata-old`, and verifies every file
write by readback. CONFIG control runs over authenticated SSH against the
bench-local ADS router, and verifies that the local AMS identity matches the
requested target. The Windows helper uses `C:/TwinCAT/Common64/TcAdsDll.dll`.
The helper is copied to a uniquely named Windows temporary file and removed
after execution; its execution-policy override applies only to that PowerShell
process. No machine execution policy or certificate trust is changed.
This avoids relying on a network ADS session while that session is being disrupted
by CONFIG. It exercises missing images, a backup-only image and a corrupt
current image with a valid backup. A corrupt current file is not assumed to have
the same recovery behavior as an absent current file: Beckhoff documents backup
loading when the current file is absent in the
[persistent-data settings](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/3434442123.html).
The configured expectation is strict: reinitialization requires both image flags
clear, default markers/history and inhibited outputs; backup recovery requires
the backup flag, seeded markers/history and inhibited outputs. It never accepts
an arbitrary outcome just because the PLC started. XAE restarts the existing configuration, and
readiness is checked before reading fixture state. Each case must prove inhibited
outputs and the expected image flags/markers. Cleanup restores the original bytes,
checks restored state and explicitly clears outputs. A failed cleanup fails the
run; retain its local backups for recovery. Use `--cases missing`,
`--cases backup_only`, or `--cases corrupt_current_with_backup` for a targeted
rerun; the report lists requested cases and does not imply unselected cases passed.

The corruption fixture replaces the current file with a short malformed image.
It does not exhaust every possible partial-write or byte-corruption pattern.
These controlled file cases do not simulate electrical power removal or prove
storage durability. Do not run them against a mapped or production application.
