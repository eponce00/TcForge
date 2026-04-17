# 2 Command Source Control

All commands in this library are issued through **RPC methods** on function blocks — there are no `pcmd` or `ocmd` input pins. Each method validates the request, checks permissions, and executes internally. The FB body handles only cyclic evaluation.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [RPC Method Response →](3-RPC-Method-Response.md) · [HMI Integration →](4-HMI-Integration.md) · [Sequencing →](5-Sequencing.md) · [Architecture →](7-Architecture.md) · [I/O Binding →](8-IO-Binding.md)

---

## 2.1 E_Requester

Two control sources exist in the library:

| Value | Name | Description |
|-------|------|-------------|
| 0 | `PROG` | PLC program logic / automatic sequences |
| 1 | `OPERATOR` | Human operator via HMI / OPC UA |

`PROG` is the higher-priority source. When the system needs to lock out operator commands, the FB rejects all `OPERATOR` requests.

---

## 2.2 Source Locking

Each FB tracks whether operator requests are allowed via an internal `bSourceLockedToProg : BOOL` flag, controlled by the `LockSource` method:

```iecst
fbActuator.LockSource(bLock := TRUE);   // Lock to PROG only
fbActuator.LockSource(bLock := FALSE);  // Unlock for OPERATOR
```

When locked, any method call with `eRequester := E_Requester.OPERATOR` is rejected with `REJECTED_SOURCE_NOT_ALLOWED`.

### 2.2.1 Decision Matrix

| Source Locked? | Requester | Faulted? | Result |
|----------------|-----------|----------|--------|
| Yes | OPERATOR | * | `REJECTED_SOURCE_NOT_ALLOWED` |
| Yes | PROG | No | Continue to command validation |
| Yes | PROG | Yes | `REJECTED_FAULTED` (except Reset) |
| No | OPERATOR | No | Continue to command validation |
| No | OPERATOR | Yes | `REJECTED_FAULTED` (except Reset) |
| No | PROG | * | Continue to command validation |

---

## 2.3 F_ValidateRequester

All methods use `F_ValidateRequester` as the first validation step:

```iecst
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR
---
Advance := F_ValidateRequester(eRequester, bSourceLockedToProg, faultLatched, FALSE, FALSE);
IF Advance <> E_RpcMethodResponse.ACCEPTED THEN RETURN; END_IF;
// ... device-specific checks and execution
```

Parameters:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `eRequester` | `E_Requester` | Who is calling |
| `bSourceLocked` | `BOOL` | Is source locked to PROG |
| `bFaulted` | `BOOL` | Is the FB in a faulted state |
| `bAllowWhenFaulted` | `BOOL` | `TRUE` for Reset-type methods |
| `bSkipSourceCheck` | `BOOL` | `TRUE` for safety commands (Abort, Stop) |

---

## 2.4 Method Validation Chain

When a method is called, validation proceeds in this order:

1. **Source check** — if locked to PROG and requester is OPERATOR → `REJECTED_SOURCE_NOT_ALLOWED`
2. **Fault check** — if faulted and not allowed when faulted → `REJECTED_FAULTED`
3. **State check** — wrong state → `REJECTED_WRONG_STATE` or `REJECTED_ALREADY_AT_TARGET`
4. **Permissive check** — permissives not met → `REJECTED_PERMISSIVE_NOT_MET`
5. **Execute** — perform command logic → `ACCEPTED`

### 2.4.1 Method Pattern

```iecst
{attribute 'TcRpcEnable' := '1'}
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR

// 1. Source + fault validation
Advance := F_ValidateRequester(eRequester, bSourceLockedToProg, faultLatched, FALSE, FALSE);
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

// 4. Execute
currentState := E_TwoPosActuator_State.Advancing;
advanceTimer(IN := FALSE);
Advance := E_RpcMethodResponse.ACCEPTED;
```

### 2.4.2 Default Requester

`eRequester` defaults to `E_Requester.PROG`, so PLC sequence code can call methods without specifying it:

```iecst
fbActuator.Advance();                                    // PROG (default)
response := fbActuator.Advance(E_Requester.OPERATOR);   // OPERATOR (from HMI/OPC)
```

---

## 2.5 FB_TwoPosActuator Methods

| Method | Source Checked | Description |
|--------|---------------|-------------|
| `Advance(eRequester)` | Yes | Validate permissives, state, source; enter Advancing state |
| `Retract(eRequester)` | Yes | Validate permissives, state, source; enter Retracting state |
| `Abort(eRequester)` | Skip source | Always accepted. De-energize all valves, enter Undefined |
| `Reset(eRequester)` | Skip source | Always accepted. Clear fault history, return to Undefined for re-evaluation |
| `LockSource(bLock)` | No | Lock or unlock source to PROG |

---

## 2.6 FB_StateMachine Methods

| Method | Source Checked | Description |
|--------|---------------|-------------|
| `Start(eRequester)` | Yes | Must be Ready; check start perms and interlocks |
| `Home(eRequester)` | Yes | Must be Stopped; check home perms and interlocks |
| `Stop(eRequester)` | No (safety) | Always accepted; transition to Stopping |
| `Abort(eRequester)` | No (safety) | Always accepted; transition to Aborting |
| `Pause(eRequester)` | Yes | Must be Running |
| `Proceed(eRequester)` | Yes | Must be Paused; check proceed perms and interlocks |
| `Retry(eRequester)` | Yes | Always accepted; triggers retry for current step |
| `LockSource(bLock)` | No | Lock or unlock source to PROG |

> **Note:** `Stop` and `Abort` bypass source checks — an emergency stop must never be rejected.

---

## 2.7 Migration from pcmd/ocmd Pattern

| Old Pattern | New Pattern |
|-------------|-------------|
| `fbActuator.pcmdAdvance := TRUE` | `fbActuator.Advance()` |
| `fbActuator.ocmdAdvance := TRUE` | `fbActuator.Advance(E_Requester.OPERATOR)` via OPC UA |
| `fbActuator.inWorkingMode := TRUE` | `fbActuator.LockSource(bLock := TRUE)` |
| `IF HMI.ocmd.Start THEN ...` | `fbSM.Start(E_Requester.OPERATOR)` via OPC UA RPC |
| Check `Status.xxx` after command | Check method return value immediately |

---

## 2.8 Design Decisions

- **No ADVANCED source** — two sources (`PROG` / `OPERATOR`) are sufficient. The enum can be extended.
- **No manual override distinction** — the operator either has authority or doesn't.
- **Safety commands always accept** — `Stop` and `Abort` skip all validation.
- **Reset allowed when faulted** — by definition, Reset is the exit from fault. It still checks source lock.
- **Methods hold the logic** — eliminates scan delay between flag and execution.
- **Default requester is PROG** — PLC code should not have to specify it on every call.
