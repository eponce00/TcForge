# TcForge progress

Last updated: 2026-09-09

## Goal and current status

Establish a dependable architecture for company production use before expanding
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

Prioritize S2: implement the isolated PLC simulation IO bridge with coherent
frames, exclusive ownership and a PLC-side freshness watchdog. Then S3 can run
Python plant models against the actual reference machine. S1 is implemented and
locally tested. In parallel with that work, resolve N1 access to the dedicated
network bench before deploying to it. Continue Q2–Q7 qualification; new SPT-inspired
features remain behind testing and diagnostic foundations. Preserve Docker,
Hyper-V and Windows security settings.

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

Priority order: S2, N1, S3/N2, A5/A6 and Q2–Q7; then D1/D2 and optional A7/A8.
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
- [ ] **S2 — Live PLC simulation IO bridge.** Implement a separate simulation
  composition using the same reference-machine source and application IO boundary.
  Enforce exclusive input ownership, version/session handshake, coherent frame
  commit, output correlation, PLC-side stale-data watchdog and explicit reconnect.
  Keep physical fieldbus mappings disabled in that configuration. Test partial
  writes, duplicate/wrong-session frames, simulator crash and PLC restart before
  enabling Python writes. [Required contract](docs/12-Simulation.md).
- [ ] **S3 — Functional scenario runner.** Drive actual PLC Home/Run/Stop/Abort,
  jams, contradictory/missing sensors, timeout, shutdown confirmation and recovery
  through the simulated plant. Retain trace and machine-readable assertions.
  Keep deterministic test time separate from wall-clock functional execution.
- [ ] **N1 — Network test-bench access and inventory.** User confirms this is a
  dedicated bench with no connected equipment. Host `BTN-000TM2QI`, IP
  `192.168.1.224`, AMS `172.18.236.100.1.1`. SSH/RDP/ADS TCP ports respond.
  Existing Secure ADS route returns error 29 (TLS connection failure). SSH accepts
  authentication but refuses commands until the default password is changed.
  Resolve initial-password setup and secure routing, then inventory OS, runtime,
  CPU, licenses, loaded projects and IO. Do not store credentials in the repo.
  Read-only probe evidence: `artifacts/network-plc-inventory.json`. No runtime
  state change, deployment, route change or password change performed.
- [ ] **N2 — Bench deployment and acceptance.** After N1, retain a backup of the
  existing configuration; deploy isolated tests/simulation, confirm memory budget
  (current TcUnit PLC data area is about 216 MB), and run Q3/Q4/Q6 on this target.
  A network bench without physical IO does not by itself close IO acceptance.
- [ ] **A5 — Initialization/configuration lifecycle audit.** Use SPT's explicit
  initialization pattern as a comparison. Define readiness, invalid live config,
  online-change/restart behavior and ownership for each block. Add mechanisms only
  where a concrete failure mode is found; integrate evidence with Q4.
- [ ] **A6 — Bus/device diagnostic adapters.** Review specific SPT Diagnostic and
  EtherCat candidates. Implement application adapters that translate bus/device
  status into existing IO quality and required conditions; test lost/stale data
  and recovery. Record version, provenance, notices and regression coverage for
  any adapted implementation.
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
  exported/installed, both consumers build cleanly, and the local PLC reaches
  RUN with its TC3 PLC trial license. TcUnit reports 235/235 passing tests across
  21 suites; individual ADS results pass the JUnit gate. Production qualification
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
No network PLC has been used.

