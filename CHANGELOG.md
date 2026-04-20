# Changelog

All notable changes to **TcForge** are recorded here. Dates are ISO-8601.
The library is pre-1.0, so the API surface may still evolve — breaking
changes are called out explicitly under each release.

## [Unreleased]

### Added

- **`FB_BitMatrix64`** in `Common/Utilities` — shared 64-bit condition-matrix
  core consumed internally by `FB_Permissives` (non-latching) and
  `FB_Interlock` (latching). Owns `MapInput`, `SetBypass`, cleanup timing,
  first-failure tracking, and "just unmapped while bad" events. Public APIs
  of the two consumers are unchanged.
- **`PRG_Alarms`** and **`GVL_ALARMS`** in `TcForgeExample` — working demo
  of the alarm composition pattern: `FB_AlarmLimit` watching a simulated
  process value, plus `FB_AlarmSimple` promoting a state-machine fault bit
  into the alarm list.

### Changed

- **DUT member prefixes dropped — BREAKING** — the redundant `cfg` / `sts`
  prefixes on members of every `ST_*_Cfg` and `ST_*_Sts` struct (plus
  `ST_DeviceHeader_Sts`, `ST_Permissive_Faceplate`, `ST_Interlock_Faceplate`)
  were removed. Reading `dev.cfg.cfgInputType` or `dev.sts.stsValue` was
  noisy — the container already says the role. Members now read cleanly:
  `dev.cfg.inputType`, `dev.sts.value`, `dev.sts.header.faulted`,
  `faceplate.ok`, `faceplate.bypassable`, etc. Unprefixed fields
  (e.g. `faultCode`, `lastFaultString`, `tsLastCommand`) were already in
  the target style and are unchanged. FB-level identifier prefixes (`inp*`
  on VAR_INPUT, `_private` on internals) are unrelated and kept — they
  signal *visibility*, not *role*. Every call site in the library, the
  `TcForgeExample` project, the unit-test suite, and the docs was updated
  by word-boundary rename. Existing application code referencing the old
  names must rename their accessors.
- **`FB_StateMachine`** streamlined — a new private `_ClearCommandFlags`
  helper collapses the seven-line command-flag boilerplate that appeared
  inside `Abort`/`Home`/`Pause`/`Proceed`/`Start`/`Stop`. Method-local temps
  (`permIndex`, `stepIsZero`, `seqDone`) moved out of FB state.
- **`FB_Permissives`** and **`FB_Interlock`** refactored to compose
  `FB_BitMatrix64`. The two FBs now focus purely on their unique logic
  (latching + unmapped-bad memory for interlocks; none for permissives).
  ~80 lines of duplicated bit-fiddling eliminated.
- **`U_IoRaw_In` / `U_IoRaw_Out`** — UNION member names widened from
  1-character aliases to multi-character ones (`r` → `fReal`,
  `i` → `nInt`); the `AT %I*` / `AT %Q*` pragma moved from a UNION
  member to the enclosing `ST_AnalogInput_IO.inRaw` /
  `ST_AnalogOutput_IO.outRaw` variable. Workaround for a TwinCAT
  parser bug that mis-parsed 1-character UNION members when the
  enclosing FB was extended by a subclass in a referenced library,
  which previously blocked unit testing of `FB_AnalogInput` and
  `FB_AnalogOutput`. Hardware-link syntax (`.io.inRaw.dw` / `.io.outRaw.dw`)
  is unchanged; only `.r` → `.fReal` and `.i` → `.nInt` on the UNION alias.

### Docs

- Documentation chapters reordered into a logical flow:
  Foundations → Command Layer → Infrastructure → Modules → Consumer.
  All internal section numbers, anchors, cross-refs, and navigation banners
  updated.

### Tests

- **`FB_BitMatrix64_Test`** — 14-case TcUnit suite exercising the shared
  bit-matrix core: initial state, MapInput semantics, out-of-range guard,
  mapping-timeout unmap, bad-at-unmap event edge behaviour, first-failure
  ordering, and every SetBypass / ClearBypass / ClearFirstFailure path.
  Covering the base simultaneously hardens `FB_Permissives` and
  `FB_Interlock`.
- **`FB_Permissives_Test`** (8 cases) and **`FB_Interlock_Test`** (9 cases)
  — lock in the consumer-visible contracts on top of `FB_BitMatrix64`:
  non-latching vs. latching behaviour, bypass semantics, and reset paths.
- **`FB_AlarmSimple_Test`** (10 cases) and **`FB_AlarmLimit_Test`**
  (8 cases) — cover debounce, latch, ack, and severity routing on the two
  most-used alarm blocks, plus the four-band HiHi/Hi/Lo/LoLo arbitration
  in `FB_AlarmLimit`.
