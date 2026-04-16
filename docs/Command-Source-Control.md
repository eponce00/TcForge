# Command Source Control Pattern

## Overview

All commands in this library are issued through **RPC methods** on function blocks — there are no `pcmd` or `ocmd` input pins. Each method acts as a self-contained API call that validates the request, checks permissions, and executes the command logic internally. The FB body handles only cyclic evaluation (timers, feedback monitoring, state persistence); all command entry points are methods.

Every command method accepts an `eRequester` parameter of type `E_Requester` indicating who is making the request. The FB evaluates whether that requester is currently allowed to issue commands, and returns an `E_RpcMethodResponse` indicating acceptance or a specific rejection reason.

## E_Requester

Two control sources exist in the library:

| Value | Name | Description |
|-------|------|-------------|
| 0 | `PROG` | PLC program logic / automatic sequences |
| 1 | `OPERATOR` | Human operator via HMI / OPC UA |

`PROG` is the higher-priority source. When the system needs to lock out operator commands (e.g. during an emergency shutdown sequence, or while an automatic sequence is running), the FB's source is locked to `PROG` and all `OPERATOR` requests are rejected.

## Source Control Rules

Each FB tracks whether operator requests are allowed via an internal `bSourceLockedToProg : BOOL` flag.

### Request Validation Order

When a method is called, validation proceeds in this order:

1. **Interlock check** — if the FB's interlocks are not OK, reject with `REJECTED_INTERLOCKED`
2. **Fault check** — if the FB is faulted, reject with `REJECTED_FAULTED` (exception: `Reset()` is allowed when faulted)
3. **Source lock check** — if `bSourceLockedToProg = TRUE` and `eSource = OPERATOR`, reject with `REJECTED_SOURCE_NOT_ALLOWED`
4. **Command-specific validation** — wrong state, already at target, permissives not met, etc.
5. **Execute** — perform the command logic and return `ACCEPTED`

### Source Lock

The source can be locked to `PROG` by calling `LockSource(bLock : BOOL)` from program code. When locked:

- All `OPERATOR` requests are rejected with `REJECTED_SOURCE_NOT_ALLOWED`
- All `PROG` requests proceed through normal validation
- The lock is typically set during emergency sequences, critical automatic operations, or startup/shutdown

This replaces the old `inWorkingMode` input. Instead of a binary auto/manual mode toggle, any method call declares its source and the FB decides whether to honor it.

### Decision Matrix

| Source Locked to PROG? | Requesting Source | FB Faulted? | Result |
|------------------------|-------------------|-------------|--------|
| Yes | OPERATOR | * | `REJECTED_SOURCE_NOT_ALLOWED` |
| Yes | PROG | No | Continue to command validation |
| Yes | PROG | Yes | `REJECTED_FAULTED` (except Reset) |
| No | OPERATOR | No | Continue to command validation |
| No | OPERATOR | Yes | `REJECTED_FAULTED` (except Reset) |
| No | PROG | No | Continue to command validation |
| No | PROG | Yes | `REJECTED_FAULTED` (except Reset) |

## Method Pattern

Every command method follows this structure:

```iecst
{attribute 'TcRpcEnable' := '1'}
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR

// 1. Interlock check
IF NOT advancePermissives.sts.OK THEN
    Advance := E_RpcMethodResponse.REJECTED_PERMISSIVE_NOT_MET;
    RETURN;
END_IF;

// 2. Fault check
IF faultLatched THEN
    Advance := E_RpcMethodResponse.REJECTED_FAULTED;
    RETURN;
END_IF;

// 3. Source check
IF bSourceLockedToProg AND eRequester = E_Requester.OPERATOR THEN
    Advance := E_RpcMethodResponse.REJECTED_SOURCE_NOT_ALLOWED;
    RETURN;
END_IF;

// 4. State check
IF currentState = E_TwoPosActuator_State.Advanced
   OR currentState = E_TwoPosActuator_State.Advancing THEN
    Advance := E_RpcMethodResponse.REJECTED_ALREADY_AT_TARGET;
    RETURN;
END_IF;

// 5. Execute
IO.outValveAdvance := TRUE;
IO.outValveRetract := FALSE;
currentState := E_TwoPosActuator_State.Advancing;
advanceTimer(IN := FALSE); // Reset timer for fresh start
Advance := E_RpcMethodResponse.ACCEPTED;
```