The local test approach follows Beckhoff's
[runtime configuration](https://infosys.beckhoff.com/content/1033/tc3_installation/20830884491.html)
and [Usermode Runtime installation/licensing](https://infosys.beckhoff.com/content/1033/tc170x_tc3_usermode_runtime/11319883275.html).
The repository now records the installed 4026.26 baseline and exact direct vendor
library versions. Verify compiler resolutions before qualification. Normal PLC licensing or
trial licensing still applies. Docker containers are not the initial TwinCAT/MCP
execution environment; native Windows XAE/COM plus Usermode Runtime is the chosen
development setup.

- [ ] **Q2 — Reproducible build.** Resolve and pin exact vendor libraries, record
  toolchain versions, build/check all library objects, export/install the current
  checkout's library, and build both consumers. Resolve compiler errors and
  investigate warnings; record commit and artifact hash.
- [ ] **Q3 — PLC test execution.** Run every registered test, including A1/A2
  additions; capture complete results and pass the report gate. Repeat from fresh
  initialization and exercise timing at 1 ms and 10 ms task cycles. Fix failures
  and record evidence; source checks cannot substitute for this.
- [ ] **Q4 — Restart and persistence.** Execute the documented restart/reset and
  power-interruption matrix on the intended runtime/IPC. Verify actual persistence,
  inhibited defaults, restoration opt-in, quality recovery and diagnostic history.
- [ ] **Q5 — Actual OPC UA integration.** Verify exposed methods, credentials,
  certificates, roles, source locks and RPC task execution. Exercise the ownership
  solution from A3 and record command arbitration behavior.
- [ ] **Q6 — Hardware and task-load acceptance.** Validate the integrated example
  on representative hardware: bus/feedback loss, fallback outputs, recovery and
  cycle-time budget. Usermode tests alone do not qualify physical response or
  real-time scheduling.
- [ ] **Q7 — Production foundation gate.** Close architecture items, retain reviewed
  build/test/restart/RPC/hardware evidence, update qualification metadata, and pass
  the release checker. Machine-specific commissioning remains required for each
  production application.

## Verification snapshot

Latest available source baseline: 109 XML files, 23 suites and 276 PLC test
declarations. Source checks and all 5 Python report-gate tests passed.
The exported library, isolated test application and example compile under XAE 3.1.4026.26,
`Release|TwinCAT RT (x64)`, with zero errors/warnings. Both the compiler output
and XAE's failed-project count confirm the builds passed. The example's obsolete
VisuSymbols library reference was removed.
**276/276 PLC tests passed across 23 suites on the local Usermode Runtime, 10 ms
cycle, after fresh activation.** This includes 19 sequence-integrity regressions, 10 reference-machine scenarios,
22 identity-validation cases and 19 mailbox/dispatch cases.
Both consumers build with zero compiler errors and warnings.

Runtime evidence: `artifacts/architecture-tcunit.log` and `artifacts/architecture-tcunit.xml`.
The JUnit export reads each test's name, finished/failed/skipped flags and duration
from the running PLC. It checks identities against the current source and detects
reinitialization during capture. All 276 individual results passed the report gate.
Actual ADS RPC evidence: `artifacts/operator-rpc-final.log`, produced by
`scripts/verify_operator_rpc.ps1`. Requests do not mutate output while consumption
is paused; execution reports the owning task; urgent commands cancel normal work;
duplicates reject; 16 concurrent clients admit one pending command and return BUSY
to the other 15. The final test fixture is left at its safe output. No OPC UA
server or network PLC was qualified.

Repeat at 1 ms and repeat the corrected build from fresh initialization before Q3
is closed; the source-only restart probes do not close Q4.

Compiler-driven fixes removed duplicate/out-of-block declarations and moved POU
methods before LineIds metadata so XAE loads them. The source checker now rejects
code after metadata and stray declarations after END_STRUCT. The sibling MCP
checks XAE's failed-project count and returns raw build output; an empty Error
List is no longer treated as proof of a successful build or safe test activation.

`powershell.exe -NoProfile -File scripts/build_twincat.ps1` exports/installs the
current library and builds both consumers without runtime activation. It requires
the built sibling MCP helper and Windows PowerShell 5.1. Generated evidence lives
in `artifacts/`; retain reviewed evidence for release. Check unused library objects
and transitive dependency resolutions separately before closing Q2.
Current library SHA-256:
`594F1ECC436D9DF26D382814D7990BC9B02A199262A2FCF9314C7F9746458F37`.
This artifact came from the modified working tree based on commit
`b7906203262b29312e75fb7ceb3ddd463de9f251`, not an immutable qualified release.
Build evidence: `artifacts/TcForge.Tests-build.json`, `artifacts/TcForge-build.json`,
`artifacts/architecture-build.log`. The reference application source is shared
by `TwinCAT/Testing.plcproj` and the example project; test sources remain under
`TwinCAT/Testing/`. Reference-machine SHA-256:
`2CF4B9A7D055AD48657975958ADD3BAD86CEBE932D022AAE655926F293BE6B1D`.
The obsolete disconnected sequence/alarm demo programs are removed from the example.

The test application currently allocates approximately 216 MB for the PLC data area (180 MB used); review
TcUnit limits/test-instance storage during Q3 before deploying to a smaller PLC.

Recompute counts after changing tests; they are not a fixed acceptance target.
Run from the repository root:

```powershell
python scripts/check_repository.py
python -m unittest discover -s scripts/tests -v
git diff --check
```

Release qualification remains blocked by incomplete build/dependency qualification
and missing runtime acceptance results. Do not mark qualification verified to bypass the gate.
