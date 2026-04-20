# 3 Command Source Control

All commands in this library are issued through **RPC methods** on function blocks — there are no `pcmd` or `ocmd` input pins. Each method validates the request, checks permissions, and executes internally. The FB body handles only cyclic evaluation.

> **Navigation:** [← Architecture](2-Architecture.md) · [README / TOC](../README.md) · [RPC Method Response →](4-RPC-Method-Response.md)

---

## 3.1 E_Requester

Two control sources exist in the library:

| Value | Name | Description |
|-------|------|-------------|
| 0 | `PROG` | PLC program logic / automatic sequences |
| 1 | `OPERATOR` | Human operator via HMI / OPC UA |

`PROG` is the higher-priority source. When the system needs to lock out operator commands, the FB rejects all `OPERATOR` requests.

---

## 3.2 Source Locking

Each FB tracks whether operator requests are allowed via an internal `bSourceLockedToProg : BOOL` flag, controlled by the `LockSource` method:

```iecst
fbActuator.LockSource(bLock := TRUE);   // Lock to PROG only
fbActuator.LockSource(bLock := FALSE);  // Unlock for OPERATOR
```

When locked, any method call with `eRequester := E_Requester.OPERATOR` is rejected with `REJECTED_SOURCE_NOT_ALLOWED`.

### 3.2.1 Decision Matrix

| Source Locked? | Requester | Faulted? | Result |
|----------------|-----------|----------|--------|
| Yes | OPERATOR | * | `REJECTED_SOURCE_NOT_ALLOWED` |
| Yes | PROG | No | Continue to command validation |
| Yes | PROG | Yes | `REJECTED_FAULTED` (except Reset) |
| No | OPERATOR | No | Continue to command validation |
| No | OPERATOR | Yes | `REJECTED_FAULTED` (except Reset) |
| No | PROG | * | Continue to command validation |

---

## 3.3 F_ValidateRequester

All non-safety methods use `F_ValidateRequester` as the first validation step. Its signature is deliberately minimal — three inputs, no flags:

```iecst
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR
---
Advance := F_ValidateRequester(
    eRequester    := eRequester,
    bSourceLocked := bSourceLockedToProg,
    bFaulted      := IsFaulted()
);
IF Advance <> E_RpcMethodResponse.ACCEPTED THEN RETURN; END_IF;
// ... device-specific checks and execution
```

Parameters:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `eRequester` | `E_Requester` | Who is calling |
| `bSourceLocked` | `BOOL` | Is source locked to PROG |
| `bFaulted` | `BOOL` | Is the FB in a faulted state |

Safety commands (`Reset`, `Abort`, `Stop`) do **not** call `F_ValidateRequester` at all — they accept unconditionally. There is no "allow when faulted" or "skip source check" parameter because these commands need to work precisely when something is wrong.

---

## 3.4 Method Validation Chain

When a non-safety method is called, validation proceeds in this order:

1. **Source check** — if locked to PROG and requester is OPERATOR → `REJECTED_SOURCE_NOT_ALLOWED`
2. **Fault check** — if faulted → `REJECTED_FAULTED`
3. **State check** — wrong state → `REJECTED_WRONG_STATE` or `REJECTED_ALREADY_AT_TARGET`
4. **Permissive check** — permissives not met → `REJECTED_PERMISSIVE_NOT_MET`
5. **Execute** — perform command logic, call `_AcceptCommand(eRequester)` for book-keeping → `ACCEPTED`

### 3.4.1 Method Pattern

