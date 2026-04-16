# 3 RPC Method Response

All RPC methods across the library return `E_RpcMethodResponse`, a standardized enumeration that tells the caller whether a command was accepted or rejected — and why.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [Command Source Control](2-Command-Source-Control.md) · [HMI Integration →](4-HMI-Integration.md)

---

## 3.1 E_RpcMethodResponse

The enum uses `{attribute 'to_string'}` so `TO_STRING(response)` returns the symbolic name (e.g. `'REJECTED_FAULTED'`).

| Value | Name | Description |
|-------|------|-------------|
| 0 | `ACCEPTED` | Command accepted and will be executed |
| 11 | `REJECTED_SOURCE_NOT_ALLOWED` | Source locked to PROG; operator request rejected |
| 20 | `REJECTED_WRONG_STATE` | FB is not in the required state for this command |
| 21 | `REJECTED_FAULTED` | FB is in a fault state; reset first |
| 23 | `REJECTED_ALREADY_AT_TARGET` | Already at the requested position/state |
| 50 | `REJECTED_PERMISSIVE_NOT_MET` | A required permissive group is not OK |
| 51 | `REJECTED_INTERLOCKED` | An interlock condition is preventing the command |
| 100 | `REJECTED_UNKNOWN` | Fallback when no other code applies |

### 3.1.1 Range Convention

| Range | Category |
|-------|----------|
| 0 | Success |
| 10–19 | Source / Authorization |
| 20–29 | State |
| 50–59 | Permissive / Interlock |
| 100 | Default |

Ranges 30–39 (Manual Override), 40–49 (Configuration), 60–69 (Output/Hardware), 70–79 (Propagation), 80–89 (Redundancy) are reserved for future use.

---

## 3.2 Method Inventory

### 3.2.1 FB_TwoPosActuator

| Method | Validation | Possible Responses |
|--------|-----------|-------------------|
| `Advance()` | Not faulted, not already advanced/advancing, advance permissives OK | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `Retract()` | Not faulted, not already retracted/retracting, retract permissives OK | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `AllOff()` | Always accepted (skip source check) | `ACCEPTED` |
| `Reset()` | Must be faulted | `ACCEPTED`, `REJECTED_WRONG_STATE` |
| `LockSource()` | Always accepted | `ACCEPTED` |

### 3.2.2 FB_StateMachine

| Method | Validation | Possible Responses |
|--------|-----------|-------------------|
| `Start()` | Must be Homed or Complete, start perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Home()` | Must be Stopped or Aborted, home perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Proceed()` | Must be Paused, proceed perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Pause()` | Must be Running | `ACCEPTED`, `REJECTED_WRONG_STATE` |
| `Stop()` | Always accepted (safety command) | `ACCEPTED` |
| `Abort()` | Always accepted (safety command) | `ACCEPTED` |
| `Retry()` | Always accepted | `ACCEPTED` |
| `LockSource()` | Always accepted | `ACCEPTED` |

---

## 3.3 OPC UA Usage

RPC methods are exposed via `{attribute 'TcRpcEnable' := '1'}`. An OPC UA client calls the method and receives the `E_RpcMethodResponse` return value in one round-trip.

### 3.3.1 OPC UA Client Example (Pseudocode)

```python
result = call_method("PLC1.MAIN.fbCylinder01.Advance")
if result != 0:
    print(f"Command rejected: {result}")  # e.g. 50 = REJECTED_PERMISSIVE_NOT_MET
```

### 3.3.2 PLC Caller Example

```iecst
// From sequence code (eRequester defaults to PROG)
eResult := fbCylinder.Advance();
IF eResult <> E_RpcMethodResponse.ACCEPTED THEN
    // Handle rejection — log, alarm, retry
END_IF;

// With explicit source
eResult := fbStateMachine.Start(eRequester := E_Requester.PROG);
```

---

## 3.4 Design Decisions

- **Stop and Abort always accept** — safety-critical commands must never be blocked.
- **Retry always accepts** — the retry mechanism handles its own edge detection internally.
- **Advance/Retract pre-check permissives** — gives immediate feedback rather than accepting and then faulting.
- **Methods execute immediately** — no scan-cycle delay between request and action.
