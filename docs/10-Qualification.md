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

- Output startup is inhibited. `restoreCommandOnRestart` is an explicit opt-in
  and also requires a valid saved-command marker. ForceSafe/Reset invalidate
  that marker; default FALSE/zero is not sufficient restoration evidence.
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

The source CI job checks XML, compile inputs, test registration, direct library
pins, RPC boundaries and test-project isolation. It does not prove ST type
correctness, virtual dispatch, timer behavior or persistent storage. Release
validation requires exact source test identities; an unrelated report with the
same count fails. Build provenance and transitive dependency verification remain
separate qualification requirements.

## Repeatable Windows build

With the sibling `twincat-mcp` helper built and TcUnit installed, run:

```powershell
powershell.exe -NoProfile -File scripts/build_twincat.ps1
```

Use `-McpRoot` if the helper repository is elsewhere. This checks all library
objects, exports/installs the current library from `TwinCAT/TcForge.Library.sln`,
then builds the isolated tests, example and standalone simulator against it.
Errors or warnings stop this workflow. Build results and the library are written
to `artifacts/`, including `TcForge-library-check-all.json`.
The script selects `Release|TwinCAT RT (x64)` and requires the exact XAE baseline
from `toolchain.json`; requested and effective versions are recorded in each
result. Missing versions and failed selection cannot silently choose another
compiler. It does not activate or restart a runtime.

To qualify consumption of an exported artifact from a fresh library repository:

```powershell
powershell.exe -NoProfile -File scripts/verify_clean_library_install.ps1 -Library artifacts/TcForge.library -Output artifacts/fresh-library-check
```

The output directory must be new. This copies consumer sources without compiler
caches, installs the supplied artifact into a uniquely named repository, and
checks actual resolved TcForge paths and hashes before and after each consumer
build. Exact dependency resolutions, compiler version and zero warnings remain
required. Cleanup removes only the temporary repository registration and verifies
the original repository order and existing System TcForge files. The copied
sources, installed artifact and evidence remain in the output directory. This
qualifies fresh TcForge consumption on the existing engineering installation;
it does not qualify a clean Windows installation.

The sibling helper must be rebuilt with the exact-version and owned-process
launcher changes. It launches XAE in embedded automation mode with the installed
native DLL paths, attaches only to that process's DTE, and closes only that owned
process. Repository scripts also initialize their own native DLL path. Neither
requires changing the machine PATH or Docker settings.

`dependencies.lock.json` records effective references and loaded library versions
for all four build projects. The build compares fresh XAE resolution and library
signature captures against this lock, including transitive dependencies. A wildcard
requires one concrete matching loaded-library signature; an installed file alone
is insufficient. Normal builds never update the lock. For deliberate dependency
changes, capture with `scripts/capture_dependency_resolutions.ps1`, produce a
candidate with `scripts/dependency_lock.py`, review it, and rebuild.

Successful builds retain a bundle under `artifacts/builds/<buildId>/`, including
the library, compiler results, dependency captures and build manifest.
`artifacts/build-evidence.json` points to the latest bundle through its recorded
canonical manifest path. Source, toolchain and helper identities are checked
before and after engineering operations. Only toolchain `notes` and `qualification`
are excluded from the compilation digest; qualification is checked separately.
These local records detect stale or mixed artifacts; they are not signed attestations.

To rebuild and run tests on the dedicated Windows RT target:

```powershell
powershell.exe -NoProfile -File scripts/run_tcunit.ps1 -Target <ams-net-id> -Platform 'TwinCAT RT (x64)'
```

This replaces the target configuration and restarts it. Evidence runs require the
platform in `toolchain.json`; another platform needs a deliberate toolchain change
and new build evidence. The runner rebuilds the selected platform in
the same XAE session immediately before activation; cached symbols from another
platform must not be reused. Build, simulation activation and test scripts share
an exclusive XAE lock. Run all engineering operations sequentially, including
manual/MCP operations that do not participate in that lock.

Use `-CycleTimeMs 1` for the 1 ms qualification run (the default is 10 ms).
The runner sets the PLC task, system task and cached PLC context before XAE
loads the project, restores the source profile after closing, and verifies the
actual running period in the JUnit exporter. Each run creates a new directory;
`-RunDirectory` may choose its location but cannot overwrite existing evidence.
The runner requires a current build manifest and verifies that the installed
TcForge library matches its artifact. Override `-BuildEvidence` or
`-InstalledLibrary` for explicit bundle/repository locations. JUnit and its receipt
bind the exact tests, actual period, target, source and library to one fresh run.
The receipt is finalized only after source profiles are restored, while the
engineering lock is still held. Re-exporting old results cannot create a bound run.

