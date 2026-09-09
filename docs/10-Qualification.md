# Foundation qualification

TcForge is a foundation under development, not a qualified production release. Source checks can run
without TwinCAT; compiler, runtime and machine acceptance evidence are required
before release. Installation and qualification progress is tracked in
[PROGRESS.md](https://github.com/eponce00/TcForge/blob/main/PROGRESS.md).

## Architecture decisions

- Keep the device base, composed alarms and modular library. Use the base fault
  state for command validation. `Status.AtRecoveryStep` describes odd steps;
  `Status.Faulted` mirrors `IsFaulted()` when the machine publishes status.
- One PLC task owns each device and its command calls. A scan samples inputs,
  evaluates conditions, consumes commands, updates state, applies output policy,
  then publishes status. There is no supported shared-instance multi-task API.
- The state machine consumes requests once. Abort outranks Stop; Stop outranks
  ordinary commands. A pending ordinary command cannot replace another pending
  request. Acceptance means admitted for the next scan, not physical completion.
- Condition configuration and freshness are separate. `nRequired` is a configured
  requirement mask, independent of whether `MapInput` was called. Configure it
  before operation. Missing required conditions cannot be bypassed. Optional
  unmapped bits retain the good-by-default behavior for intentionally optional conditions.
- Default output recovery is inhibited. Retained command restoration and holding
  a value during invalid quality each require explicit configuration. Neither
  setting bypasses a device fault or ForceSafe.
- Device blocks expose ordinary signal inputs and outputs. Hardware allocation
  and terminal mapping live exclusively in the application. Simulation uses the
  same public contract and cannot switch a hidden hardware path inside a device.
- Program methods are not RPC-enabled. Only `Operator*` wrappers are exposed,
  with operator identity fixed inside the PLC. Source locking is arbitration;
  authentication and method authorization belong in the OPC UA server setup.
  No instance may be called from an arbitrary second PLC task. Validate RPC
  execution in the owning PLC task during qualification.
- These are ordinary process-control interlocks, not safety-rated PLC functions.
  Machine safety functions remain in the machine's appropriate safety system.

## Output and recovery contracts

- Output startup is inhibited. `restoreCommandOnRestart` is an explicit opt-in.
- BAD/UNKNOWN quality disarms output. Default behavior applies `safeOutput` or
  `safeRaw`; `holdOnBadQuality` may hold only while quality remains invalid and
  no fault/ForceSafe overrides it. Recovery requires a fresh accepted command.
- ForceSafe applies electrical/raw fallback on the next cyclic call, bypassing
  pulse/debounce/inversion, and outranks ordinary output commands for that scan.
- SetOff is a logical command, so inversion still applies. It is not ForceSafe.
- Actuator faults remove coils in the detecting scan. Abort/Reset inhibit hold
  coils until an explicit new motion command, including rearming at a known position.
- State-machine Reset requires STOPPED and healthy running conditions. Retry
  handles designated step faults; Stop/Abort perform operational shutdown.

Outputs are process-image commands, not proof that a terminal or actuator changed
physically. Use actual feedback for physical confirmation. Analog `sts.rawReal`
is the applied raw command; when `outputInhibited` is true, `sts.value` must not
be interpreted as valid engineering-unit output feedback. Invalid output types
produce zero raw bits. A configured fallback must be appropriate for its terminal.

Persistent storage must be configured and tested for the chosen runtime. The
library preserves diagnostic history separately from volatile operating state.

## Verification available without installation

From the repository root:

```powershell
python scripts/check_repository.py
python -m unittest discover -s scripts/tests -v
```

The source CI job checks XML, compile inputs, test registration, RPC boundaries and
test-project isolation. It does not prove ST type correctness, virtual dispatch,
timer behavior or persistent storage. The JUnit validator is tested with failing,
empty, partial, skipped and duplicate reports.

## Repeatable Windows build

With the sibling `twincat-mcp` helper built and TcUnit installed, run:

```powershell
powershell.exe -NoProfile -File scripts/build_twincat.ps1
```

Use `-McpRoot` if the helper repository is elsewhere. This exports/installs the
current library from `TwinCAT/TcForge.Library.sln`, then builds the isolated tests
and example against it. Build results and the library are written to `artifacts/`.
The script selects `Release|TwinCAT RT (x64)` explicitly. XAE may otherwise choose
`TwinCAT OS (x64)`. It does not activate or restart a runtime. Export success alone
is not compilation evidence; check the consumer build results and still check
all unused library objects before release.

## TwinCAT qualification after installation

1. `toolchain.json` records the installed 3.1.4026.26 engineering baseline,
   Usermode Runtime 1.26.2 and the TcUnit 1.3.0.0 dependency. Direct Beckhoff
   library versions are pinned from the installation. Verify effective resolutions
   in the compiler, including transitive dependencies, and rebuild all projects.
   Record any deliberate toolchain changes before qualifying another baseline.
2. Build/check all library objects, including unused ones. Export/install the
   **current checkout's** TcForge 2.0.0.0 library before building Testing and
   TcForgeExample. Their references are exact, not a wildcard selecting an older
   installed library. Record commit, artifact SHA-256, dependency versions,
   compiler version and warnings. Do not suppress new compiler warnings globally.
3. Open `TwinCAT/TcForge.Tests.sln`. It contains only the Testing application,
   no example application or IO devices, no fixed target and no CPU reservation.
   Explicitly select an isolated Usermode Runtime/test target. The task is checked
   in with autostart disabled; the test runner must enable it for the run. Do not
   run two projects against the same runtime simultaneously.
4. Build, activate and run Testing (ADS port 853, task `Testing`). With the MCP,
   supply the solution, target, PLC and task explicitly to `twincat_run_tcunit`.
   Capture every test result; a timeout, skipped test, or missing suite is failure.
   Run again from a fresh PLC initialization to detect persistent test contamination.
5. After the runner finishes, export individual results using
   `python scripts/export_tcunit_report.py --target <ams-net-id>`. The exporter
   reads the pinned TcUnit 1.3 instance layout over ADS, checks test identities
   against source, rejects unfinished results and detects runtime reinitialization
   during capture. It writes `artifacts/tcunit.xml` and runs the report gate. Run
   `python scripts/check_test_report.py artifacts/tcunit.xml --expected-tests N`,
   using the declaration count printed by the source checker. The MCP runner's
   aggregate JSON is retained alongside the independently captured JUnit results.
6. Run `powershell.exe -NoProfile -File scripts/verify_operator_rpc.ps1 -Target
   <test-ams-net-id>` against the activated Testing fixture. The verifier only
   addresses MAIN.rpcOutput, MAIN.rpcUninitialized and the context probe. It
   verifies deferred output mutation, owner-task dispatch, cancellation, duplicate
   IDs and 16 concurrent ADS clients. Keep its output with the build evidence.
   Then exercise the same contracts through the actual OPC UA server: locked
   normal commands queue but their final result rejects; program calls still
   work; LockSource/SetBypass/core methods are not callable. Verify roles,
   credentials, certificates and the published symbol allowlist. Test conflicting
   cyclic ownership, server reconnects and runtime restarts. ADS RPC verification
   alone does not qualify the OPC UA server or its security configuration.
7. Execute the restart matrix below. Run timing tests at 1 ms and 10 ms task
   cycles. Then test representative real hardware for bus loss, feedback loss,
   safe-state behavior and cycle-time budget. Usermode execution cannot qualify
   physical IO response time or real-time scheduling.
8. Store signed/reviewed acceptance evidence with the release, mark `qualification`
   verified only when complete, and run `python scripts/check_repository.py
   --release --test-report artifacts/tcunit.xml`. Source CI passing alone never qualifies a release.

## Restart and persistence acceptance matrix

Use an isolated test project with no physical IO. Call each block once per scan.
For each case, record before/after command, applied output, fault and history.

| Case | Expected result |
|---|---|
| Default output, command ON/nonzero, orderly runtime restart | Inhibited; configured fallback; a new command is necessary |
| Same with explicit restore enabled and valid persisted image | Saved command resumes only with acceptable quality and no active fault |
| Restore enabled but startup quality BAD/UNKNOWN | Inhibited; quality recovery alone cannot resume |
| ForceSafe/Reset followed by restart | Saved operating intent has been cleared; default fallback remains |
| Active actuator hold, then Abort/Reset/restart | No automatic coil energization from feedback alone |
| Record fault, clear it, orderly restart | History survives only when persistent storage is configured and saved correctly; active fault is reevaluated |
| Cold reset / reset origin / missing or incompatible persistent image | Apply the documented reset-class storage semantics; default operating intent remains inhibited |
| Queued remote command then runtime restart | Pending intent and results are cleared; unknown result must not trigger automatic replay |
| OPC UA server restart/reconnect with PLC still running | PLC mailbox state remains authoritative; reconcile results/status without replaying uncertain intent |
| Real power interruption on the qualified IPC | Verify the actual UPS/persistent-save mechanism; declarations alone do not prove durability |

The source tests exercise fresh initialization and public lifecycle behavior;
multi-scan watchdog/motion tests use real TON time. Restart-image injection tests
are distinct from this matrix and cannot replace runtime/power-cycle evidence.

## Release evidence

Retain the commit ID, library SHA-256, toolchain/dependency manifest, clean build and
check-all-objects logs, complete test report, repeat-run results, restart/RPC matrix,
hardware acceptance results, and operating contracts. Production adoption requires
this evidence and machine-specific commissioning, even after every source change
in this foundation revision is complete.
