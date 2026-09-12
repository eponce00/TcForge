# TcForge progress

Last updated: 2026-09-11

## Goal and current status

Establish a dependable open-source architecture for discrete assembly production use before expanding
the feature set. The foundation refactor is implemented in source, but TwinCAT production qualification remains open. This is not a production-qualified release.

There are no existing consumers or backward-compatibility requirements. Delete or
refactor obsolete designs freely. Document the current contracts; migration guides
and before/after documentation are not required.

## How to maintain this tracker

- Keep this file as the shared work backlog; update it alongside relevant code changes.
- Use `[ ]` for open work and `[x]` for completed work. Keep stable item IDs when
  discussing work or referencing it from commits and issues.
- Mark implementation complete only when the source change and available checks
  are complete. Runtime verification has separate items and must not be implied.
- Add newly discovered gaps to the appropriate section with a concrete completion
  criterion. Note blockers and dependencies next to the item.
- Keep completed entries concise. Remove obsolete or duplicate tasks instead of
  preserving a changelog. Keep design details in `docs/` and link to them here.
- Update the date, current status, and next action whenever priorities change.

## Next action

Next, perform the medium-priority SPT candidate implementation audit: compare
its Components/Utilities and Event Logger blocks with our existing discrete-assembly
contracts, select a concrete missing capability, and adapt it with tests and
provenance. Start by assessing an optional Event Logger adapter for existing
faults; keep vendor logging dependencies outside the core control path. Do not
add a PackML hierarchy without a machine-coordination use case.

The immediate high-priority bench cases now pass: matching-session Online Change,
healthy-motion preservation, moving declaration recovery, controlled persistent-image
recovery, a real execution gap with preservation enabled and Home/Start pending,
and serialized ownership misuse by two real cyclic tasks. Keep execution-gap and
IO-loss protection. Physical power cuts, physical IO, fresh-PC qualification,
commissioned permissions and distribution work remain deferred and unqualified.

### Current priorities (user scope, 2026-09-10)

This ordering overrides older sequencing in the detailed items below; deferred
acceptance remains unproven, not completed.

- **High — Q4 engineering workflow:** use actual XAE Online Change with matching
  compile information; never silently substitute download, activation or restart.
  `scripts/verify_online_change.py` already edits through Automation Interface,
  invokes the available XAE DTE Online Change command and verifies the actual
  runtime counter. Baseline activation/restoration are separate fixture operations.
  Diagnose simulator feed stalls separately from PLC execution interruption;
  demonstrate healthy motion immediately before the applied change. Review and
  extend the verified compatible implementation policy to the remaining recovery and declaration/layout cases.
- **High — engineering tool usability:** extract a reusable online-change operation
  from the qualification fixture, with explicit target/PLC selection, baseline
  checks, command availability, outcome verification and no restart fallback.
  Source implementation now includes `twincat_online_change`, explicit target/port,
  sole logged-in PLC context, expected counter and runtime counter/cycle checks.
  Host errors are never replayed through CLI fallback. Matching-session preparation
  and end-to-end validation through an updated MCP server now pass. Preserve separate
  online-change and activation operations and explicit boot-project update behavior.
- **High — Q4 recovery:** exercise invalid/missing/backup persistent images and
  deterministic recovery. SSH permits an orderly Windows reboot; this does not
  reproduce abrupt removal of electrical power. Retain that distinction in reports.
- **Supporting robustness — Q5:** conflicting ownership means two cyclic tasks
  inside one PLC calling the same FB instance, not two PLCs commanding one device.
  The dedicated serialized misuse fixture now passes on the bench; keep the
  single-owner contract. Arbitrary concurrent FB calls remain unsupported.
  Deployment-specific operator accounts/permissions are later commissioning work.
- **Medium — R1/A7/A8:** after the high-priority lifecycle/tooling work, evaluate
  and adapt useful SPT utilities, device patterns and documentation integration
  for discrete assembly. Review actual needs and upstream license/attribution
  before adopting code; avoid process-plant scope or unnecessary dependencies.
- **Low/deferred — Q2/Q6/N2:** clean engineering-PC qualification, physical IO and
  fieldbus commissioning, physical power cuts and representative hardware/load
  acceptance. Local build reliability still matters when it blocks development.
- **Low/deferred — D2/Q7:** packaging/publication improvements and downstream
  release qualification. This repository is the reusable open-source library;
  company publisher metadata, private distribution and company-specific deployment
  policy are not current deliverables. Do not mark deferred qualification passed.

Simulator communication loss covers the application's stale/unavailable-input
response while the PLC continues running. PLC reboot also restarts execution and
reloads state; device power loss can additionally reset device state. Treat these
as distinct test scenarios even when all appear as a broken connection externally.