## TwinCAT qualification after installation

1. `toolchain.json` records the installed 3.1.4026.26 engineering baseline,
   Usermode Runtime 1.26.2 and the TcUnit 1.3.0.0 dependency. Direct Beckhoff
   library versions are pinned from the installation. Verify effective resolutions
   in the compiler, including transitive dependencies, and rebuild all projects.
   Record any deliberate toolchain changes before qualifying another baseline.
2. Build/check all library objects, including unused ones. Export/install the
   **current checkout's** TcForge 2.0.0.0 library before building Testing,
   TcForgeExample and the standalone simulator. Their references are exact, not a wildcard selecting an older
   installed library. Record commit, artifact SHA-256, dependency versions,
   compiler version and warnings. Do not suppress new compiler warnings globally.
3. Open `TwinCAT/TcForge.Tests.sln`. It contains only the Testing application,
   no example application or IO devices, no fixed target and no CPU reservation.
   Explicitly select an isolated Usermode Runtime/test target. The task is checked
   in with autostart disabled; the test runner must enable it for the run. Do not
   run two projects against the same runtime simultaneously.
4. Build, activate and run Testing (ADS port 853, task `Testing`) with
   `scripts/run_tcunit.ps1`, supplying the target and platform explicitly.
   Capture every test result; a timeout, skipped test, or missing suite is failure.
   Run again from a fresh PLC initialization to detect persistent test contamination.