```iecst
{attribute 'TcRpcEnable' := '1'}
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR

// 1. Source + fault validation
Advance := F_ValidateRequester(
    eRequester    := eRequester,
    bSourceLocked := bSourceLockedToProg,
    bFaulted      := IsFaulted()
);
IF Advance <> E_RpcMethodResponse.ACCEPTED THEN RETURN; END_IF;

// 2. State check
IF currentState = E_TwoPosActuator_State.Advanced
   OR currentState = E_TwoPosActuator_State.Advancing THEN
    Advance := E_RpcMethodResponse.REJECTED_ALREADY_AT_TARGET;
    RETURN;
END_IF;

// 3. Permissive check
IF NOT advancePermissives.sts.OK THEN
    Advance := E_RpcMethodResponse.REJECTED_PERMISSIVE_NOT_MET;
    RETURN;
END_IF;

// 4. Execute + book-keep
currentState := E_TwoPosActuator_State.Advancing;
advanceTimer(IN := FALSE);
_AcceptCommand(eRequester := eRequester);
Advance := E_RpcMethodResponse.ACCEPTED;
```

### 3.4.2 Default Requester

`eRequester` defaults to `E_Requester.PROG`, so PLC sequence code can call methods without specifying it:

```iecst
fbActuator.Advance();                                    // PROG (default)
response := fbActuator.Advance(E_Requester.OPERATOR);   // OPERATOR (from HMI/OPC)
```

---

## 3.5 FB_TwoPosActuator Methods

| Method | Validated | Description |
|--------|-----------|-------------|
| `Advance(eRequester)` | `F_ValidateRequester` + state + permissives | Enter Advancing state |
| `Retract(eRequester)` | `F_ValidateRequester` + state + permissives | Enter Retracting state |
| `Abort(eRequester)` | Always accepted | De-energize all valves, enter Undefined |
| `Reset(eRequester)` | Always accepted | Clear active fault, return to Undefined for re-evaluation |
| `LockSource(bLock)` | Always accepted | Lock or unlock source to PROG |

---

## 3.6 FB_StateMachine Methods

| Method | Validated | Description |
|--------|-----------|-------------|
| `Start(eRequester)` | `F_ValidateRequester` + state + permissives | Must be Ready; check start perms and interlocks |
| `Home(eRequester)` | `F_ValidateRequester` + state + permissives | Must be Stopped; check home perms and interlocks |
| `Stop(eRequester)` | Always accepted | Transition to Stopping |
| `Abort(eRequester)` | Always accepted | Transition to Aborting |
| `Pause(eRequester)` | `F_ValidateRequester` + state | Must be Running |
| `Proceed(eRequester)` | `F_ValidateRequester` + state + permissives | Must be Paused; check proceed perms and interlocks |
| `Retry(eRequester)` | Always accepted | Triggers retry for current step |
| `Reset(eRequester)` | Always accepted | Clears fault, returns to Ready |
| `LockSource(bLock)` | Always accepted | Lock or unlock source to PROG |

> **Note:** Safety commands (`Stop`, `Abort`, `Reset`, `Retry`) bypass `F_ValidateRequester` entirely — an emergency stop must never be rejected.

---

## 3.7 Migration from pcmd/ocmd Pattern

| Old Pattern | New Pattern |
|-------------|-------------|
| `fbActuator.pcmdAdvance := TRUE` | `fbActuator.Advance()` |
| `fbActuator.ocmdAdvance := TRUE` | `fbActuator.Advance(E_Requester.OPERATOR)` via OPC UA |
| `fbActuator.inWorkingMode := TRUE` | `fbActuator.LockSource(bLock := TRUE)` |
| `IF HMI.ocmd.Start THEN ...` | `fbSM.Start(E_Requester.OPERATOR)` via OPC UA RPC |
| Check `Status.xxx` after command | Check method return value immediately |

---

## 3.8 Design Decisions

- **No ADVANCED source** — two sources (`PROG` / `OPERATOR`) are sufficient. The enum can be extended.
- **No manual override distinction** — the operator either has authority or doesn't.
- **Safety commands always accept** — `Reset`, `Abort`, and `Stop` don't call `F_ValidateRequester` at all. Reset is the exit from fault; Abort and Stop must fire regardless of source lock.
- **Minimal validator** — `F_ValidateRequester` has three inputs (requester, source lock, fault). Commands that need to bypass the gate simply don't call it rather than carrying feature flags.
- **Methods hold the logic** — eliminates scan delay between flag and execution.
- **Default requester is PROG** — PLC code should not have to specify it on every call.
