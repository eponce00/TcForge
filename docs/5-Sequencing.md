# 5 Sequencing

The sequencing module provides `FB_StateMachine` and `FB_Step` — the two blocks you need to drive any multi-step automatic process. This document covers the state model, how sequences are structured, and how to wire permissives.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [Command Source Control](2-Command-Source-Control.md) · [RPC Method Response](3-RPC-Method-Response.md) · [HMI Integration](4-HMI-Integration.md) · [Persistent Variables →](6-Persistent-Variables.md)

---

## 5.1 State Model (E_SM_State)

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

### 5.1.1 Transition Graph

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

### 5.1.2 Distinguishing READY sub-states

`READY` is entered from both `HOMING` (first home) and `RUNNING` (cycle complete). Use `Status.LastState` when you need to tell them apart:

```iecst
IF fbSM.Status.State = E_SM_State.READY AND fbSM.Status.LastState = E_SM_State.RUNNING THEN
    // just finished a production cycle
END_IF;
```

`AutoCycleRequest` and the auto-run logic already use this internally to only auto-restart after a completed cycle, not after homing.

### 5.1.3 Fault indication

`Status.Faulted` is `TRUE` whenever the current step number is odd (`CurrentStep MOD 2 <> 0`). An abort lands in `STOPPED` with `Status.LastState = E_SM_State.ABORTING`, giving the HMI enough context to show "stopped after abort" without needing a separate state.

---

## 5.2 FB_StateMachine

### 5.2.1 Instantiation

```iecst
fbStateMachine : FB_StateMachine;
```

Minimum call in the cyclic program:

```iecst
fbStateMachine(
    EnableIn    := TRUE,
    cfgAutoRun  := FALSE
);
```

| Input | Purpose |
|-------|---------|
| `EnableIn` | Enables the FB. When `FALSE` all command requests are cleared. |
| `cfgAutoRun` | Automatically re-starts a new cycle when `READY` after a completed run and start permissives are met. |

### 5.2.2 Key outputs

| Output | Type | Description |
|--------|------|-------------|
| `Status` | `ST_SM_Status` | State, last state, faulted flag, blocked/starved, ready flags |
| `StepInfo` | `ST_SM_StepInfo` | CurrentStep, CurrentStepName, NextStep, StepTimerSeconds |
| `HomePermOK`, `StartPermOK`, `ProceedPermOK`, `AutoPermOK` | `BOOL` | Flat perm-OK flags directly on the FB output |
| `StepPermCfg` | `ST_Permissive_Config` | Active step's permissive config (mirrored from FB_Step) |
| `StepPermStatus` | `ST_Permissive_Status` | Active step's permissive status (mirrored from FB_Step) |
| `ConditionStatus` | `ST_SM_Conditions` | OEE-level blocked / starved condition codes |

---

## 5.3 Writing a Sequence

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

### 5.3.1 Step Lifecycle

`FB_Step` provides three one-scan phases:

| Phase | Fires when | Typical use |
|-------|-----------|-------------|
| `Entry` | First scan the step becomes active | Command actuators, reset timers |
| `Execute` | Every scan while active | Monitor feedback, call `MapPerm` |
| `Exiting` | One scan when all permissives pass and `nNextStep` is set | Cleanup, confirm outputs |

After `Exiting`, `FB_Step` hands `nNextStep` to the state machine and the sequence advances.

### 5.3.2 Minimal step example

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

### 5.3.3 Dynamic branching

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

### 5.3.4 Completing a sequence

Set `nNextStep := 0` on the last step. The state machine detects step `0` at the end of an active sequence and transitions to the next waiting state automatically:

```iecst
step3008(
    sm        := sm,
    nStep     := 3008,
    nNextStep := 0,       // sequence complete
    sName     := 'Unload part'
);
```

### 5.3.5 Fault steps (odd step numbers)

Fault steps use the odd-step convention. The step directly above the normal step serves as its fault landing. `Status.Faulted` derives from `CurrentStep MOD 2 <> 0`:

```
3000 — normal step
3001 — fault step (e.g. timeout from step 3000)
3002 — next normal step
```

`FB_Step` automatically advances to `nStep + 1` on timeout expiry.

---

## 5.4 Permissives

### 5.4.1 State-level permissives (on FB_StateMachine)

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

### 5.4.2 Step-level permissives (on FB_Step)

Map per-step conditions inside the `Execute` phase each scan. The active step automatically republishes its permissive data to `FB_StateMachine.StepPermCfg` and `FB_StateMachine.StepPermStatus` for HMI / OPC:

```iecst
IF step3002.Execute THEN
    step3002.MapPerm(nIndex := 0, sDescription := 'Cycle complete', bValue := tonProcess.Q);
    step3002.MapPerm(nIndex := 1, sDescription := 'No fault active', bValue := NOT bFault);
END_IF;
```

The step will not exit (will not enter `Exiting`) until all mapped permissives are `TRUE`.

---

## 5.5 Step Number Convention

| Range | State |
|-------|-------|
| 1000–1999 | HOMING |
| 2000–2999 | STOPPING |
| 3000–3999 | RUNNING |
| 4000–4999 | PAUSING |
| 5000–5999 | ABORTING |
| 6000–6999 | PROCEEDING |

Odd step numbers are fault steps. Even numbers are normal execution steps.