- **`FB_DeviceBase_Test`** (10 cases) via a test-only
  `FB_DeviceBase_Probe` — validates protected `_Raise` / `_ClearFault`
  semantics, `Reset()` safety, and how `_UpdateHeader()` mirrors fault
  state into `ST_DeviceHeader_Sts`. Establishes the "probe subclass +
  `SUPER^()` in cyclic body" pattern now reused across device tests.
- **`FB_LPF_FirstOrder_IIR_Test`** (6 cases) — pure-math coverage of the
  exponential smoothing recurrence, including passthrough on invalid
  `fDt` / `fTau`, first-sample seeding, convergence, and error-flag
  bookkeeping.
- **`FB_DigitalOutput_Test`** (12 cases) — command routing through
  `F_ValidateRequester` (source lock), debounce on/off, `invert` in
  Regular mode, bad-quality last-known-good hold, one-scan edge pulses,
  and SinglePulse arm/cancel.
- **`FB_DigitalInput_Test`** (10 cases) via `FB_DigitalInput_Probe` —
  raw → quality gate → invert → debounce → edge detect pipeline, plus
  quality-tag propagation into `ST_DeviceHeader_Sts`.
- **`FB_TwoPosActuator_Test`** (15 cases) via `FB_TwoPosActuator_Probe`
  — state machine (Undefined / Advancing / Advanced / Retracting /
  Retracted / Faulted), permissive gating, source-locked arbitration,
  both-feedback and lost-feedback faults, `Abort` always accepted, and
  `header.busy` mirroring `moving`. Time-dependent timeout paths
  deferred to integration testing.
- **`FB_AnalogInput_Test`** (12 cases) via `FB_AnalogInput_Probe` —
  conditioning pipeline end-to-end: initial status, linear scaling
  endpoints + midpoint, raw bypass, clamp-low / clamp-high with
  `clamped*` reporting, `CLAMPED` quality promotion, `clampAsFault`
  promoting clamps to `ClampLow` / `ClampHigh` faults, `BadConfig` on
  first scan, BAD-quality last-known-good hold, `TYPE_REAL` UNION
  member selection, and quality-tag propagation. Unblocked by the
  `U_IoRaw_In` rename above.
- **`FB_AnalogOutput_Test`** (14 cases) via `FB_AnalogOutput_Probe` —
  command pipeline end-to-end: initial status, linear scaling
  endpoints + midpoint (verifies both `sts.rawReal` and the INT
  UNION alias `io.outRaw.nInt`), clamp-high / clamp-low with
  `clamped*` reporting, `sts.commanded` preserving the unclamped
  request, raw bypass, `clampAsFault` promoting clamps to
  `ClampLow` / `ClampHigh` faults, `BadConfig` on first scan,
  `TYPE_REAL` UNION alias write via `io.outRaw.fReal`, BAD-quality
  skipping the UNION write (verified through the DWORD view),
  quality-tag echo, and source-lock arbitration rejecting OPERATOR
  while still accepting PROG.
- **`FB_AlarmThreshold_Test`** (10 cases) — single-side threshold
  trip logic: `bFailHigh` / `bFailLow` strict > / < comparisons,
  priority when both flags are set, no-op when neither flag is set,
  `bEnable` suppression, `eSeverity` propagation into status, and
  latching behaviour.
- **`FB_AlarmDeviation_Test`** (10 cases) — deviation tripping in
  both absolute and setpoint-relative modes: above / below /
  inside-band, setpoint tracked in relative mode and ignored in
  absolute mode, asymmetric limits, `bEnable` suppression, and
  `eSeverity` propagation.
- **`FB_Step_Test`** (12 cases) via `FB_StateMachine_Probe` —
  lifecycle contract of the step wrapper: inactive leaves
  Entry/Execute/Exiting low, Entry one-shot on activation, the
  perm-settle Execute pass, Exiting one-shot once perms go
  satisfied, Advance leaves all three lifecycle outputs low,
  `sm.Status.Step.Name` published while active, mapped-FALSE
  perm holds Execute and blocks Exiting, flipping to TRUE releases
  Exiting, `nTimeout = 0` disables the timeout branch,
  `TimerSeconds > nTimeout` raises `E_SM_Fault.StepTimeout`,
  `RaiseFault` is a no-op outside the active step, and surfaces
  the code through `sm.GetFaultCode()` while active.

  `FB_StateMachine_Probe` is a tiny test-only subclass that empties
  the SM cyclic body (so the SM logic under test doesn't interfere
  with step observations) and exposes a narrow `SetCurrentStep` /
  `SetTimerSeconds` pair for driving the step without running the
  full state machine — the SM itself deserves its own dedicated
  suite (next). The probe is shared at the test-suite FB level:
  `FB_StateMachine` is ~52 KB and TwinCAT puts method-local `VAR`
  on the task stack (default 48 KB), so a per-method probe blew
  `C0297` and took the RT task (and Windows) down at activation.
