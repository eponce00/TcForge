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

- **`FB_StateMachine`** streamlined — a new private `_ClearCommandFlags`
  helper collapses the seven-line command-flag boilerplate that appeared
  inside `Abort`/`Home`/`Pause`/`Proceed`/`Start`/`Stop`. Method-local temps
  (`permIndex`, `stepIsZero`, `seqDone`) moved out of FB state.
- **`FB_Permissives`** and **`FB_Interlock`** refactored to compose
  `FB_BitMatrix64`. The two FBs now focus purely on their unique logic
  (latching + unmapped-bad memory for interlocks; none for permissives).
  ~80 lines of duplicated bit-fiddling eliminated.

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
  `F_ValidateRequester` (source lock), debounce on/off, `cfgInvert` in
  Regular mode, bad-quality last-known-good hold, one-scan edge pulses,
  and SinglePulse arm/cancel.
- **`FB_DigitalInput_Test`** (10 cases) via `FB_DigitalInput_Probe` —
  raw → quality gate → invert → debounce → edge detect pipeline, plus
  quality-tag propagation into `ST_DeviceHeader_Sts`.
- **`FB_TwoPosActuator_Test`** (15 cases) via `FB_TwoPosActuator_Probe`
  — state machine (Undefined / Advancing / Advanced / Retracting /
  Retracted / Faulted), permissive gating, source-locked arbitration,
  both-feedback and lost-feedback faults, `Abort` always accepted, and
  `header.stsBusy` mirroring `stsMoving`. Time-dependent timeout paths
  deferred to integration testing.

Full suite: 106 tests across 11 suites, green on the remote runtime
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
  via `FB_AlarmLimit` watching `stsValue`. The analog block is now a pure
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