Key points:
- The method **contains the command logic**, not just a flag toggle
- `eSource` defaults to `PROG` so PLC callers can omit it: `fbCylinder.Advance()`
- OPC UA calls arrive as `OPERATOR` by default (the OPC UA server passes the source)
- The return value tells the caller exactly why a command was rejected

## FB Body Role

With methods holding all command logic, the FB body is responsible only for:

- **Cyclic monitoring** — timer evaluation, feedback edge detection, fault detection
- **State persistence** — the state machine stays in its current state; only methods cause transitions
- **Status generation** — updating `sts` output with current state, strings, one-shots
- **Permissive evaluation** — running FB_Permissives instances each cycle

The body does **not** read command inputs, process mode selection, or initiate state transitions. All transitions originate from method calls.

## FB_TwoPosActuator Methods

| Method | Source Checked | Description |
|--------|---------------|-------------|
| `Advance(eRequester)` | Yes | Validate permissives, state, source; energize advance valve and enter Advancing state |
| `Retract(eRequester)` | Yes | Validate permissives, state, source; energize retract valve and enter Retracting state |
| `AllOff(eRequester)` | Yes | De-energize all valves |
| `Reset(eRequester)` | Yes (but allowed when faulted) | Clear fault latch if safe conditions are met |
| `LockSource(bLock)` | No (always PROG) | Lock or unlock source to PROG |

## FB_StateMachine Methods

| Method | Source Checked | Description |
|--------|---------------|-------------|
| `Start(eRequester)` | Yes | Validate state (must be Homed/Complete), start perms, auto interlocks; transition to Running |
| `Home(eRequester)` | Yes | Validate state (must be Stopped/Aborted), home perms, auto interlocks; transition to Homing |
| `Stop(eRequester)` | No (safety command) | Always accepted; transition to Stopping |
| `Abort(eRequester)` | No (safety command) | Always accepted; transition to Aborting |
| `Pause(eRequester)` | Yes | Validate state (must be Running); transition to Pausing |
| `Proceed(eRequester)` | Yes | Validate state (must be Paused), proceed perms, auto interlocks; transition to Proceeding |
| `Retry(eRequester)` | Yes | Trigger retry signal for current step |
| `LockSource(bLock)` | No (always PROG) | Lock or unlock source to PROG |

> **Note:** `Stop` and `Abort` bypass source checks because they are safety-critical — an emergency stop must never be rejected.

## E_RpcMethodResponse

All methods return a standardized response code. See [RPC Method Response](./RPC-Method-Response.md) for the full specification.

Callers check the return value to determine outcome:

```iecst
// From PLC program (eSource defaults to PROG)
eResult := fbCylinder.Advance();
IF eResult <> E_RpcMethodResponse.ACCEPTED THEN
    // Handle rejection — log, alarm, retry, etc.
END_IF;

// From sequence program with explicit source
eResult := fbStateMachine.Start(eRequester := E_Requester.PROG);
```

OPC UA clients receive the return value directly from the RPC call, enabling immediate feedback without polling.

## Migration from pcmd/ocmd Pattern

| Old Pattern | New Pattern |
|-------------|-------------|
| `fbActuator.pcmdAdvance := TRUE` | `fbActuator.Advance()` or `fbActuator.Advance(E_Requester.PROG)` |
| `fbActuator.ocmdAdvance := TRUE` | `fbActuator.Advance(E_Requester.OPERATOR)` (via OPC UA RPC) |
| `fbActuator.inWorkingMode := TRUE` | `fbActuator.LockSource(bLock := TRUE)` to lock out operator |
| `IF Commands.Start THEN ...` | `fbSM.Start(eRequester := E_Requester.PROG)` |
| `IF HMI.ocmd.Start THEN ...` | `fbSM.Start(eRequester := E_Requester.OPERATOR)` (via OPC UA RPC) |
| Check `Status.xxx` after command | Check return value of method call |

## Design Decisions

- **No ADVANCED source** — our library does not have an optimization layer; two sources (PROG/OPERATOR) are sufficient. The enum can be extended if needed.
- **No manual override** — we do not distinguish between "operator command" and "operator manual override." The operator either has authority to command (source not locked) or doesn't. This keeps the model simple.
- **Safety commands always accept** — Stop and Abort must never be blocked. They skip source validation entirely.
- **Reset allowed when faulted** — by definition, Reset is the way out of a fault state. It still checks source lock.
- **Methods hold the logic** — this eliminates the scan-delay between setting a flag and the body processing it. Commands take effect immediately in the calling scan.
- **Default requester is PROG** — PLC code should not have to specify `E_Requester.PROG` on every call. The default parameter handles this.
