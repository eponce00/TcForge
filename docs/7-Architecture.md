# 7 Architecture

This document describes the OO pattern every TcForge device follows: the abstract base class, the built-in fault book-keeping it provides, and the unified fault-context model that ties fault codes, RPC responses, and HMI fault strings together. Follow this pattern for any new device block so aggregators, HMIs and the fault history all keep working with zero glue code.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [Command Source Control](2-Command-Source-Control.md) · [Sequencing](5-Sequencing.md) · [Persistent Variables](6-Persistent-Variables.md) · [I/O Binding →](8-IO-Binding.md) · [Alarms →](9-Alarms.md)

---

## 7.1 Class Layout

```
FB_DeviceBase (ABSTRACT)
├── Safety-command primitives
│     ├── Reset(eRequester)      -- always accepted, clears active fault
│     └── LockSource(bLock)      -- writes bSourceLockedToProg
├── Diagnostics
│     ├── IsFaulted()
│     ├── GetFaultCode()
│     └── GetFaultString()       -- virtual; dispatches to ResolveFaultString(code)
├── Protected helpers (used by children)
│     ├── _Raise(code, source, reason)   -- idempotent-on-code fault raise
│     ├── _ClearFault()                  -- clears active fault, keeps history
│     ├── _AcceptCommand(eRequester)
│     └── _UpdateHeader(header, stateString, stsBusy)
└── Internal state
      ├── VAR            _faultCode / _faultTs / _faultSource / _faultReason
      └── VAR PERSISTENT _lastFault* + _faultRing[0..7] OF ST_FaultEntry

FB_TwoPosActuator EXTENDS FB_DeviceBase
FB_StateMachine   EXTENDS FB_DeviceBase
FB_DigitalOutput  EXTENDS FB_DeviceBase
FB_AnalogOutput   EXTENDS FB_DeviceBase
FB_DigitalInput   EXTENDS FB_DeviceBase
FB_AnalogInput    EXTENDS FB_DeviceBase
```

There is deliberately **no** device-interface hierarchy. Early versions of TcForge had `I_Resettable`, `I_SourceLockable`, `I_Diagnosable`, `I_Abortable`, `I_DigitalCommandable`, `I_AnalogCommandable` marker interfaces, but nothing ever held a polymorphic reference to any of them — every call site used the concrete FB type — so the interfaces were decorative. They were deleted to keep the base class the single source of truth for the safety/diagnostics contract.

The only device-facing interface is `I_Alarm` (see [§9 Alarms](9-Alarms.md)), which **is** consumed polymorphically by the aggregator pattern.

---

## 7.2 Safety-Command Invariant

`Reset` and device-specific `Abort` methods are **always accepted** from any requester, regardless of source lock or fault state. They may reject only when execution would be a no-op (e.g. `Abort` when already `STOPPED`). Every other command goes through `F_ValidateRequester`.


| Command      | Base behavior                              | Reject reasons                      |
| ------------ | ------------------------------------------ | ----------------------------------- |
| `Reset`      | `_ClearFault()`, resets to known state     | None — always `ACCEPTED`            |
| `Abort`      | Stops motion, enters safe state            | Only when already stopped/aborting  |
| `LockSource` | Writes `bSourceLockedToProg`               | Never                               |
| *all others* | `F_ValidateRequester` + state + permissive | Source / fault / state / permissive |

`F_ValidateRequester(eRequester, bSourceLocked, bFaulted)` has exactly three inputs — there is no "skip source check" or "allow when faulted" flag. Commands that must bypass the gate (Reset, Abort, Stop) don't call `F_ValidateRequester` at all; they accept unconditionally.

---

## 7.3 The Unified Fault Model

TcForge treats **fault code**, **fault source**, **fault reason**, and **RPC response** as four facets of one model. The goal is that every fault on the HMI answers three questions without developer guesswork:

1. **What happened?** — the `DINT` fault code plus its resolved string (`ResolveFaultString`).
2. **Where did it happen?** — a short `source` tag like `STEP_3004` or `PERMISSIVES`.
3. **Why did it happen?** — a free-form `reason` sentence, optionally written by the sequence author.

