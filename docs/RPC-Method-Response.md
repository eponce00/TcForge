# RPC Method Response Pattern

## Overview

All RPC methods across the library return `E_RpcMethodResponse`, a standardized enumeration that tells the caller whether a command was accepted or rejected — and why. This provides a consistent, machine-readable mechanism for HMI, OPC UA clients, and supervisory systems to understand command outcomes without parsing strings or polling status flags.

The enum uses `{attribute 'to_string'}` so `TO_STRING(response)` returns the symbolic name (e.g. `'REJECTED_FAULTED'`) rather than the numeric value.

## E_RpcMethodResponse

| Value | Name | Description |
|-------|------|-------------|
| 0 | `ACCEPTED` | Command accepted and will be executed |
| 20 | `REJECTED_WRONG_STATE` | FB is not in the required state for this command |
| 21 | `REJECTED_FAULTED` | FB is in a fault state; reset first |
| 23 | `REJECTED_ALREADY_AT_TARGET` | Already at the requested position/state |
| 50 | `REJECTED_PERMISSIVE_NOT_MET` | A required permissive group is not OK |
| 51 | `REJECTED_INTERLOCKED` | An interlock condition is preventing the command |
| 100 | `REJECTED_UNKNOWN` | Fallback when no other code applies |

### Range Convention

| Range | Category |
|-------|----------|
| 0 | Success |
| 20–29 | State |
| 50–59 | Permissive / Interlock |
| 100 | Default |

Additional ranges (10–19 Source/Authorization, 30–39 Manual Override, 40–49 Configuration, 60–69 Output/Hardware, 70–79 Propagation, 80–89 Redundancy) are reserved for future use. Add values as needed when the library grows.

## Method Inventory

### FB_TwoPosActuator

| Method | Validation | Possible Responses |
|--------|-----------|-------------------|
| `Advance()` | Not faulted, not already advanced/advancing, advance permissives OK | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `Retract()` | Not faulted, not already retracted/retracting, retract permissives OK | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `AllOff()` | Always accepted | `ACCEPTED` |
| `Reset()` | Must be faulted | `ACCEPTED`, `REJECTED_WRONG_STATE` |

### FB_StateMachine

| Method | Validation | Possible Responses |
|--------|-----------|-------------------|
| `Start()` | Must be Homed or Complete, start perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Home()` | Must be Stopped or Aborted, home perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Proceed()` | Must be Paused, proceed perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Pause()` | Must be Running | `ACCEPTED`, `REJECTED_WRONG_STATE` |
| `Stop()` | Always accepted (safety command) | `ACCEPTED` |
| `Abort()` | Always accepted (safety command) | `ACCEPTED` |
| `Retry()` | Always accepted | `ACCEPTED` |

## OPC UA Usage

RPC methods are exposed via `{attribute 'TcRpcEnable' := '1'}`. An OPC UA client calls the method and receives the `E_RpcMethodResponse` return value in one round-trip. Because the enum has `{attribute 'to_string'}`, clients can also use `TO_STRING()` on the PLC side to generate human-readable rejection reasons if needed.

### Example (OPC UA Client Pseudocode)

```
result = call_method("PLC1.MAIN.fbCylinder01.Advance")
if result != 0:
    print(f"Command rejected: {result}")  // e.g. 50 = REJECTED_PERMISSIVE_NOT_MET
```

## Design Decisions

- **Stop and Abort always accept** — these are safety-critical commands that should never be blocked by validation logic.
- **Retry always accepts** — the retry mechanism handles its own edge detection internally.
- **Advance/Retract pre-check permissives** — gives immediate feedback to the caller rather than accepting and then faulting.
- **Methods set internal flags, not direct state changes** — the main FB body processes the flags on the next scan cycle, maintaining deterministic execution order.
