# 7 Sequencing

The sequencing module provides `FB_StateMachine` and `FB_Step` — the two blocks you need to drive any multi-step automatic process. This document covers the state model, how sequences are structured, how to wire permissives, and how steps participate in the unified fault model from [§2 Architecture](2-Architecture.md).

> **Navigation:** [← Persistent Variables](6-Persistent-Variables.md) · [README / TOC](../README.md) · [Alarms →](8-Alarms.md)

---

## 7.1 State Model (E_SM_State)

The machine is always in one of nine states:

| State | Kind | Meaning |
|-------|------|---------|
| `STOPPED` | Waiting | Power-on default. Not homed. Entry via `Abort` sets `Status.Faulted`. `Home` is the only exit. |
| `READY` | Waiting | Homed or just-completed a cycle. `Start` is the only command that moves forward. |
| `PAUSED` | Waiting | Frozen mid-cycle. Context held for `Proceed`. |
| `HOMING` | Active | Homing sequence running (steps 1000–1999). |
| `RUNNING` | Active | Production sequence running (steps 3000–3999). |
| `STOPPING` | Active | Graceful shutdown sequence (steps 2000–2999). |
| `ABORTING` | Active | Fast-safe shutdown sequence (steps 5000–5999). |
| `PAUSING` | Active | Save-context sequence before pausing (steps 4000–4999). |
| `PROCEEDING` | Active | Restore-context sequence before resuming (steps 6000–6999). |

**Waiting** states: no step sequence is running; the machine is quiescent.  
**Active** states: a step sequence is driving outputs; `FB_Step` blocks execute.

### 7.1.1 Transition Graph

```
STOPPED  --Home-->    HOMING     --done-->  READY
READY    --Start-->   RUNNING    --done-->  READY   ← AutoCycle loops here
RUNNING  --Stop-->    STOPPING   --done-->  STOPPED
RUNNING  --Pause-->   PAUSING    --done-->  PAUSED
PAUSED   --Proceed--> PROCEEDING --done-->  RUNNING (re-enters at paused step)
READY    --Stop-->    STOPPED    (direct, no sequence)
ANY*     --Abort-->   ABORTING   --done-->  STOPPED (Status.Faulted = TRUE)
```

`ANY*` = any state except `STOPPED` and `ABORTING`.

### 7.1.2 Distinguishing READY sub-states

`READY` is entered from both `HOMING` (first home) and `RUNNING` (cycle complete). Use `Status.LastState` when you need to tell them apart:

```iecst
IF fbSM.Status.State = E_SM_State.READY AND fbSM.Status.LastState = E_SM_State.RUNNING THEN
    // just finished a production cycle
END_IF;
```

`AutoCycleRequest` and the auto-run logic already use this internally to only auto-restart after a completed cycle, not after homing.

### 7.1.3 Fault indication

`Status.Faulted` is `TRUE` whenever the current step number is odd (`CurrentStep MOD 2 <> 0`). An abort lands in `STOPPED` with `Status.LastState = E_SM_State.ABORTING`, giving the HMI enough context to show "stopped after abort" without needing a separate state.

---

## 7.2 FB_StateMachine

### 7.2.1 Instantiation

```iecst
fbStateMachine : FB_StateMachine;
```

Minimum call in the cyclic program:

```iecst
fbStateMachine(
    cfgAutoRun  := FALSE
);
```

| Input | Purpose |
|-------|---------|
| `cfgAutoRun` | Automatically re-starts a new cycle when `READY` after a completed run and start permissives are met. |

### 7.2.2 Key outputs

| Output | Type | Description |
|--------|------|-------------|
| `Status` | `ST_SM_Status` | Embeds `header : ST_DeviceHeader_Sts` (ready/busy/faulted, fault code + string + source + reason, timestamps), plus `State`, `LastState`, `BlockedCondition`, `StarvedCondition`, `Step` snapshot |
| `StepInfo` | `ST_SM_StepInfo` | CurrentStep, CurrentStepName, NextStep, StepTimerSeconds |
| `HomePermOK`, `StartPermOK`, `ProceedPermOK`, `AutoPermOK` | `BOOL` | Flat perm-OK flags directly on the FB output |
| `StepPermCfg` | `ST_Permissive_Config` | Active step's permissive config (mirrored from FB_Step) |
| `StepPermStatus` | `ST_Permissive_Status` | Active step's permissive status (mirrored from FB_Step) |