These four facets keep different scopes:

| Facet                 | Scope                                                   | Lives on                                          |
| --------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| `E_<Dev>_Fault` enum  | Persistent device fault, surfaces in ring buffer + HMI  | `_faultCode`, `header.faultCode`                  |
| `source` string       | Where in the FB the fault was raised                    | `header.faultSource` / `ST_FaultEntry.source`     |
| `reason` string       | Human-readable description, optionally author-supplied  | `header.faultReason` / `ST_FaultEntry.reason`     |
| `E_RpcMethodResponse` | One-round-trip RPC result; **never** persisted          | Method return value only                          |

### 7.3.1 RPC responses vs. device faults

An RPC call that rejects (e.g. `REJECTED_PERMISSIVE_NOT_MET`) is **not** a fault. It's a synchronous "try again" to the caller. Persistent faults only come from the cyclic body — never from inside an RPC method — because faults outlive a single call and must show in the ring buffer. The two spaces share a **numbering convention** (§7.3.3) but never the same storage.

### 7.3.2 Idempotent raising

`_Raise(code, source, reason)` is idempotent on `code`:

- First call with a non-zero code pushes one entry onto the ring and sets the active fault.
- Subsequent calls in the same scan (or across scans) with the **same** non-zero code no-op (return FALSE).
- A **different** non-zero code replaces current and pushes a new ring entry.
- `code = 0` is a no-op (use `_ClearFault()` to actually clear).

This means cyclic fault detection can fire every scan without flooding the ring. The requester recorded with the fault is `_lastRequester` (populated by `_AcceptCommand`), so the ring shows who issued the command that provoked the fault.

### 7.3.3 Fault-code range convention

Both `E_<Dev>_Fault` (persistent faults) and `E_RpcMethodResponse` (synchronous rejections) follow the same numbering scheme so HMI code and operators can read any number and immediately know the category:

| Range  | Category               | Used by                                                 |
| ------ | ---------------------- | ------------------------------------------------------- |
| 0      | None / Success         | Always                                                  |
| 1–9    | Timeouts               | `E_<Dev>_Fault` (e.g. `StepTimeout`, `AdvanceTimeout`)  |
| 10–19  | Source / Authorization | `E_RpcMethodResponse` (e.g. `REJECTED_SOURCE_*`)        |
| 10–19  | Feedback / Hardware    | `E_<Dev>_Fault` (e.g. `BothFeedbackOn`, `NoFeedback`)   |
| 20–29  | State                  | Both (e.g. `REJECTED_WRONG_STATE`, `UndefinedState`)    |
| 30–39  | Manual override        | Reserved                                                |
| 40–49  | Configuration          | `E_<Dev>_Fault` (e.g. `BadConfig`)                      |
| 50–59  | Permissive / Interlock | Both (e.g. `RunningInterlockTripped`, `PermissivesNotOK`) |
| 60–69  | Output / Hardware      | Reserved                                                |
| 70–79  | Propagation            | `E_<Dev>_Fault` (e.g. `SubmoduleFaulted`)               |
| 80–89  | Redundancy             | Reserved                                                |
| 100    | Default / Unknown      | `E_RpcMethodResponse.REJECTED_UNKNOWN`                  |

Range **10–19 is reused**: authorization rejects are RPC-only; feedback faults are persistent-only. They never appear in the same namespace, so the overlap is harmless and keeps each enum's numbers small and memorable.

Process-alarm limits (HH / HI / LO / LL) intentionally **do not** live in `E_<Dev>_Fault`. They belong on `FB_AlarmLimit` — composed with the device's process variable — where configuration, latching, severity and ack logic sit in one place. See [§9 Alarms](9-Alarms.md).

### 7.3.4 How the facets reach the HMI

