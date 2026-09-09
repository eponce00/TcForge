# 7 Sequencing

`FB_StateMachine` owns machine state, current/next step, a step timer and device
faults. `FB_Step` owns each step's Entry, Execute and Exiting lifecycle. Use even
steps for work; the following odd step is a recovery location. State ranges are:
HOMING 1000–1999, STOPPING 2000–2999, RUNNING 3000–3999, PAUSING 4000–4999,
ABORTING 5000–5999 and PROCEEDING 6000–6999.

## Commands

| Command | Valid state and result |
|---|---|
| Home | STOPPED → HOMING, when home/auto permissions and running interlocks are good |
| Start | READY → RUNNING with start/auto permissions and no fault |
| Pause | RUNNING → PAUSING; completion enters PAUSED |
| Proceed | PAUSED → PROCEEDING; completion re-enters the paused step |
| Stop | READY → STOPPED; other operational states → STOPPING; does not downgrade ABORTING |
| Abort | Any operational state → ABORTING; cancels queued Home even before movement starts |
| Reset | STOPPED only, no active submodule fault and good running interlocks; failed Abort also requires `inpShutdownConfirmed` |
| Retry | Recorded ordinary-step failure at its odd recovery step, including application fault codes; validates source/interlocks and re-enters the previous even step |

Reset accepts either valid requester regardless of source lock; an invalid requester is rejected before recovery state changes.

Commands are consumed once; Abort outranks Stop and ordinary commands. A scan makes
at most one machine-state transition. Running interlocks and submodule faults
request Abort. Shutdown steps still execute while the triggering fault remains;
completion enters STOPPED without hiding the fault. Ordinary steps stop executing
on a fault. `Status.AtRecoveryStep` is separate from `Status.Faulted`.

Auto-run is an explicit `cfgAutoRun` opt-in. A completed RUNNING cycle may restart
from READY only with good permissions/interlocks and no fault. The example defaults
to manual operation. Rejected Start commands do not become latent start requests.

## Conditions and call order

Use `cfgHome`, `cfgStart`, `cfgProceed`, `cfgAuto`, `cfgRunning` to configure required
and bypassable masks before operation. Feed values using MapHomeCondition,
MapStartCondition, MapProceedCondition, MapAutoCondition and MapRunningIntlk before
the state-machine cyclic call. Missing required interlocks latch; restore fresh
inputs, ResetRunningIntlk, then Reset the stopped machine.

Call the state machine before the steps. Call every FB_Step instance once each scan, including inactive ones. The following state-machine call checks that the active even step was called exactly once. A missing implementation or duplicate call raises a distinct configuration fault. Detection occurs on the next state-machine call; it does not undo application actions already issued that scan. Entry fires
once, Execute maps completion conditions, Exiting runs cleanup once, and Advance
sets the next step. `nNextStep := 0` completes the sequence. Mappings made during
Execute are evaluated on the next step call. Configure `nRequired` independently
so a missing MapPerm call cannot silently satisfy a required completion condition.

```iecst
step(sm := sm, nStep := 3000, nNextStep := 3002,
     nRequired := ULINT#3, nTimeout := 10, sName := 'Wait for device');
IF step.Execute THEN
    step.MapPerm(nIndex := 0, sDescription := 'In position', bValue := inPosition);
    step.MapPerm(nIndex := 1, sDescription := 'Quality good', bValue := qualityGood);
END_IF;
```

## Step boundaries and failed shutdown

A destination must be zero (complete the state) or a different even step in the
current state's range. Negative, odd, cross-state and self destinations fault before
lifecycle outputs execute. Loops use two or more work steps. A valid number with
no corresponding called instance faults when selected. Keep each instance's
`nStep` identity fixed; configure destinations dynamically when branching.

`nTimeout = 0` disables timing. Valid positive values are 1–356400 seconds (99 hours), matching the step timer range; values outside that range are invalid. Positive timeouts
cover the entire active lifecycle, including Entry and Exiting, and expire at
`elapsed >= timeout`. A failure suppresses that step's lifecycle outputs immediately. Nonpositive application fault codes normalize to `StepUserFault`.
Application code must also gate its final physical outputs on current fault and
quality conditions; clearing lifecycle flags cannot revoke commands already issued.

| Failure location | Result on the next state-machine call | Recovery |
|---|---|---|
| Homing, Running, Pausing, Proceeding | Following odd recovery step; normal work inhibited | Explicit Retry with healthy interlocks/submodules, or Stop/Abort |
| Stopping | Aborting, first step 5000; original fault retained | Execute the application's Abort sequence |
| Aborting | Stopped with latched `ShutdownFailed`; work inhibited | Application confirms physical shutdown through `inpShutdownConfirmed`, then explicit Reset |

`Status.FailedStep` identifies the failed step until Reset. The fault history retains
individual failure diagnostics, including escalation. `STOPPED` alone does not
prove physical shutdown. `inpShutdownConfirmed` defaults false and must be derived
from appropriate application feedback, not merely the state enum or output command.
Normal successful Stop/Abort completion retains the initiating fault until Reset.
A failed shutdown is not retried through an odd step.

Stop/Abort sequences must implement actual output shutdown and confirmation in a
machine application. The example is not a commissioned machine safety sequence.

A state transition publishes the new state and its first step in the same cyclic
call. Abort from RUNNING therefore publishes ABORTING with step 5000 immediately;
a pending running-step advance cannot delay or replace the abort entry step.
