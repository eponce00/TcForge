# 4 RPC Method Response

All RPC methods across the library return `E_RpcMethodResponse`, a standardized enumeration that tells the caller whether a command was accepted or rejected — and why. RPC responses share a **numbering convention** with the persistent fault codes in [§2.4 Architecture — Fault Book-Keeping](2-Architecture.md#24-fault-book-keeping) but belong to a different storage scope.

> **Navigation:** [← Command Source Control](3-Command-Source-Control.md) · [README / TOC](../README.md) · [I/O Binding →](5-IO-Binding.md)

---

## 4.1 E_RpcMethodResponse

The enum uses `{attribute 'to_string'}` so `TO_STRING(response)` returns the symbolic name (e.g. `'REJECTED_FAULTED'`).


| Value | Name                          | Description                                      |
| ----- | ----------------------------- | ------------------------------------------------ |
| 0     | `ACCEPTED`                    | Command accepted and will be executed            |
| 11    | `REJECTED_SOURCE_NOT_ALLOWED` | Source locked to PROG; operator request rejected |
| 20    | `REJECTED_WRONG_STATE`        | FB is not in the required state for this command |
| 21    | `REJECTED_FAULTED`            | FB is in a fault state; reset first              |
| 23    | `REJECTED_ALREADY_AT_TARGET`  | Already at the requested position/state          |
| 50    | `REJECTED_PERMISSIVE_NOT_MET` | A required permissive group is not OK            |
| 51    | `REJECTED_INTERLOCKED`        | An interlock condition is preventing the command |
| 100   | `REJECTED_UNKNOWN`            | Fallback when no other code applies              |


### 4.1.1 Range Convention

The same numeric ranges used for persistent device faults ([§2.3.3](2-Architecture.md#233-fault-code-range-convention)) gate RPC rejections. Reading any code anywhere in the system immediately tells you the category:


| Range  | Category               | RPC usage                              | Persistent-fault usage                         |
| ------ | ---------------------- | -------------------------------------- | ---------------------------------------------- |
| 0      | Success / None         | `ACCEPTED`                             | `None`                                         |
| 1–9    | Timeouts               | *reserved*                             | `StepTimeout`, `AdvanceTimeout`, …             |
| 10–19  | Source / Authorization | `REJECTED_SOURCE_NOT_ALLOWED`          | *reserved*                                     |
| 10–19  | Feedback / Hardware    | *reserved*                             | `BothFeedbackOn`, `NoFeedback`                 |
| 20–29  | State                  | `REJECTED_WRONG_STATE`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET` | `UndefinedState`, `ConflictingCommands` |
| 30–39  | Manual override        | *reserved*                             | *reserved*                                     |
| 40–49  | Configuration          | *reserved*                             | *reserved*                                     |
| 50–59  | Permissive / Interlock | `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` | `PermissivesNotOK`, `RunningInterlockTripped` |
| 60–69  | Output / Hardware      | *reserved*                             | *reserved*                                     |
| 70–79  | Propagation            | *reserved*                             | `SubmoduleFaulted`                             |
| 80–89  | Redundancy             | *reserved*                             | *reserved*                                     |
| 100    | Default / Unknown      | `REJECTED_UNKNOWN`                     | *reserved*                                     |


Range **10–19** is reused: RPC uses it for authorization, persistent faults use it for feedback / hardware. They never appear in the same namespace, so the overlap is harmless and keeps each enum small and memorable.

---

## 4.2 RPC vs. Persistent Fault Decoupling

An RPC rejection is **not** a fault. They are two different things that share a numbering scheme:

| Aspect        | `E_RpcMethodResponse`                          | `E_<Dev>_Fault` / fault state on `FB_DeviceBase`      |
| ------------- | ---------------------------------------------- | ----------------------------------------------------- |
| Lifetime      | One method call / one round-trip               | Persistent; survives `Reset` as `lastFaultCode`       |
| Storage       | Return value only — never written to sts       | `_faultCode` + ring buffer owned by `FB_DeviceBase`   |
| Trigger       | Caller asks, validation rejects synchronously  | Cyclic body detects an abnormal runtime condition     |
| HMI surface   | Log line / toast on the calling client         | `Status.header.faultCode/String/Source/Reason`        |
| Cleared by    | The caller moving on / retrying                | `Reset()` (clears current, preserves last + ring)     |

Two implications:

1. **Never call `_Raise()` from inside an RPC method.** Persistent faults come from the cyclic body only. A permissive that fails an `Advance()` call returns `REJECTED_PERMISSIVE_NOT_MET` — it does not also push a `PermissivesNotOK` entry onto the ring. If the same condition persists long enough to be worth alarming, the cyclic body will raise the corresponding persistent fault.
2. **Never show an `E_RpcMethodResponse` as a fault on the main HMI.** RPC responses are feedback to the caller, not global state. A "REJECTED" popup next to the button is fine; turning the whole machine status red because of a rejected click is wrong.

The numbering convention is what makes the split cheap: a central HMI helper can render "`REJECTED_PERMISSIVE_NOT_MET`" and "`PermissivesNotOK`" with the same icon and color because the category is the code's 10s digit, regardless of which side of the fence the value came from.

---

## 4.3 Method Inventory

### 4.3.1 FB_TwoPosActuator


| Method         | Validation                                                            | Possible Responses                                                                          |
| -------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `Advance()`    | Not faulted, not already advanced/advancing, advance permissives OK   | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `Retract()`    | Not faulted, not already retracted/retracting, retract permissives OK | `ACCEPTED`, `REJECTED_FAULTED`, `REJECTED_ALREADY_AT_TARGET`, `REJECTED_PERMISSIVE_NOT_MET` |
| `Abort()`      | Always accepted (safety command)                                      | `ACCEPTED`                                                                                  |
| `Reset()`      | Always accepted (safety command)                                      | `ACCEPTED`                                                                                  |
| `LockSource()` | Always accepted                                                       | `ACCEPTED`                                                                                  |


### 4.3.2 FB_StateMachine


| Method         | Validation                                           | Possible Responses                                                                        |
| -------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `Start()`      | Must be Ready, start perms OK, auto interlocks OK    | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Home()`       | Must be Stopped, home perms OK, auto interlocks OK   | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Proceed()`    | Must be Paused, proceed perms OK, auto interlocks OK | `ACCEPTED`, `REJECTED_WRONG_STATE`, `REJECTED_PERMISSIVE_NOT_MET`, `REJECTED_INTERLOCKED` |
| `Pause()`      | Must be Running                                      | `ACCEPTED`, `REJECTED_WRONG_STATE`                                                        |
| `Stop()`       | Always accepted (safety command)                     | `ACCEPTED`                                                                                |
| `Abort()`      | Always accepted (safety command)                     | `ACCEPTED`                                                                                |
| `Reset()`      | Always accepted (safety command)                     | `ACCEPTED`                                                                                |
| `Retry()`      | Always accepted                                      | `ACCEPTED`                                                                                |
| `LockSource()` | Always accepted                                      | `ACCEPTED`                                                                                |


`FB_StateMachine` also exposes two **non-RPC** reporter methods that do not return `E_RpcMethodResponse` — they simply record an OEE condition code (0 = clear, non-zero = active reason). See [§7.2.3 Sequencing](7-Sequencing.md#723-oee-conditions--reportblocked--reportstarved):

- `ReportBlocked(code : DINT)` — downstream blocked reason
- `ReportStarved(code : DINT)` — upstream starved reason


---

## 4.4 OPC UA Usage

RPC methods are exposed via `{attribute 'TcRpcEnable' := '1'}`. An OPC UA client calls the method and receives the `E_RpcMethodResponse` return value in one round-trip.

### 4.4.1 OPC UA Client Example (Pseudocode)

```python
result = call_method("PLC1.MAIN.fbCylinder01.Advance")
if result != 0:
    print(f"Command rejected: {result}")  # e.g. 50 = REJECTED_PERMISSIVE_NOT_MET
```

### 4.4.2 PLC Caller Example

```iecst
// From sequence code (eRequester defaults to PROG)
eResult := fbCylinder.Advance();
IF eResult <> E_RpcMethodResponse.ACCEPTED THEN
    // Handle rejection — log, alarm, retry. Do NOT also raise a persistent fault.
END_IF;

// With explicit source
eResult := fbStateMachine.Start(eRequester := E_Requester.PROG);
```

---

## 4.5 Design Decisions

- **Stop and Abort always accept** — safety-critical commands must never be blocked.
- **Retry always accepts** — the retry mechanism handles its own edge detection internally.
- **Advance/Retract pre-check permissives** — gives immediate feedback rather than accepting and then faulting.
- **Methods execute immediately** — no scan-cycle delay between request and action.
- **RPC responses never write the fault handler** — rejections are feedback to the caller, not system state. See §4.2.
- **Numbering matches `E_<Dev>_Fault`** — a single 10s-digit lookup categorizes any code the operator sees.