### 7.2.3 OEE conditions — `ReportBlocked` / `ReportStarved`

OEE condition codes (`BlockedCondition`, `StarvedCondition`) are written by external reporter methods, not by mutating inputs. The caller — typically the same program that ran the sequence programs — pushes the active reason code each scan:

```iecst
// Report from the station program that knows *why* the line is blocked/starved
IF NOT inpDownstreamReady THEN
    fbStateMachine.ReportBlocked(code := 101);   // 101 = downstream buffer full
ELSE
    fbStateMachine.ReportBlocked(code := 0);     // 0 clears the condition
END_IF;

IF NOT inpUpstreamPartPresent THEN
    fbStateMachine.ReportStarved(code := 202);   // 202 = upstream queue empty
ELSE
    fbStateMachine.ReportStarved(code := 0);
END_IF;
```

The state machine copies the latest reported value into `Status.BlockedCondition` / `Status.StarvedCondition` each cycle. A non-zero value means the condition is active; zero means clear. Use any code space you like as long as zero is reserved for "no condition".

### 7.2.4 Faults — `E_SM_Fault`

`FB_StateMachine` raises its own faults through `_Raise(code, source, reason)` inherited from `FB_DeviceBase` (see [§2.4 Fault Book-Keeping](2-Architecture.md#24-fault-book-keeping)). Fault codes follow the range convention from [§2.3.3](2-Architecture.md#233-fault-code-range-convention):

| Code | Name                       | Range        | Trigger                                                                                   |
|------|----------------------------|--------------|-------------------------------------------------------------------------------------------|
| 1    | `StepTimeout`              | 1–9 Timeouts | A step's `nTimeout` (seconds) was exceeded. Source = `'STEP_<N>'`.                        |
| 2    | `OddStepReached`           | 1–9 Timeouts | Sequence landed on an odd step without a more specific fault already being active.        |
| 3    | `StepUserFault`            | 1–9 Timeouts | A step body called `step.RaiseFault(code, reason)` to report a custom condition.          |
| 50   | `RunningInterlockTripped`  | 50–59 Intlk  | Running-state interlock (`intlkRunning`) tripped and forced an abort. Source = `'INTLK_RUNNING'`. |
| 70   | `SubmoduleFaulted`         | 70–79 Prop   | `inpSubmoduleFaulted` asserted by a child module. Source = `'SUBMODULE'`.                 |

All five raise with **source** and (when useful) **reason** so the HMI shows where and why:

- `StepTimeout` / `StepUserFault` / `OddStepReached`: raised by `FB_StateMachine._RaiseStepFault(stepNum, stepName, code, reason)`. `source` is auto-built as `'STEP_<nnnn>'`; `reason` defaults to `'Step <N> [<name>]: <resolved fault string>'` when the caller doesn't supply one. This guarantees the HMI never sees an empty reason.
- `RunningInterlockTripped` / `SubmoduleFaulted`: raised by the state machine body with a constant `source` tag and a fixed `reason` sentence.

The fault code, text, source, reason, timestamp and ring buffer all surface through `Status.header` — see [§2 Architecture](2-Architecture.md) for the shared header contract.

---

## 7.3 Writing a Sequence

Each active state has its own sequence program. Sequence programs receive the state machine as a `VAR_IN_OUT` parameter so FB_Step can call internal methods without exposing them publicly.

```iecst
PROGRAM _3000_PRG_Running
VAR_IN_OUT
    sm : FB_StateMachine;
END_VAR
VAR
    step3000 : FB_Step;
    step3002 : FB_Step;
END_VAR
```

Call it from MAIN:

```iecst
_3000_PRG_Running(sm := fbStateMachine);
```

### 7.3.1 Step Lifecycle

`FB_Step` provides three one-scan phases:

| Phase | Fires when | Typical use |
|-------|-----------|-------------|
| `Entry` | First scan the step becomes active | Command actuators, reset timers |
| `Execute` | Every scan while active | Monitor feedback, call `MapPerm` |
| `Exiting` | One scan when all permissives pass and `nNextStep` is set | Cleanup, confirm outputs |

After `Exiting`, `FB_Step` hands `nNextStep` to the state machine and the sequence advances.

### 7.3.2 Minimal step example

```iecst
step3000(
    sm        := sm,
    nStep     := 3000,
    nNextStep := 3002,
    sName     := 'Enable drives',
    nTimeout  := 5
);
IF step3000.Entry  THEN outDriveEnable := TRUE; END_IF;
IF step3000.Execute THEN step3000.MapPerm(0, 'Drives ready', inpDriveReady); END_IF;
```

### 7.3.3 Dynamic branching

Compute `nNextStep` conditionally in the FB call — it is re-evaluated every scan:

```iecst
step3004(
    sm        := sm,
    nStep     := 3004,
    nNextStep := SEL(bQualityOK, 3008, 3006),   // fail → 3008, pass → 3006
    sName     := 'Inspect part'
);
```

Branches based on timers, sensor states, or counters work identically — just compute the value inline.

### 7.3.4 Completing a sequence

Set `nNextStep := 0` on the last step. The state machine detects step `0` at the end of an active sequence and transitions to the next waiting state automatically:

```iecst
step3008(
    sm        := sm,
    nStep     := 3008,
    nNextStep := 0,       // sequence complete
    sName     := 'Unload part'
);
```

### 7.3.5 Fault steps (odd step numbers)

Fault steps use the odd-step convention. The step directly above the normal step serves as its fault landing. `Status.Faulted` derives from `CurrentStep MOD 2 <> 0`:

```
3000 — normal step
3001 — fault step (e.g. timeout from step 3000)
3002 — next normal step
```

`FB_Step` automatically advances to `nStep + 1` on timeout expiry **and** raises a fault on the way. The fault itself is what the HMI displays; the odd step is just the rendezvous point for any cleanup logic.

---

## 7.4 Raising Faults From a Step

Two kinds of fault enter the state machine from a step body, both routed through the unified fault model (§2.4):

### 7.4.1 Automatic `StepTimeout`

Fires when `Status.Step.TimerSeconds > nTimeout` and `nTimeout > 0`. The step:

1. Calls `sm._RaiseStepFault(stepNum := nStep, stepName := sName, code := E_SM_Fault.StepTimeout, reason := '')`.
2. Writes `nNextStep := nStep + 1` so the sequence lands on the odd fault step.
3. Guards with an internal `_timeoutFired` flag so the transition only happens once per step activation.

On the HMI, the header ends up with:

- `faultCode     = 1` (`E_SM_Fault.StepTimeout`)
- `faultString   = 'Step Timeout'`
- `faultSource   = 'STEP_3004'`
- `faultReason   = 'Step 3004 [Inspect part]: Step Timeout'` (auto-built when `reason` is empty)

### 7.4.2 Author-supplied `step.RaiseFault(code, reason)`

When a step detects a condition that needs a specific fault code or a human-readable reason the library can't infer, call `RaiseFault` directly on the step instance:

```iecst
step3004(
    sm        := sm,
    nStep     := 3004,
    nNextStep := 3006,
    sName     := 'Inspect part',
    nTimeout  := 10
);

IF step3004.Execute AND NOT inpSensorOK THEN
    step3004.RaiseFault(
        code   := E_SM_Fault.StepUserFault,
        reason := 'Sensor A reports out-of-range reading 42.7 bar'
    );
END_IF;
```

What happens:

1. `FB_Step.RaiseFault` is a no-op if the step is not currently active (safe to call unconditionally).
2. It forwards to `sm._RaiseStepFault(stepNum, stepName, code, reason)`, which raises the fault via the base class's `_Raise(code, source, reason)` with:
   - `source = 'STEP_<N>'` (auto-built from `nStep`)
   - `reason = <your sentence>` (or the default `'Step <N> [<name>]: <resolved fault string>'` if you pass `''`)
3. It advances the sequence to `nStep + 1` — the odd fault step — so any per-step cleanup can run.

Guidelines:

- **Use a specific code when you have one.** If the condition is a wiring fault, raise `MyDev_Fault.BadWiring`, not `StepUserFault`. This keeps fault codes meaningful across runs and machines.
- **Use `StepUserFault` (`E_SM_Fault.StepUserFault`, code `3`) as the catch-all** when the sequence needs a fault but no device-specific enum applies.
- **Always pass a reason** when the code's resolved string isn't self-explanatory. The operator never sees the enum name; they see `faultString` and `faultReason`.
- **Multiple `RaiseFault` calls in one scan are safe.** `_Raise` is idempotent on `code` ([§2.3.2](2-Architecture.md#232-idempotent-raising)); only the first call pushes to the ring, later calls with the same code no-op.

### 7.4.3 Falling back to `OddStepReached`

If the sequence lands on an odd step *without* anyone raising a more specific fault (for example, a branch that explicitly targeted `3005`), `FB_StateMachine` auto-raises `OddStepReached` with `source = 'STEP_<odd>'` and a default reason. This keeps `Status.Faulted = TRUE` consistent with the odd-step convention even when no timeout or user fault triggered.

Because it only fires when no other fault is already active, a proper `StepTimeout` or `StepUserFault` always wins — no risk of overwriting the real reason with a generic one.

---

## 7.5 Permissives

### 7.5.1 State-level permissives (on FB_StateMachine)

Four permissive groups gate the main commands. Wire them in MAIN or in a dedicated permissive program:

| Group | Gates | Accessor |
|-------|-------|----------|
| `internalHomePerm` | `Home()` | `fbSM.internalHomePerm` |
| `internalStartPerm` | `Start()` | `fbSM.internalStartPerm` |
| `internalProceedPerm` | `Proceed()` | `fbSM.internalProceedPerm` |
| `internalAutoPerm` | `Home()`, `Start()`, `Proceed()` (shared auto permissive) | `fbSM.internalAutoPerm` |

```iecst
// Wire state-level permissives once, outside the sequences
fbStateMachine.internalHomePerm.MapInput(bitIndex := 0, inputValue := bDoorClosed);
fbStateMachine.internalStartPerm.MapInput(bitIndex := 0, inputValue := bMaterialLoaded);
fbStateMachine.internalStartPerm.MapInput(bitIndex := 1, inputValue := bRobotReady);
fbStateMachine.internalAutoPerm.MapInput(bitIndex := 0, inputValue := bEstopOK);
```

### 7.5.2 Step-level permissives (on FB_Step)

Map per-step conditions inside the `Execute` phase each scan. The active step automatically republishes its permissive data to `FB_StateMachine.StepPermCfg` and `FB_StateMachine.StepPermStatus` for HMI / OPC:

```iecst
IF step3002.Execute THEN
    step3002.MapPerm(nIndex := 0, sDescription := 'Cycle complete', bValue := tonProcess.Q);
    step3002.MapPerm(nIndex := 1, sDescription := 'No fault active', bValue := NOT bFault);
END_IF;
```

The step will not exit (will not enter `Exiting`) until all mapped permissives are `TRUE`.

---

## 7.6 Step Number Convention

| Range | State |
|-------|-------|
| 1000–1999 | HOMING |
| 2000–2999 | STOPPING |
| 3000–3999 | RUNNING |
| 4000–4999 | PAUSING |
| 5000–5999 | ABORTING |
| 6000–6999 | PROCEEDING |

Odd step numbers are fault steps. Even numbers are normal execution steps.