Engineering references:
[Online Change](https://infosys.beckhoff.com/content/1033/tc3_userinterface/2531444363.html),
[PLC Automation Interface](https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242730891.html),
[Login choices](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2531393419.html).

### Latest verification batch

2026-09-11 source-reference development workspace:

- [x] `TwinCAT/TcForge.sln` contains the core library, Example, Testing and
  Simulation in one TwinCAT project. Both source libraries enable referenced
  library use; consumers resolve the bracketed project identities. No reinstall
  or version bump is required for development builds.
- [x] `TcForgeReference` owns the shared reference-machine/bridge files once,
  avoiding duplicate object IDs across consumers while keeping fixture code
  outside the reusable core. Source libraries have no runtime instances or
  boot-project build entries.
- [x] Combined XAE 3.1.4026.26 build: zero errors/warnings; captured effective
  references confirm both source libraries for all three consumers. Dedicated
  bench source-reference TcUnit run: 380/380 individual tests across 31 suites
  at 10 ms (`artifacts/development-tcunit-10ms/tcunit.xml`). This is development
  evidence, not an installed-artifact qualification receipt.
- [x] Isolated Example, Testing and Simulation profiles remain available for
  single-application deployment. Build/test scripts distinguish source development
  from installed core-library qualification and restore source-reference files.
- [x] Reviewed installed-artifact dependencies: only the shared support library
  and its bindings/edges were added; vendor and core dependency versions did not
  change. Strict core check and all three consumer builds passed with zero
  errors/warnings and matching locks. Build receipt:
  `artifacts/builds/0a005d8c741d408db644a457ed6856c8/`.
- [x] All 92 tooling tests, repository structure checks and strict documentation
  build passed. Guards reject installed fallback, missing library membership,
  task collisions and source-library boot-build configurations.
- [x] Restored Example on bench port 851. ADS cyclic readiness and authenticated
  OPC UA passed (device error 0); ForceSafe completed on owner task 1 and duplicate
  submission returned 35. Both coils are off and outputs inhibited. Evidence:
  `artifacts/development-final-ready.json`, `development-final-opcua.json` and
  `development-final-outputs.json`.

2026-09-11 execution-boundary and ownership batch:

- [x] Real ADS STOP/RUN with both reference machines advancing and compatible-edit
  preservation enabled. System-task counter delta 26; PLC fixture cycles stayed
  frozen at 87 while stopped. First resumed scan rejected pending Home and Start
  with response 51, both coils off and outputs inhibited. Held requests stayed
  rejected; explicit recovery and fresh commands completed a full cycle.
  This isolated fixture has no IO watchdog and performs no online edit.
- [x] Two actual cyclic tasks (owner 1, witness 2): initial owner command executed,
  queued command cancelled (2), subsequent command rejected as wrong-task (13),
  conflict latched and output off. The deliberate handoff serializes calls;
  this does not qualify concurrent FB access or direct cross-task program methods.
- [x] Repeatable runner with fresh JSON/JUnit output, second-task liveness preflight,
  cleanup and negative evidence tests. Simulation compiled with zero errors/warnings;
  135 source XML files, 31 suites and 380 ST declarations checked. All 85 tooling
  tests and 18 simulator tests pass. No new TcUnit runtime run is claimed for this
  fixture-only batch. Evidence: `artifacts/architecture-boundaries-10ms-final/`.
  Earlier failed fixture setup attempts are retained separately and not counted as passes.
- [x] Restored Example on ADS 851. Authenticated OPC UA readiness passed after
  69 seconds; initial server-start timeouts remain in the report. ForceSafe
  completed in the owner task, duplicate rejection passed, and both reference
  coils are off/inhibited. Evidence: `artifacts/architecture-final-ready.json`,
  `artifacts/architecture-final-opcua.json`, `artifacts/architecture-final-output-state.json`.
  Strict documentation build passes.

2026-09-11 simulator transport and engineering-session batch:

- [x] Retain validated ADS RPC method handles for each transport connection.
  Snapshot calls measured roughly 29–36 ms on the bench, versus the earlier
  90–110 ms high-level RPC calls. Every cyclic request uses one read/write round
  trip. Signature/identity checks remain mandatory and failed commands are never
  replayed. `scripts/benchmark_simulation_rpc.py` reproduces read-only timing.
- [x] Separate read-only transport initialization from cyclic IO deadlines;
  retain the 200 ms scheduling and 150 ms frame-confirmation budgets. Cache the
  qualification counter's read handle, too; only this read-only handle may be
  reacquired after a symbol-version change.
- [x] Declaration qualification cycles the machine during compilation and judges
  motion from the last pre-change observation. Normal inhibited Ready between
  cycles is allowed; faults, lost IO and inhibition during motion still fail.
  Tooling tests: 79 pass. Simulation tests: 18 pass.
- [x] Implement matching-login, source read and hash-checked source edit tools in
  sibling `twincat-mcp`; isolated C# build and 17 MCP tests pass. Login cancels
  change/download prompts, edits require the existing logged-in host, and neither
  mutation is replayed through a fallback process.
- [x] Moving declaration/layout change and explicit recovery pass on ADS 854:
  counter 0 → 1, healthy advance immediately before the change, both coils off and
  old session invalidated afterward; stale claim/exchange return 34. Reset/Home
  and a new complete cycle pass, as do retained-history assertions. Source and
  baseline restored with no cleanup errors. Evidence:
  `artifacts/declaration-moving-two-second-stroke/`. The trace has 107 confirmed
  frames, maximum measured feed interval 157.3 ms. This is one bench configuration,
  not a general latency or production-load guarantee.
- [x] Actual MCP client completed matching login, source read, stale-hash rejection,
  source edit, object check and verified Online Change in the same owned host.
  Explicit baseline configuration/platform are selected and verified. Wrong ADS
  port was rejected before login. Source restored and owned host/DTE closed.
  Evidence: `artifacts/mcp-session-live.json` and `artifacts/mcp-session-live-v3.log`.
  Object checking succeeded with one XAE warning about the ignored generated
  `Simulation.tmc` file version; this was not a zero-warning check. The dedicated
  qualification fixture retires ignored generated TMC files before opening XAE.
  Delivered command failures now retain their structured receipts instead of
  being misreported as host failure or replayed through CLI.
- [x] Five synthetic UI cases verify cancellation of owned download/change/
  overwrite dialogs and noninterference with other PIDs/unrelated dialogs.
  Existing pending MCP launch/version fixes also pass 20 focused checks and are
  included with the workflow's required build/ADS prerequisites.
- [x] Restored Example on ADS 851. Consecutive authenticated OPC UA readiness
  checks report device error 0. ForceSafe completed on owner task 1, duplicate
  request rejected (35), output off. Evidence:
  `artifacts/session-workflow-final-ready.json` and
  `artifacts/session-workflow-final-opcua.json`. Source checks and strict docs
  build pass; no new full TcUnit run is claimed for these transport/tooling edits.
  MCP implementation and its prerequisites are committed as `77c9aea`.
- Earlier moving-test attempts found
  startup timeout, a Ready-state harness assertion and an idle application boundary;
  those incomplete runs are not counted as moving qualification.

2026-09-11 MCP online-change batch:

- [x] Added the C# online-change primitive, persistent-host-only MCP wrapper,
  direct/batch safety gates and documentation in sibling `twincat-mcp`.
  It refuses target/port mismatch, missing login, multiple online PLCs, unavailable
  command or stale expected count. It never logs in, downloads, activates, restarts,
  updates the boot project or retries an uncertain dispatch.
- [x] MCP Python tests: 11 pass, including no retry after host failure and no
  replacement of the current session. C# helper builds against the local MCP
  working tree; its pre-existing XAE/ADS dependency changes are separate.
- [x] Qualification runner can exercise the MCP primitive using `--command-backend
  mcp` and an optional isolated `--automation` build, retaining its structured
  receipt and assembly hash. Baseline activation/restoration stay separate.
- [x] Idle declaration change through the C# primitive applied on the real bench:
  ADS 854, online-change count 0 → 1, cyclic count 11070 → 11971. Receipt records
  `RuntimeVerified=true`. Evidence: `artifacts/mcp-online-idle-v3/`. This is command
  verification, not moving-machine or full MCP-client qualification. Original
  source and baseline restored; cleanup confirmed outputs inhibited.
- [x] Final Example restoration: ADS 851 RUN, authenticated OPC UA device error 0,
  ForceSafe completed on owner task 1, duplicate rejected and output off.
  Evidence: `artifacts/mcp-online-final-ready.json` and
  `artifacts/mcp-online-final-opcua.json`. All 77 TcForge tooling tests, source
  checks and strict documentation build pass. No PLC source change or new full
  TcUnit qualification is claimed by this batch.
- [x] Moving declaration/layout timing follow-up completed in the newer batch
  above. Retained RPC method handles resolved the extra ADS round trips; moving
  recovery now has a full passing scenario with unchanged cyclic watchdog limits.
- [x] Complete MCP-client workflow validated using an isolated updated server/build
  in the newer batch above. An existing installed server advertises its loaded
  tool set until its next launch; this does not alter a running engineering session.

2026-09-10 controlled recovery batch:

- [x] Read-only readiness runner verifies system RUN, cyclic execution and optional
  authenticated OPC UA device health with consecutive successes and bounded,
  fresh-process attempts. Separate restart-only XAE operation reports dispatch,
  not runtime success. See [runtime recovery](docs/18-Runtime-Recovery.md).
- [x] Orderly SSH/Windows reboot recovered Example and OPC UA with no route repair:
  `artifacts/recovery-ready-after-reboot.json`, 41 probes, 197.047 seconds from
  monitoring start. Existing pinned certificate authentication remained intact.
  One successful reboot does not establish worst-case startup time or eliminate
  the earlier intermittent TLS failure.
- [x] Controlled persistent-image runner: baseline backup, verified CONFIG,
  exact file readback, XAE restart, readiness, policy assertions and restoration.
  Bench-local CONFIG runs through pinned SSH with bounded state verification.
  No route repair was used in this batch.
- [x] Missing and backup-only cases passed in
  `artifacts/recovery-persistent-matrix-bounded/evidence.json`; both also completed
  baseline restoration and output cleanup. That report remains **failed overall**
  because its initial corrupt-image expectation incorrectly required backup loading.
- [x] A targeted repeat with an explicit reinitialization expectation passed:
  `artifacts/recovery-corrupt-reinitialize/evidence.json`. The malformed current
  file was rejected despite the valid backup being present: image flags cleared,
  markers/history initialized and outputs inhibited. Original images were restored,
  restored state checked and outputs cleared. This result covers the selected
  malformed-file fixture, not every corruption pattern or sudden power loss.
- [x] Example and Simulation activation now use bounded cyclic readiness rather
  than a single check after a fixed delay. Standalone monitoring can additionally
  require authenticated OPC UA device readiness.
- [x] Final Example restoration passed the integrated cyclic readiness gate.
  Authenticated OPC UA became ready after another 65.985 seconds of monitoring;
  ForceSafe queued/completed in owner task 1, duplicate rejected, output off.
  Evidence: `artifacts/recovery-final-example.log`, `recovery-final-ready.json`,
  `recovery-final-opcua.json` (all under `artifacts/`).
- [x] 77 tooling tests, source validation (132 XML / 31 suites / 380 declarations),
  PowerShell syntax checks and strict documentation build pass. No PLC library
  behavior changed in this batch; the earlier 380-test runtime result is separate.
  The final Example activation exercised the new integration on the bench;
  Simulation uses the same monitor, which was exercised throughout the image tests.



2026-09-10 online-change and recovery batch:

- [x] Separate `executionInterrupted` from `onlineChanged`. The default
  `recoverOnOnlineChange := TRUE` remains conservative; explicit FALSE permits
  compatible implementation edits while retaining gap/owner protection.
- [x] Actual moving implementation online change with `--policy preserve`:
  counter 0 -> 1, same nonzero boot epoch/session, healthy advance before and
  after, then completed cycle without reconnect, Reset or Home. Baseline source
  restored. Evidence: `artifacts/online-compatible-moving/`.
- [x] All 380 PLC tests in 31 suites passed at 10 ms on the bench:
  `artifacts/online-policy-tcunit-10ms-ready/`. The three new tests cover compatible
  continuity and mandatory interruption for coincident gaps/owner faults.
  The earlier 377-test 1 ms runs do not cover these three additions.
- [x] Full build `9385dcfbe409419d8b959c5c2eab1758`: all library objects and
  all three consumers, zero errors/warnings, matching dependency locks.
  Library SHA-256: `1F632506B66409C390BAD73A32A4693EB5080CA882ADCE6E4308EDF8F791D15F`.
  One tooling-test exit-code fix followed this receipt; do not claim an immutable
  qualification of the entire current source/tooling snapshot.
- [x] Generated TMC preflight preserves ignored XAE-generated symbols in artifacts
  before project load; compile/login information is retained. Tested rejection
  of unexpected producer and paths outside the repository. Integrated into
  build, Example/Simulation activation, TcUnit and online-change runners.
- [x] Reusable online-change command dispatch extracted to
  `scripts/online_change_commands.ps1`; dispatch is explicitly not runtime success,
  and unavailable/logged-out sessions cannot fall back to activation or download.
  66 tooling tests pass, including these command and TMC preflight checks.
- [x] Full MCP workflow and moving layout-change qualification pass in the newer batch;
  see that batch for the completed timing fix and retained runtime evidence.
- [ ] Restart robustness follow-up: the earlier Secure ADS TLS failure required
  a pinned route refresh. The current batch recovered without one, including an
  orderly Windows reboot. Repeated reboot endurance and the cause of that earlier
  failure remain unqualified; do not imply certificate trust was weakened.
- Example was reactivated successfully on port 851 with zero build warnings and
  advancing cyclic-owner counters: `artifacts/architecture-example-final.log`.
  Final authenticated OPC UA check passed: device error zero, ForceSafe queued
  and completed in cyclic task 1, duplicate rejected, output off. Evidence:
  `artifacts/architecture-final-opcua.json`. Endpoint remains
  `opc.tcp://192.168.1.224:4840`, Example ADS port 851. Existing certificate trust
  and authentication remain in place; no helper OPC UA process remains.
- Source checks, strict documentation build and whitespace checks pass after the
  final documentation update. The 66 tooling-test result is recorded above.

Earlier verification batch (different source snapshots):

- New immutable build `21835695c01c45c1be4a7c6be272bce6`: all library objects
  and all three consumers pass with zero warnings and matching dependency locks.
  Library SHA-256: `FEF53EE92AE22E409A5F59E170DF23B021AF3468DBCFA277596E7527993AD82F`.
- Fresh 377/377 PLC tests at both 10 ms and 1 ms, validated together against that
  build: `artifacts/batch-tcunit-10ms/`, `artifacts/batch-tcunit-1ms/`,
  `artifacts/batch-bound-validation.json`.
- The same library passes all three consumers from a clean library repository
  and fresh project copies; original repository registration is restored:
  `artifacts/batch-clean-library-install/`. This is the same engineering PC,
  not a separately qualified clean Windows/XAE installation.
- Reusable OPC UA suite: Example and Testing at 10 ms; Testing at 1 ms with a
  temporary read-only user. Sixteen independent clients, priority cancellation,
  source lock/safe exception, duplicate/invalid IDs, anonymous denial and verified
  cleanup pass. Evidence: `artifacts/q5-repeatable-example/`,
  `artifacts/q5-repeatable-testing-10ms-ready/`, `artifacts/q5-repeatable-testing-1ms/`.
- All 10 assembly functional scenarios and both short/long in-motion STOP/RUN
  cases pass at 1 ms: `artifacts/batch-assembly-1ms/`, `artifacts/batch-stop-start-1ms/`.
- 63 tooling tests, 18 Python model/contract tests, source integrity and strict
  documentation build pass. Guide: [OPC UA qualification](docs/17-OPC-UA-Qualification.md).
- A stale ignored `Simulation.tmc` caused an XAE warning and correctly failed
  the first build. Retaining it in artifacts and regenerating it produced the
  clean build above. No warning suppression was added; recurring stale generated
  metadata handling remains a build-workflow improvement.
- End state: Example restored on 851 via `scripts/activate_example.ps1`, with
  advancing cyclic counter, successful OPC UA ForceSafe/duplicate checks and
  output off (`artifacts/batch-example-restored.json`). UAExpert's certificate
  connects successfully. Temporary permission-test account removed. OPC UA
  startup temporarily refused TCP connections after restoration; verified ready
  before ending the batch. Current build/test bindings still validate after
  restoring the Example and the library repository configuration.

## Remaining architecture work

- [x] **A1 — Sequence boundaries and shutdown recovery.** Destinations and timeout
  bounds are validated; missing/duplicate active steps fault explicitly. Ordinary
  failures support explicit retry; failed Stop escalates to Abort; failed Abort
  latches `ShutdownFailed` and requires physical confirmation before Reset.
  Invalid fault codes cannot suppress fault handling; invalid Reset identity
  cannot clear recovery state. Nineteen new regression cases pass in the local
  PLC runtime. Current contract: [Sequencing](docs/7-Sequencing.md).
- [x] **A2 — Integrated reference machine.** One owning task composes required
  IO conditions, sequencing, the clamp actuator, final digital outputs and status.
  Home/Run, controlled Stop, Abort with independent trusted confirmation, and
  explicit recovery use the public signal boundary. Ten cyclic integration
  scenarios pass on the local PLC runtime. Test and example projects compile
  the same application files; the source checker enforces this. Current contract:
  [Reference machine](docs/11-Reference-Machine.md). Physical commissioning is Q6.
- [x] **A3 — Remote command execution ownership implementation.** Operator RPCs
  submit to a bounded, nonblocking mailbox; the cyclic owner validates and executes
  with fixed OPERATOR identity. One pending command, priority cancellation, eight
  result records, duplicate-ID rejection and program shutdown cancellation are
  defined. Actual ADS RPC observed context 0 versus cyclic owner 1, and verified
  deferred output mutation, owner dispatch and 16-client concurrent admission.
  Nineteen mailbox/dispatch PLC regressions pass. Contract:
  [Command source control](docs/3-Command-Source-Control.md).
  OPC UA server/security, conflicting-task and restart acceptance remain Q4/Q5;
  ADS RPC evidence does not qualify those environments.
- [x] **A4 — Uniform command validation.** Requester-bearing commands validate
  identity before device-specific checks or mutation, including recovery methods
  and alarm acknowledgement. Valid recovery/source-lock exceptions remain intact.
  Twenty-two invalid-identity regressions pass across sequences, actuators,
  analog/digital outputs, base diagnostics and alarms. Source checks reject new
  command implementations that omit the leading identity validation.

## Simulation, network bench and SPT follow-up

Priority order: Q4, Q2, Q5/Q6, Q7/D2; optional A7/A8 follow demonstrated machine needs.
The user's 2026-09-09 ideas are tracked here; completed foundations remain below.

- [x] **R1 — SPT reference review.** Reviewed SPT repository structure, Base Types,
  Components, diagnostics, initialization and distribution/documentation patterns.
  Recorded upstream commit and selective adoption decisions in
  [SPT review](docs/13-SPT-Review.md). No upstream implementation copied or added
  as a mandatory dependency. Candidate code-level audit remains part of A6/A8.
- [x] **S1 — Python simulation primitives.** Added `python/` package with pure
  cylinder and first-order analog models, mechanical/sensor fault injection,
  transport protocol, deterministic runner, JSONL trace and read-only ADS probe.
  Eleven Python tests and a 200-tick offline scenario pass. ADS probe reaches the
  existing local test PLC in RUN. These are not PLC end-to-end tests. CI now runs
  the Python model tests and offline scenario. [Package guide](python/README.md).
- [x] **S2 — Live PLC simulation IO bridge.**
  Added versioned identity, exclusive session, boot handshake, atomic complete-frame
  admission, output acknowledgement, owning-task consumption and 250 ms watchdog.
  The canonical reference machine runs in both TcUnit and a standalone no-IO,
  no-TcUnit simulation composition. Three consumers compile with zero warnings/errors.
  Actual ADS tests verify rejected frames, competing sessions, lost simulator,
  reconnect and explicit recovery. Actual runtime restart changed the boot identity,
  cleared the session, kept both coils off and rejected the previous boot identity.
  Standalone port 854 passes all 10 functional scenarios and an in-motion system
  restart on the network bench. Full lifecycle acceptance remains Q4. [Protocol and commands](docs/12-Simulation.md).
- [x] **S3 — Initial discrete assembly functional runner.** Ten actual PLC scenarios
  pass at 10 ms on both Testing and standalone network-bench applications:
  session/frame rejection, Home/assembly cycle, controlled Stop, Abort, jam timeout,
  contradictory sensors, lost IO quality, simulator loss, explicit recovery, and
  independent shutdown confirmation/timeout/Reset. JSONL/JUnit evidence:
  `artifacts/bench-assembly-e2e/` and `artifacts/bench-standalone-fed-probes/`.
  Eighteen Python model/live-contract tests pass. System restart during simulated
  advance passes: `artifacts/bench-in-motion-restart/`. Online-change, power-loss
  and physical IO/load acceptance remain Q4/Q6.
- [x] **N1 — Network test-bench access and inventory.** User confirms this is a
  dedicated bench with no connected equipment. Host `BTN-000TM2QI`, IP
  `192.168.1.224`, AMS `172.18.236.100.1.1`. SSH/RDP/ADS TCP ports respond.
  Secure ADS responds in Config mode. SSH command execution now works after the
  Administrator password change; credentials are kept outside the repository.
  RDP inspection confirms Windows 10 IoT Enterprise LTSC 21H2 build 19044.4046,
  Atom E3940, 8 GB RAM, TwinCAT kernel runtime 3.1.4026.17 (local XAE 4026.26).
  User activated a trial license on 2026-09-09; the isolated Testing application
  activated and reached RUN on port 853, confirming the required license coverage. An OPC UA server is installed. The route now displays secure status.
  Before deployment, backed up 79 boot/configuration files (8,962,036 bytes) with
  SHA-256 manifest in `artifacts/bench-backup-20260909/`. The saved boot configuration
  predates this work. Credentials stay out of repo.
  Read-only evidence: `artifacts/network-plc-inventory.json` and RDP inventory.
- [ ] **N2 — Bench deployment and acceptance.** After N1, retain a backup of the
  existing configuration; deploy isolated tests/simulation, confirm memory budget
  (current TcUnit PLC data area is about 245 MiB), and run Q3/Q4/Q6 on this target.
  A network bench without physical IO does not by itself close IO acceptance.
- [x] **A10 — Application execution continuity.** The reference composition detects
  missed system-task cycles and changed online-change counters before admitting
  commands. It cancels motion and requires explicit recovery; the simulation bridge
  invalidates its session/epoch. Six counter-policy tests and short/long in-motion
  stop/start tests pass at 1 ms and 10 ms. This does not control physical outputs
  while PLC code is stopped or detect a stop that skips no task cycle. Actual
  online-change acceptance remains Q4.
- [x] **A5 — Device configuration and conditioning lifecycle.**
  Output/actuator behavioral config changes invalidate active/saved/queued intent;
  new commands for the current config remain valid. Input type/config/quality
  handling is consistent; revoked bypass permissions cannot silently persist;
  standalone filter nonfinite inputs cannot poison history. Readiness/ownership
  contracts are documented in [Device lifecycle](docs/16-Lifecycle.md).
  Filter interpretation changes reseed from fresh usable samples; source reassignment
  invalidates old measurements. Digital inputs cannot advance debounce or emit edges
  during unusable quality. Saved output intent now has an explicit persistent validity marker; default zero/
  FALSE cannot arm restoration. ForceSafe/Reset/config changes invalidate it.
  A loaded non-backup image is also required; missing/backup-image status clears
  old intent. Six policy tests cover that gate; real invalid-image acceptance is Q4.
  Alarm validity is covered by A9. The combined 377-test
  suite passes on the bench at 10 ms and 1 ms. Actual restart/online-change and
  persistence acceptance remain Q4; there is no blanket online-change guarantee.
- [x] **A6 — IO diagnostic foundation.**
  Added original FB_IOQualityMonitor and EtherCAT slave status mapping after SPT
  diagnostic review. Producer freshness is separate from sensor value changes and
  InfoData.ChangeCnt. Startup/loss/deadline/recovery and error-bit tests are added.
  No SPT code copied. [Contract and provenance](docs/15-IO-Diagnostics.md).
  Actual driver wiring, bus loss and target load remain Q6.
- [x] **A9 — Alarm evaluation validity.** Explicit validity/evaluation state prevents
  invalid data from silently clearing alarms. Bit classification precedes numeric
  operations; wide deviation/rate arithmetic covers finite REAL extremes.
  Recovery requires fresh clear evidence and full off-delay. Configuration edits
  discard elapsed debounce credit without erasing unacknowledged latches; rate
  history reinitializes on invalidity, reassignment and timing/configuration changes.
  Fifteen focused regressions pass within the combined bench suite.
- [ ] **A7 — Parent/child machine coordination (later).** Evaluate SPT/PackML
  composition against an actual multi-module use case before adding framework
  hierarchy or changing the current sequencing contract.
- [ ] **A8 — Optional event/utility integrations (later).** Review SPT Event Logger
  and utility implementations individually. Keep event sinks outside mandatory
  control dependencies; audit numeric bounds and failure paths before adoption.
- [x] **D1 — Documentation website.** Build a navigable site from current Markdown,
  validate internal links and keep a single source of truth. Material for MkDocs
  configuration, home page, search, light/dark themes, grouped navigation and
  Pages deployment workflow are implemented. Strict build/link/anchor validation
  and browser search/navigation checks pass. Published with HTTPS at
  https://eponce00.github.io/TcForge/ from commit `021b5dd`; GitHub Actions run
  `34357244998` passed build and deployment. Public home and guide pages return
  HTTP 200, and the search index is served. Publication is separate from the local
  PLC update; the site identifies that source/documentation gap. Versioned
  documentation remains follow-up work. See [site maintenance](docs/documentation-site.md).
- [ ] **D2 — Company library distribution.** After Q2, replace development publisher
  metadata, define immutable release version/hash identity and generate a TwinCAT
  library repository layout. Test clean-machine installation and a consumer's
  pinned reference; link matching docs and release evidence. No distributable
  library repository has been published yet; the documentation website is live.

## Implemented foundation work

Checked entries track implementation. Build/runtime evidence is recorded below;
production qualification remains subject to Q2–Q7.

- [x] **F1 — State and command arbitration.** Base fault state gates normal
  commands; recovery-step status is distinct; Abort outranks Stop and normal
  commands; pending commands are consumed once and permissives rechecked.
  Stop, Retry and Reset handling includes the A1 sequence/recovery rules.
- [x] **F2 — Required conditions.** Required masks expose missing/stale mappings
  and inhibit operation; required interlock failures latch until healthy/reset.
  Applications must explicitly configure their requirements.
- [x] **F3 — Output recovery.** Default startup inhibition, explicit restart
  restoration and bad-quality hold options, fresh-command rearming, ForceSafe
  priority, configuration/numeric validation and bounded analog conversions.
- [x] **F4 — Actuator behavior.** Faults remove coil commands in the detecting
  scan; Abort/Reset inhibit automatic hold energization; motion and pending Abort
  arbitration are explicit; travel conditions and configuration are checked.
- [x] **F5 — IO boundary.** Plain public signal inputs/outputs; hardware allocation
  belongs to the consuming application. Obsolete embedded IO types, compatibility
  paths and injection-only probes removed; tests use public signal boundaries.
- [x] **F6 — RPC identity boundary.** Only fixed-identity Operator wrappers are
  RPC-enabled; source locking and core program methods are application-only.
  Execution ownership and server authorization still require A3/Q5.
- [x] **F7 — Supporting robustness.** Persistent fault-ring index bounds,
  task-cycle lookup instance isolation, input quality and numeric validation.
- [x] **F8 — Project isolation.** Separate test solution, explicit runtime target,
  no test-project hardware mappings or CPU reservation; exact TcForge/TcUnit
  consumer references. Library development/export has its own solution; consumers
  reference the installed library. Direct vendor dependencies are pinned.
- [x] **F9 — Verification infrastructure.** Source checker, source CI, complete
  JUnit report gate and its Python tests; foundation regressions and cyclic PLC
  tests registered. Actual TwinCAT execution remains Q3.
- [x] **F10 — Current design documentation.** Architecture, commands, IO,
  persistence, sequencing, HMI and qualification contracts documented.

## Installation and qualification follow-up

Engineering and runtime installation is complete; qualification is in progress. The detailed acceptance procedure and
restart matrix live in [Foundation qualification](docs/10-Qualification.md);
the selected versions belong in [toolchain.json](toolchain.json).

- [x] **Q1a: Install engineering and test tools.** Installed XAE 3.1.4026.26,
  TcXaeShell64, Usermode Runtime 1.26.2, TcUnit 1.3.0.0, .NET Framework 4.7.2
  Developer Pack, Package Manager UI 2.2.6.0 / CLI 2.4.77, and TwinCAT MCP.
  Existing Python 3.10 and VS 2022 Build Tools are used. Hyper-V remains active;
  Docker engine 29.5.3 responds with Linux containers. Runtime mode is UM and
  package signature verification remains enabled.
- [x] **Q1b: Verify basic connectivity.** The MCP C# helper builds; XAE loads
  both PLC projects through the Automation Interface; MCP initialization advertises
  40 tools; an actual MCP ADS read returns CONFIG from the local runtime at
  `192.168.1.108.1.1:10000`. TcUnit is present in the System library repository.
  Four MCP Python tests pass. The C# build emits warnings (including nullable
  annotations without nullable context); build-warning review remains Q2.