- **`FB_StateMachine_Test`** (17 cases) via an extended
  `FB_StateMachine_Probe` — command gate and transition matrix:
  power-on defaults, Home/Start/Stop/Abort/Pause/Proceed happy paths
  and wrong-state rejections, permissive-bad rejection on Home,
  Ready+Stop short-circuit to Stopped, Abort auto-init settling over
  two scans (transition scan resets step to 0, next scan auto-inits
  to `ABORTING_MIN`), Homing sequence-complete via `R_TRIG_5` on
  `_nextStep=0`, running-interlock trip auto-aborting with the
  `RunningInterlockTripped` fault surfaced through `GetFaultCode()`,
  odd-step auto-raise of `OddStepReached`, external
  `inpSubmoduleFaulted` surfacing through the fault book-keeping,
  and OEE blocked-condition publishing during RUNNING.

  The probe body was promoted from empty to `SUPER^()` so the SM
  body runs when the test calls `sm()`; the step suite doesn't call
  `sm()` so its observations are unchanged. A new `ResetAll` mutator
  clears fault book-keeping, command-request flags, the internal
  `R_TRIG_1` / `R_TRIG_5` rising-edge memory, and permissive /
  interlock live bits between tests. Interlock reset order matters
  — `MapInput(bit, TRUE)` must precede `Reset()` because
  `FB_Interlock.Reset` snaps `_latchedBits` from `nLiveBits`, so a
  bit left FALSE by the previous test stays latched bad across the
  reset otherwise. `ForceState` / `ForceLastState` / `ForceNextStep`
  and `MapHome/Start/Proceed/AutoPerm` complete the driver surface.

Full suite: 181 tests across 17 suites, green on the remote runtime
(`172.18.236.100.1.1`).

## [2026-04-16] — Alarms + architecture simplification

### Added

- **Alarms module** — complete alarm subsystem built around
  `FB_AlarmBase` + `I_Alarm`: `FB_AlarmSimple`, `FB_AlarmThreshold`,
  `FB_AlarmLimit` (4-level HiHi/Hi/Lo/LoLo), `FB_AlarmDeviation`,
  `FB_AlarmRateOfChange`. Uniform surface for debounce, latch, ack,
  severity, timestamps. Latch/ack state is `VAR PERSISTENT` so process
  restarts cannot silently hide critical alarms.
- **`F_Now`** in `Common/Utilities` — single LTIME timestamp function
  used across fault / command / alarm logs.

### Changed

- **`FB_DeviceBase`** now owns fault book-keeping directly — current
  fault, last fault (persistent), and an 8-entry persistent ring buffer.
  `_Raise(code, source, reason)` is idempotent on `code` within one
  episode; `_ClearFault()` preserves history.
- **`FB_AnalogInput`** simplified — embedded HH/HI/LO/LL process-alarm
  logic and clamp-threshold handling removed. Alarms compose externally
  via `FB_AlarmLimit` watching `value`. The analog block is now a pure
  signal-conditioning pipeline.
- **`F_ValidateRequester`** signature collapsed to three parameters
  (`eRequester`, `bSourceLocked`, `bFaulted`) — the `bAllowWhenFaulted`
  and `bSkipSourceCheck` escape hatches were never used and encouraged
  bypassing the safety contract.

### Removed

- **Decorative interfaces** — `I_Abortable`, `I_AnalogCommandable`,
  `I_DigitalCommandable`, `I_Diagnosable`, `I_Resettable`,
  `I_SourceLockable`. They existed only as documentation; no consumer
  ever treated implementers polymorphically. `I_Alarm` is retained
  because the alarm list does consume it polymorphically.
- **`FB_FaultHandler`** — merged into `FB_DeviceBase`. The separate FB
  added indirection without adding capability.
- Dead getters on `FB_AlarmBase`.

## [2026-04-09] — State machine + interlocks foundation

### Added

- **`FB_StateMachine`** / **`FB_Step`** — 9-state machine
  (STOPPED → READY → HOMING → RUNNING → STOPPING → ABORTING → PAUSING →
  PAUSED → PROCEEDING) with step ranges per state, permissive gating,
  auto-start, retry, OEE blocked/starved condition reporting, and a
  running-interlock auto-abort hook.
- **`FB_Step`** — Entry/Execute/Exiting lifecycle for sequence steps,
  permissive mapping, step-level fault raising, timeout handling.
- **`FB_Interlock`** — latching 64-bit condition matrix with mapping
  timeout, first-failure tracking, per-bit bypass, and "bit was bad when
  it became unmapped" memory.
- **`FB_Permissives`** — non-latching 64-bit condition matrix with
  bypass and first-failure tracking.
- **TcUnit harness** in `Testing/` with the first suite covering
  `F_ValidateRequester`.

### Project

- Renamed `Core` → `Forge` → `TcForge` across library, example, solution,
  and documentation.
- MIT license.

---

Unreleased changes land on top of the last published section; once a
coherent batch is ready for users, we promote it to a dated release.