5. The runner exports individual results automatically. The exporter
   reads the pinned TcUnit 1.3 instance layout over ADS, checks test identities
   against source, rejects unfinished results and detects runtime reinitialization
   during capture. Retain the printed run directory, its `tcunit.xml`, evidence
   receipt and activation-build JSON. A manual export is useful for diagnostics
   but cannot replace the runner's fresh provenance token and completed receipt.
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
   --release --build-evidence <bundle>/build-evidence.json --library
   <bundle>/TcForge.library --test-report <run-1ms>/tcunit.xml --test-report
   <run-10ms>/tcunit.xml`. Both reports must bind to the same build. Source CI
   passing alone never qualifies a release.

## Restart and persistence acceptance matrix

### Execution-boundary and cyclic-ownership fixture

The standalone Simulation project includes two unmapped reference machines and
an isolated digital output for architecture qualification. On a dedicated bench,
first run `scripts/activate_simulation.ps1` with the explicit target/platform,
then run:

```powershell
artifacts/sim-venv/Scripts/python.exe scripts/verify_architecture_boundaries.py --target <AMS-Net-ID> --output artifacts/architecture-boundaries
```

The output directory must be new. The runner verifies that the second program
is cyclic, starts simulated movement, stops only PLC application 854 through ADS,
writes Home/Start while execution is stopped, then resumes it. Both machines use
`recoverOnOnlineChange := FALSE`; actual execution gaps must still inhibit motion.
The PLC captures command responses and both coil bits on the first resumed scan.
The runner checks held commands, explicit recovery and completion of a fresh cycle.
This fixture has no IO watchdog and uses real system-task counters. It does not
apply an online edit or measure electrical outputs while PLC execution is stopped.

The ownership case first executes an operator command in the owner task. It then
queues a second command and yields the instance to a different cyclic task for
one call. The owner resumes after that call, checks cancellation of the queued
command and rejection of a new command, and verifies the latched ownership fault.
The handoff serializes these deliberately invalid calls; passing does not make
arbitrary concurrent FB calls or direct program methods safe. Each device still
requires exactly one cyclic owner. See Beckhoff's
[PLC task linking interface](https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242921611.html).

JSON and JUnit record the observed results, and cleanup returns the application
to RUN with the fixture outputs off. This ownership case is one-shot: reactivate
a fresh fixture before repeating it. Restore the normal application separately
after qualification.

### Acceptance cases

Use an isolated test project with no physical IO. Call each block once per scan.
For each case, record before/after command, applied output, fault and history.
Capture the first resumed scan as well as settled status. Distinguish a PLC
stop/start, a PLC reset, a TwinCAT system restart and an online change in the
evidence; one operation does not qualify the others.

The reference/simulation composition uses `FB_ExecutionContinuity` with the owning
system task's `CycleCount` and the PLC application's `OnlineChangeCnt`. Its
interruption response cancels intent and requires explicit recovery; standalone
devices have no implicit online-change contract. See the
[execution-continuity contract](16-Lifecycle.md#execution-continuity-in-the-application)
for counter sources and limits. In particular, it cannot act while PLC code is
stopped or detect a stop/start that misses no system-task tick.

| Case | Expected result |
|---|---|
| Default output, command ON/nonzero, orderly runtime restart | Inhibited; configured fallback; a new command is necessary |
| Same with explicit restore enabled and valid persisted image | Saved command resumes only with saved-command validity, BootDataLoaded TRUE, OldBootData FALSE, acceptable quality and no active fault |
| Missing or backup image, even with a saved-command marker | Old intent is invalidated; outputs remain inhibited until a fresh accepted command |
| Restore enabled but startup quality BAD/UNKNOWN | Inhibited; quality recovery alone cannot resume |
| Restore enabled with no valid saved-command marker, including inverted DO/nonzero AO fallback | Inhibited at configured fallback; default FALSE/zero cannot arm output |
| ForceSafe/Reset followed by restart | Saved operating intent has been cleared; default fallback remains |
| Active actuator hold, then Abort/Reset/restart | No automatic coil energization from feedback alone |
| Record fault, clear it, orderly restart | History survives only when persistent storage is configured and saved correctly; active fault is reevaluated |
| Restored alarm latch with invalid startup input | Active latch and recognized configured severity remain visible; invalid evidence cannot clear it |
| Restored acknowledged alarm latch | No second Ack required; valid clear evidence is still required |
| Cold reset / reset origin / missing or incompatible persistent image | Apply the documented reset-class storage semantics; default operating intent remains inhibited |
| Reference machine running, PLC stop/start that skips system-task cycles | First resumed scan cancels intent and inhibits outputs; explicit Reset/Home and fresh Start required |
| Same with a stop shorter than the simulation watchdog | Counter interruption must still invalidate session/epoch; do not rely on watchdog expiry |
| Implementation-only and declaration-changing online changes, idle and moving | Default recovery policy cancels intent and invalidates epoch. Explicit compatible-implementation preservation requires no execution gap or owner fault; declaration/layout changes require recovery. Qualify each policy separately |
| Home/Start coincident with detected interruption | Command is rejected/consumed, cannot execute later while held; explicit recovery and a fresh command edge required |
| Queued remote command then runtime restart | Pending intent and results are cleared; unknown result must not trigger automatic replay |
| OPC UA server restart/reconnect with PLC still running | PLC mailbox state remains authoritative; reconcile results/status without replaying uncertain intent |
| Real power interruption on the qualified IPC | Verify the actual UPS/persistent-save mechanism; declarations alone do not prove durability |

The source tests exercise fresh initialization and public lifecycle behavior;
multi-scan watchdog/motion tests use real TON time. Restart-image injection tests
are distinct from this matrix and cannot replace runtime/power-cycle evidence.
The saved-command marker and restored-alarm publication policy are implemented;
the full matrix remains open. On the dedicated 3.1.4026.17 bench, short/long
PLC stop/start passes at 1 ms and 10 ms. Direct ADS RESET/RUN and orderly system
restart pass the standalone fixture's saved-intent/configuration, alarm-latch and
fault-history checks. ForceSafe/Reset invalidation survives both operations.
Separate controlled missing/backup/malformed-image cases and actual online changes
now have bench evidence in PROGRESS.md, including moving declaration recovery and
compatible implementation preservation. Sudden power loss remains unqualified.
Reset-origin passes separately: engineering logout and controller
application removal are verified before same-source reload; persistent markers,
intent, alarms and history then initialize. The separate XAE cold-reset path passes after
confirming engineering login, waiting for reset STOP, and verifying subsequent
RUN. See PROGRESS.md for retained evidence.

Use Beckhoff's [remanent-variable semantics](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2528803467.html)
to define reset-class expectations, and its
[online-change operating cases](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/6415331211.html)
to distinguish initialization and instance-copying behavior. Record the actual
runtime version, image status and save mechanism with those results.

## Release evidence

Retain the commit ID, library SHA-256, toolchain/dependency manifest, clean build and
check-all-objects logs, complete test report, repeat-run results, restart/RPC matrix,
hardware acceptance results, and operating contracts. Production adoption requires
this evidence and machine-specific commissioning, even after every source change
in this foundation revision is complete.