- [x] **Q1c: Verify the complete build/test workflow.** The current library is
  exported/installed, all three consumers build cleanly, and the local PLC reaches
  RUN with its TC3 PLC trial license. The latest network-bench runs report
  380/380 tests across 31 suites at 10 ms. The earlier 1 ms baseline has 377/377
  tests; it does not cover the three added continuity tests. Individual ADS results
  pass the JUnit gate. Production qualification
  remains separate under Q2–Q7.

MCP is registered in Codex as `twincat-automation` using the sibling repo's `.venv`,
with a 30-second startup timeout, 600-second tool timeout and the verified local
AMS Net ID as its default. The server remains in default SAFE mode. Reload Codex
if the newly registered tools are not available in an existing task.
Setup fixes in the sibling repo constrain Python MCP to 1.x (installed 1.30.0),
use Beckhoff ADS 7.0.317, and add the installed Common64 native ADS directory to
the helper process PATH. This resolved ADS client port registration without
changing firewall or virtualization settings.

TcUnit 1.3.0.0 was installed from the official release after copying it to the
repository's `artifacts/` directory. XAE rejected the same file from the AppData
location as corrupted, although its published size and ZIP CRC checks passed.
SHA-256: `A467549A5A44C352B3E4344328B1AD6F8F245E3AF841664149DC2E095AFB6DD4`.
An alternative tagged-source build attempt was unsuccessful and is not used.
Installed package inventory: `artifacts/installed-twincat-packages.config`.
Installer/helper logs: `%LOCALAPPDATA%/TcForge/installers/` and `%TEMP%/TcForge-*.log`.
The installer restart and licensing blocks are resolved. A seven-day TC3 PLC
trial was generated through XAE on 2026-09-08 and applied to the local Usermode
Runtime `192.168.1.108.1.1`. ADS port 853 reaches RUN. The local trial file is
ignored by Git; renew the trial or provide a production license as appropriate.
Current qualification also uses the licensed, dedicated network bench
`172.18.236.100.1.1` at `192.168.1.224`, with no connected equipment.