`ST_DeviceHeader_Sts` (embedded as `header` in every device's `_Sts`) surfaces all four facets. `_UpdateHeader(...)` populates them every cycle from the base's internal state:

| Header field       | Populated from                                              |
| ------------------ | ----------------------------------------------------------- |
| `faultCode`        | `_faultCode`                                                |
| `faultString`      | `THIS^.ResolveFaultString(code)` — device-specific enum → text |
| `faultSource`      | `_faultSource` — e.g. `'STEP_3004'`, `'FEEDBACK'`           |
| `faultReason`      | `_faultReason` — full sentence, may be empty                |
| `lastFaultCode`    | `_lastFaultCode` — survives `Reset`                         |
| `lastFaultString`  | `ResolveFaultString(lastFaultCode)`                         |
| `lastFaultSource`  | `_lastFaultSource`                                          |
| `lastFaultReason`  | `_lastFaultReason`                                          |

The HMI renders "`faultSource`: `faultString` — `faultReason`". That formula works for every device because every device writes into the same header.

---

## 7.4 Fault Book-Keeping

`FB_DeviceBase` owns the fault history directly — there is no separate `FB_FaultHandler` to compose, and no `_fault.Xxx()` indirection. Previously these lived on a composed helper; that helper was folded into the base class so children call `_Raise` / `_ClearFault` / `IsFaulted` / `GetFaultCode` / `GetFaultString` directly.

The state owned by the base class:

- **Active fault** (`VAR`, not persistent) — `_faultCode`, `_faultTs`, `_faultSource`, `_faultReason`. Cleared on restart so recovery logic re-runs from a known state.
- **Last fault** (`VAR PERSISTENT`) — `_lastFaultCode`, `_lastFaultTs`, `_lastFaultRequester`, `_lastFaultSource`, `_lastFaultReason`. Survives `Reset` and warm-start so HMIs can always show "what last went wrong".
- **Ring buffer** (`VAR PERSISTENT`) — `_faultRing : ARRAY[0..7] OF ST_FaultEntry`, plus `_faultRingHead`. Rolling window of the last eight distinct fault episodes.

Calling semantics (children-facing):

| Call                              | Effect                                                                                                                                 |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `_Raise(code, source, reason)`    | Idempotent on `code`. First non-zero call pushes to ring and sets active fault. Same code is a no-op. A different non-zero code replaces + pushes. `code = 0` is a no-op. |
| `_ClearFault()`                   | Sets `_faultCode := 0` and clears `_faultSource` / `_faultReason`. Preserves ring + last-fault fields.                                 |
| `IsFaulted()`                     | `_faultCode <> 0`.                                                                                                                     |
| `GetFaultCode()`                  | Current active fault code.                                                                                                             |
| `GetFaultString()`                | Resolves the current code through the child's `ResolveFaultString` override.                                                           |

Timestamps come from the shared utility `F_Now()` (`Tc2_System.F_GetSystemTime()` converted to `LTIME`). There is one timestamp function in the library and every FB uses it.

### 7.4.1 When to set `source` / `reason`

- **Always set `source`** when raising from the cyclic body. A short constant string (`'FEEDBACK'`, `'MOTION'`, `'PERMISSIVES'`, `'STEP_3004'`) is enough — it answers "where in this FB?" without inspecting the code.
- **Set `reason` when you know something the resolved fault string doesn't.** For a `NoFeedback` fault raised in the advanced state, a reason like `'No advanced feedback 1.5 s after advance command'` turns a one-word alarm into a diagnostic.
- **Leave `reason` empty** when the resolved fault string already says everything (e.g. `AdvanceTimeout`). The HMI will simply render the string.

### 7.4.2 Example call sites

```iecst
// Timeout-style fault: source tells where, reason omitted (string is enough).
_Raise(
    code   := E_TwoPosActuator_Fault.AdvanceTimeout,
    source := 'MOTION',
    reason := ''
);

// Feedback fault with a reason the enum can't express.
_Raise(
    code   := E_TwoPosActuator_Fault.BothFeedbackOn,
    source := 'FEEDBACK',
    reason := 'Advanced and retracted feedback both TRUE — check wiring'
);

// Interlock trip (state-machine side).
_Raise(
    code   := E_SM_Fault.RunningInterlockTripped,
    source := 'INTLK_RUNNING',
    reason := 'Running interlock tripped during RUNNING state'
);
```

---

## 7.5 ST_DeviceHeader_Sts

Every device sts struct embeds `header : ST_DeviceHeader_Sts` as its first field. The base class's `_UpdateHeader` method fills it each cycle:

```iecst
// Called from every device's cyclic body
_UpdateHeader(
    header      := sts.header,
    stateString := _StateToString(state := currentState),
    stsBusy     := sts.stsMoving
);
```

`_UpdateHeader` derives the rest from the inherited fault state, `bSourceLockedToProg`, and `_lastRequester` / `_tsLastCommand` (populated by `_AcceptCommand`).


| Header field                                   | Meaning                                               |
| ---------------------------------------------- | ----------------------------------------------------- |
| `stateString`                                  | Human-readable state name (device-specific)           |
| `stsReady`                                     | Not faulted, not busy, source unlocked                |
| `stsBusy`                                      | Transitioning / moving (device-specific)              |
| `stsFaulted`                                   | `IsFaulted()`                                         |
| `stsSourceLocked`                              | `bSourceLockedToProg`                                 |
| `faultCode` / `faultString`                    | Current fault code + resolved string                  |
| `faultSource` / `faultReason`                  | Current fault context (where / why)                   |
| `lastFaultCode` / `lastFaultString`            | Most recent fault (survives Reset)                    |
| `lastFaultSource` / `lastFaultReason`          | Most recent fault context                             |
| `lastRequester`                                | Source of last accepted command                       |
| `tsLastCommand` / `tsLastFault`                | `LTIME` timestamps                                    |


---

## 7.6 Writing a New Device

1. Define the three structs: `ST_<Dev>_Cfg`, `ST_<Dev>_Sts` (with `header : ST_DeviceHeader_Sts` first), `ST_<Dev>_IO` (flat, with `AT %I* / %Q*`). See [§8 I/O Binding](8-IO-Binding.md) for the I/O contract.
2. Define `E_<Dev>_State` and `E_<Dev>_Fault` enums (use `{attribute 'qualified_only'}`). Number fault codes by category per [§7.3.3](#733-fault-code-range-convention). Keep the enum focused on ground truths about the device — leave process-limit alarms to `FB_AlarmLimit`.
3. Declare the FB: `FUNCTION_BLOCK FB_<Dev> EXTENDS FB_DeviceBase`.
4. Hold `io : ST_<Dev>_IO` as an internal `VAR` — **never** `VAR_IN_OUT`. I/O binds via `TcLinkTo` on the FB instance (§8).
5. Override `ResolveFaultString(code : DINT) : STRING(79)` to map your fault enum to text. Every enumerator gets a branch.
6. Add a `PRIVATE _StateToString(state) : STRING(31)` helper for the state name.
7. In every accepted command method: `_AcceptCommand(eRequester := eRequester);`
8. In the cyclic body: call `_Raise(code, source, reason)` on fault detection, with a short `source` tag and a descriptive `reason` (or `''` when the fault string already explains enough). Call `_UpdateHeader(...)` at the end.
9. Override `Reset` only if device-specific cleanup is needed; call `SUPER^.Reset(eRequester := eRequester)` first to preserve the always-accept invariant and clear fault context.

Enum-to-string is always a **dedicated method** (`ResolveFaultString`, `_StateToString`), never an inline `CASE` ladder in the body.

---

## 7.7 Persistence Convention

Only two places in a TcForge device use `VAR PERSISTENT`:

1. The fault book-keeping inherited from `FB_DeviceBase` — last-fault fields and the ring buffer.
2. Any last-commanded setpoints the device exposes (e.g. a digital output's last state, an analog output's last setpoint).

Everything else — `cfg`, `sts`, timers, state, edge-detection — is recomputed each cycle. See [§6 Persistent Variables](6-Persistent-Variables.md) for the full rationale and the UPS configuration.