The local test approach follows Beckhoff's
[runtime configuration](https://infosys.beckhoff.com/content/1033/tc3_installation/20830884491.html)
and [Usermode Runtime installation/licensing](https://infosys.beckhoff.com/content/1033/tc170x_tc3_usermode_runtime/11319883275.html).
The repository now records the installed 4026.26 baseline and exact direct vendor
library versions. Verify compiler resolutions before qualification. Normal PLC licensing or
trial licensing still applies. Docker containers are not the initial TwinCAT/MCP
execution environment. Engineering uses native Windows XAE/COM; Usermode remains
available locally, and current runtime qualification uses the dedicated RT bench.

- [ ] **Q2 — Reproducible build.** Exact XAE version selection/readback,
  all-library-objects checking and zero-warning build policy are implemented.
  Direct project pins and exact source test identities are enforced. The all-objects
  library check and all three consumer builds pass with the exact baseline and
  zero errors/warnings.
  Implemented: `dependencies.lock.json` captures effective direct/transitive
  references and compiler-produced library signatures for all four projects;
  normal builds fail on drift. Source/tooling/helper hashes, Git revision and
  dirty state, compiler, dependencies and library bytes are retained in immutable
  build bundles. Fresh test tokens and receipts bind exact source test identities
  and actual 1 ms/10 ms task periods to that bundle. Local regression checks pass.
  The first bound full build passed with zero errors/warnings; immutable bundle:
  `artifacts/builds/d8a936f9ab514d5b8ea4bcb148b197f7/`. Fresh bound 377/377 PLC runs
  at both 1 ms and 10 ms passed, including installed-library and source restoration
  checks. Both reports validate together against that exact build. Evidence:
  `artifacts/q2-bound-tcunit-1ms/`, `artifacts/q2-bound-tcunit-10ms/`, and
  `artifacts/q2-bound-evidence-validation.json`. The full release checker reports
  only the intentionally pending overall qualification status.
  `verify_clean_library_install.ps1` passed all three consumer builds from a fresh
  library repository and uncached copies, with exact resolved TcForge path/hash
  checks before/after compilation. Repository order was restored and System
  TcForge files were unchanged. Evidence: `artifacts/q2-clean-library-install/`;
  tested artifact SHA-256 `BB25A4024DCC46C5CBC0125BEE079055D9B80198859D6346D7C3B1C6000EFEB2`.
  Repeated successfully for the immutable, runtime-tested `A59C27FB...` artifact:
  `artifacts/q2-bound-clean-library-install/`. All three consumers passed with zero
  errors/warnings; original repository configuration and System files were verified unchanged.
  Remaining: bind broader acceptance evidence and qualify
  a fresh engineering environment. Local manifests are unsigned evidence records.
  The development export is still mutable `2.0.0.0`, and a repeated export changed
  its binary hash. Each new build now retains its exact export separately.
  Bit-for-bit reproducible exports and a qualified production release are not claimed.
  The sibling helper now launches its own embedded XAE process with native DLL
  paths, attaches by exact PID and cleans up only that process. Engineering login,
  deployment and cold reset work. Ten launch and ten exact-version tests pass.
  Retain `artifacts/q2-enforced-build-verified.log`,
  `artifacts/q2-build-evidence.json` and the version-bearing consumer reports.
  The earlier `VisualElem` initialization failure remains a reliability observation
  in `artifacts/xae-initialization-failure.log`; full environment qualification is open.
- [x] **Q3 — PLC test execution.** All 377 registered tests passed across 31 suites
  on the licensed network bench after fresh activations at 10 ms and 1 ms. Each
  report verifies test identities, completion and actual runtime task period.
  Latest source-bound runs: `artifacts/batch-tcunit-10ms/` and
  `artifacts/batch-tcunit-1ms/`, both linked to build `21835695c01c45c1be4a7c6be272bce6`.
  Evidence: `artifacts/q4-trusted-tcunit-10ms.xml`, `artifacts/q4-trusted-tcunit-1ms.xml`,
  matching logs and activation-build JSON. Target/load stress remains Q6.
- [ ] **Q4 — Restart and persistence.** Execute the documented restart/reset and
  power-interruption matrix on the intended runtime/IPC. Verify actual persistence,
  inhibited defaults, restoration opt-in, quality recovery and diagnostic history.
  Completed: actual system restart during simulated advance on the bench; new boot
  identity, cleared session, coils off, stale requests rejected, no automatic resume,
  explicit Reset/Home and a complete recovery cycle. Evidence:
  `artifacts/bench-in-motion-restart/`. Direct ADS RESET/RUN and orderly system restart now pass retained-data checks
  for valid saved intent, ForceSafe-cleared intent, and Reset-cleared intent,
  including persistent configuration, alarm latch and diagnostic history.
  Reset-origin now passes with confirmed engineering logout and application removal
  before same-source reload; persistent markers, intent, alarms and history initialize.
  Evidence: `artifacts/q4-reset-origin/`. Controlled missing, backup-only and
  malformed-image cases now have evidence in the latest recovery batch above.
  Physical power loss remains open. Implementation-only online change
  while idle now passes via the actual Online Change command: counter increment,
  retained lifecycle state, epoch/session invalidation, stale-request rejection
  and explicit recovery. Evidence: `artifacts/q4-online-direct-idle/`.
  The earlier logged-in full solution build returned COM `E_FAIL`; removing that
  unrelated build step resolved the engineering failure. A later compatible implementation change during healthy motion passed with
  the same session and a completed cycle (`artifacts/online-compatible-moving/`).
  Declaration-changing online change while idle also passes, including retained
  state and explicit recovery (`artifacts/q4-online-declaration-idle-retry/`).
  Moving declaration/layout recovery now also passes with cached method handles
  and repeated two-second strokes (`artifacts/declaration-moving-two-second-stroke/`).
  A real execution gap with preservation enabled and pending Home/Start now passes,
  including first-resumed-scan rejection, held-command rejection and explicit
  recovery (`artifacts/architecture-boundaries-10ms-final/`).
  Each run restores exact POU source
  and reactivates the baseline application.
  XAE cold reset during motion now passes with verified login,
  STOP/RUN transitions, retained configuration/intent and explicit recovery:
  `artifacts/q4-trusted-cold-reset-verified/`.
- [ ] **Q5 — Actual OPC UA integration.** Verify exposed methods, credentials,
  certificates, roles, source locks and RPC task execution. Exercise the ownership
  solution from A3 and record command arbitration behavior.
  Bench connectivity resolved: changed the default Administrator password via
  authenticated Device Manager; verified SSH command execution. Recovery credential
  is DPAPI-encrypted outside the repo under the current Windows user's
  `%LOCALAPPDATA%/TcForge/bench/192.168.1.224-Administrator.credential.xml`.
  Confirmed the Win32 `TcOpcUaServer.exe` listens on TCP 4840 and accepts local
  connections. Added inbound rule `TcForge-Bench-OPCUA-DevPC`, restricted to
  development PC `192.168.1.108`; firewall remains enabled. Remote TCP and OPC UA
  discovery now pass (`artifacts/q5-opcua-endpoints.json`). Advertised endpoint is
  `opc.tcp://BTN-000tm2qi:4840` (reachable by IP), with SignAndEncrypt and username
  authentication. Certificate trust, credentials/roles, active ADS backend mapping
  and application-level method/ownership tests remain open. Installation XML points
  to ADS 851; standalone simulation needs its configured runtime 854.
  Added a separate filtered `TcForgeSimulation` device on ADS 854 and verified
  browsing with device error zero while that runtime was active. The subsequent
  user activation selected Example on 851; Simulation is now inactive.
  Secure Administrator login and an actual Example `OperatorForceSafe` call pass:
  queued (1), completed (0), duplicate rejected (35), execution task equals owner
  task (1), output remains off (`artifacts/q5-ua-force-safe.json`). Initial calls
  correctly rejected an uninitialized owner because Example's cyclic task had
  autostart disabled. Enabled task autostart in `TwinCAT/TcForge.tsproj` and
  rebuilt/reactivated Example with zero errors/warnings
  (`artifacts/q5-example-activation-build.json`). This verifies safe-command
  dispatch, not the complete ownership/role matrix.
  Explicit certificate trust now enabled on the bench: automatic trust disabled,
  UAExpert and qualification client certificates explicitly installed. Both trusted
  identities connect; a new certificate is rejected with BadSecurityChecksFailed
  and its exact certificate appears in the rejected store. Anonymous login is
  rejected with BadIdentityTokenRejected (`artifacts/q5-certificate-trust.json`).
  A temporary OS-authenticated read-only user successfully browsed/read but method
  invocation returned BadUserAccessDenied (`artifacts/q5-readonly-role.json`).
  The temporary user was removed and the original user/role configuration restored;
  no additional persistent credentials were introduced. Explicit certificate trust
  remains enabled and UAExpert's certificate was verified after the change.
  Twelve OPC UA SetOn requests while Example was inhibited were all queued then
  cancelled by cyclic policy, with output off at each observation; zero request ID
  returned 30 (`artifacts/q5-inhibition-arbitration.json`). Final ForceSafe,
  duplicate rejection and owner-task execution checks pass again. This samples
  output state; it is not a continuous electrical-output timing measurement.
  `scripts/verify_opcua.py` now provides the repeatable fixture suite with fresh
  JSON/JUnit directories, failure/cleanup handling, pinned server certificate,
  environment-only passwords and explicit coverage scope. Sixteen independent
  clients admit one request; paused-owner priority cancellation and source-lock
  enforcement pass at 10 ms and 1 ms. Observer read/method denial passes through
  the runner at 1 ms; temporary OS account removal is recorded in
  `artifacts/q5-readonly-role-batch-cleanup.json`. Example's 12 inhibition cases
  also pass through the runner. A separate real two-task ownership fixture passes
  serialized misuse, cancellation and subsequent rejection on ADS 854
  (`artifacts/architecture-boundaries-10ms-final/`). Remaining Q5: commissioned
  operator-role/node permissions. An initial test attempt
  timed out during OPC UA server restart; the ready-server repeat passed. No
  failed attempt is counted as successful acceptance.
- [ ] **Q6 — Hardware and task-load acceptance.** Validate the integrated example
  on representative hardware: bus/feedback loss, fallback outputs, recovery and
  cycle-time budget. Usermode tests alone do not qualify physical response or
  real-time scheduling.
  Initial 1 ms bench telemetry: 309 samples over 35 seconds, highest observed
  execution 159.2 microseconds, no observed overrun flags
  (`artifacts/q6-task-samples-1ms.json`). Sampling is not continuous worst-case
  measurement, and the window includes server preparation/restart as well as
  qualification activity; this does not close load or physical IO acceptance.
- [ ] **Q7 — Production foundation gate.** Close architecture items, retain reviewed
  build/test/restart/RPC/hardware evidence, update qualification metadata, and pass
  the release checker. Machine-specific commissioning remains required for each
  production application.

## Verification snapshot

Earlier baseline: **132 XML files, 31 suites, 377 PLC tests** (current batch above has 380). All three consumers
(test application, example and standalone simulator) compile under XAE
3.1.4026.26, `Release|TwinCAT RT (x64)`, with zero errors and warnings.

**377/377 tests passed on the licensed network bench at both 10 ms and 1 ms**
after fresh activations. JUnit export verifies every source test identity,
finished/failed/skipped flags, runtime initialization marker and actual task
period. These runs include 17 alarm-validity, eight filter-lifecycle, four digital-input-lifecycle,
ten saved-intent policy, six image-trust and six execution-continuity regressions.

Evidence:

- `artifacts/builds/d8a936f9ab514d5b8ea4bcb148b197f7/`: immutable build bundle with
  current source/tooling/helper identities, exact resolved dependency lock/captures,
  zero-error/warning all-objects and consumer reports, and tested library SHA-256
  `A59C27FB3162B55610B488FFBA9B706E4444987B23EC13838BDFD0B727EA19E4`.
  `artifacts/q2-bound-tcunit-1ms/` and `artifacts/q2-bound-tcunit-10ms/` contain
  new 377/377 results and validated receipts for that bundle. The older Q4 reports
  below are separate observed evidence; they have not been retroactively bound.
- `artifacts/q2-bound-clean-library-install/`: all three uncached consumers compile
  against the exact runtime-tested artifact in a fresh repository. Registration
  is restored and System TcForge hashes remain unchanged.
- `artifacts/q2-final-assembly-e2e/`: all ten assembly scenarios pass after
  activating the current installed artifact. This is observed functional evidence,
  not yet part of the automated build/test receipt protocol. Final bench state:
  `artifacts/q2-final-bench-state.json`, no session, both coils off and inhibited.
  Released simulation IO is unhealthy by design and requires a fresh connection
  and explicit recovery before operation.
- `artifacts/q4-trusted-evidence-manifest.json`: hashes for the 12 current PLC
  reports, source files and retained `artifacts/q4-tested-TcForge.library`. This
  records observed bench evidence; it is not the Q2/Q7 release manifest.
- `artifacts/q4-trusted-tcunit-10ms.xml` and `artifacts/q4-trusted-tcunit-1ms.xml`, with
  matching `.log` and `-build.json` files.
- `artifacts/bench-operator-rpc.log`: actual ADS context differs from cyclic owner;
  deferred execution, priority cancellation, duplicate rejection and 16 concurrent
  clients verified. The fixture finishes with its output off.
- `artifacts/bench-assembly-e2e/`: all 10 functional scenarios passed on Testing
  port 853. `artifacts/bench-standalone-fed-probes/`: all 10 also passed on the
  standalone simulation at port 854. The first standalone protocol test exceeded
  the scheduling budget; the harness now feeds IO between rejection probes.
  Watchdog and scheduling limits were not relaxed.
- `artifacts/q4-trusted-stop-start-1ms/` and `artifacts/q4-trusted-stop-start-10ms/`: short
  (30 ms) and long (500 ms) PLC stops during advance; resumed execution inhibits
  outputs, rejects stale sessions and requires explicit recovery.
- `artifacts/q4-trusted-ads-reset-seed/`, `q4-trusted-ads-reset-safe/`, `q4-trusted-ads-reset-reset/`:
  direct ADS RESET/RUN retains configured data, saved-intent validity, alarm latch
  and fault history while clearing volatile execution state. ForceSafe/Reset
  prevent command restoration. This is an observed ADS reset, not evidence that
  the XAE ResetColdCmd path worked; that separate path has its own evidence below.
- `artifacts/q4-trusted-cold-reset-verified/`: engineering login and cold reset
  during advance pass, including observed STOP/RUN, retained data and recovery.
- `artifacts/q4-trusted-system-restart-seed/`, `q4-trusted-system-restart-safe/`,
  `q4-trusted-system-restart-reset/`: orderly restart during simulated motion with real
  persistent data retained and volatile commands reset. Explicit saved-command
  invalidation survives restart. Boot-data-loaded status is recorded.
- `artifacts/q4-trusted-assembly-e2e/`: all 10 scenarios pass with execution continuity and the image-trust gate.
- `artifacts/bench-in-motion-restart/`: system restart during simulated advance
  passed, including stale-session rejection and explicit recovery. Cleanup released
  the session with both coils off and motion inhibited.
- `artifacts/q4-image-trust-build.log` and `artifacts/q4-trusted-simulation-activation-embedding.log`, `artifacts/TcForge.Tests-build.json`,
  `artifacts/TcForge-build.json`, `artifacts/TcForge.Simulation-build.json`.
- `artifacts/bench-backup-20260909/manifest.json`: hashes for 79 saved bench boot
  and configuration files, retained before deployment.

The user-reported duplicate message-category exception did not recur in fresh
build sessions; the old 07:19 local FPU exception predates the verified fixes.
One later XAE session had a PLC-subsystem `VisualElem` type-loading failure.
A fresh session recovered; engineering-session reliability remains part of Q2.

The test runner sets both task declarations and the cached PLC context coherently
before loading XAE, checks the engineering task period, rebuilds the selected
platform immediately before activation, then verifies the actual runtime period.
It restores the source profile after closing. Engineering scripts serialize XAE
access. Do not run manual/MCP engineering operations concurrently with them.

Bench-tested library SHA-256 (`artifacts/q4-tested-TcForge.library`):
`383EA729535A99E92A162E3DF615D898A452351A6C06F1F4D6199ED45EC431CB`.
Built from the modified working tree based on
`a55e2a7bd202d4d62b1aef243d24ef5afb26ac81`, not an immutable qualified release.
The shared reference-machine SHA-256 is
`530394AABDA2B6CDB46F1C9F9BC518FECC70E5253949F3EA3B820B839862CC08`.

The test PLC allocates approximately 245 MiB for its data area (204 MiB used).
The standalone simulator allocates 10 MiB (about 0.5 MiB used), so TcUnit storage
is not a production application memory estimate. Review target memory and task
load during Q6.

All 18 Python simulation tests and 85 script/evidence-gate tests pass. Recompute counts
after changing tests; they are not a fixed acceptance target. Run from repo root:

```powershell
python scripts/check_repository.py
python -m unittest discover -s scripts/tests -v
git diff --check
```

Q2/Q4/Q5/Q6/Q7 remain open for the deferred acceptance described above. Passing
bench cases does not qualify physical IO, abrupt-power-loss persistence,
machine-specific OPC UA permissions or worst-case load.
Keep qualification metadata at `pending-validation` until the release gate closes.
