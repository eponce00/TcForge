# 7 Architecture

This document describes the OO pattern every TcForge device follows: the abstract base class, the interfaces it implements, and the composed fault handler. Follow this pattern for any new device block so aggregators, HMIs and the fault history all keep working with zero glue code.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [Command Source Control](2-Command-Source-Control.md) · [Sequencing](5-Sequencing.md) · [Persistent Variables](6-Persistent-Variables.md) · [I/O Binding →](8-IO-Binding.md)

---

## 7.1 Class Layout

```
FB_DeviceBase (ABSTRACT)
├── IMPLEMENTS I_Resettable       -- Reset(eRequester)
├── IMPLEMENTS I_SourceLockable   -- LockSource(bLock)
├── IMPLEMENTS I_Diagnosable      -- IsFaulted / GetFaultCode / GetFaultString
└── composes FB_FaultHandler (_fault)
        ├── VAR PERSISTENT ring[0..7] OF ST_FaultEntry
        ├── VAR PERSISTENT lastCode, lastTs, lastRequester
        └── Raise(code, requester) / Clear() / IsFaulted / GetRingEntry(idx)

FB_TwoPosActuator EXTENDS FB_DeviceBase IMPLEMENTS I_Abortable
FB_StateMachine   EXTENDS FB_DeviceBase IMPLEMENTS I_Abortable
FB_DigitalOutput  EXTENDS FB_DeviceBase IMPLEMENTS I_DigitalCommandable
FB_AnalogOutput   EXTENDS FB_DeviceBase IMPLEMENTS I_AnalogCommandable
FB_DigitalInput   EXTENDS FB_DeviceBase
FB_AnalogInput    EXTENDS FB_DeviceBase
```

---

## 7.2 Interfaces


| Interface              | Method(s)                                   | When to implement                                |
| ---------------------- | ------------------------------------------- | ------------------------------------------------ |
| `I_Resettable`         | `Reset(eRequester) : E_RpcMethodResponse`   | Always (inherited from `FB_DeviceBase`).         |
| `I_SourceLockable`     | `LockSource(bLock) : E_RpcMethodResponse`   | Always (inherited from `FB_DeviceBase`).         |
| `I_Diagnosable`        | `IsFaulted / GetFaultCode / GetFaultString` | Always (inherited from `FB_DeviceBase`).         |
| `I_Abortable`          | `Abort(eRequester) : E_RpcMethodResponse`   | Devices that can stop their own motion/sequence. |
| `I_DigitalCommandable` | `SetOn / SetOff`                            | Discrete output blocks.                          |
| `I_AnalogCommandable`  | `SetValue(rValue)`                          | Continuous output blocks.                        |


`I_Diagnosable` lets an aggregator walk any collection of unrelated devices:

```iecst
VAR
    devices : ARRAY[0..N] OF I_Diagnosable;  // populated at init
END_VAR
FOR i := 0 TO N DO
    IF devices[i].IsFaulted() THEN
        // surface devices[i].GetFaultString() in a plant-wide alarm list
    END_IF;
END_FOR;
```

---

## 7.3 Safety-Command Invariant

The `Reset` and `Abort` commands are **always accepted** from any requester, regardless of source lock or fault state. They may reject only when execution would be a no-op (e.g. `Abort` when already `STOPPED`). Everything else goes through `F_ValidateRequester`.


| Command      | Base behavior                              | Reject reasons                      |
| ------------ | ------------------------------------------ | ----------------------------------- |
| `Reset`      | Clears `_fault`, resets to known state     | None — always `ACCEPTED`            |
| `Abort`      | Stops motion, enters safe state            | Only when already stopped/aborting  |
| `LockSource` | Writes `bSourceLockedToProg`               | Never                               |
| *all others* | `F_ValidateRequester` + state + permissive | Source / fault / state / permissive |


---

## 7.4 FB_FaultHandler

Device-agnostic book-keeping composed into every `FB_DeviceBase`. Stores:

- `currentCode` — active fault (0 = clear), cleared only by `Reset`
- `lastCode / lastTs / lastRequester` — most recent fault, survives `Reset` (persistent)
- `ring[0..7]` — ring buffer of recent faults with timestamps (persistent)

Calling semantics:


| Call                     | Effect                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `Raise(code, requester)` | Idempotent on `code`. First call pushes to ring. Same code again no-ops. Different non-zero code replaces + pushes. |
| `Clear()`                | Sets `currentCode := 0`. Preserves ring + last-*.                                                                   |
| `GetRingEntry(idx)`      | `idx=0` returns oldest kept entry; `RING_SIZE-1` returns newest.                                                    |


Timestamps come from `Tc2_System.F_GetSystemTime()` (100 ns ticks since 1601 UTC) converted to `LTIME`.

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

`_UpdateHeader` derives the rest from `_fault`, `bSourceLockedToProg`, and `_lastRequester` / `_tsLastCommand` (populated by `_AcceptCommand`).


| Header field                        | Meaning                                     |
| ----------------------------------- | ------------------------------------------- |
| `stateString`                       | Human-readable state name (device-specific) |
| `stsReady`                          | Not faulted, not busy, source unlocked      |
| `stsBusy`                           | Transitioning / moving (device-specific)    |
| `stsFaulted`                        | `_fault.IsFaulted()`                        |
| `stsSourceLocked`                   | `bSourceLockedToProg`                       |
| `faultCode` / `faultString`         | Current fault code + resolved string        |
| `lastFaultCode` / `lastFaultString` | Most recent fault (survives Reset)          |
| `lastRequester`                     | Source of last accepted command             |
| `tsLastCommand` / `tsLastFault`     | `LTIME` timestamps                          |


---

## 7.6 Writing a New Device

1. Define the three structs: `ST_<Dev>_Cfg`, `ST_<Dev>_Sts` (with `header : ST_DeviceHeader_Sts` first), `ST_<Dev>_IO`.
2. Define `E_<Dev>_State` and `E_<Dev>_Fault` enums (use `{attribute 'qualified_only'}`).
3. Declare the FB: `FUNCTION_BLOCK FB_<Dev> EXTENDS FB_DeviceBase [IMPLEMENTS I_Abortable]`.
4. Override `ResolveFaultString(code : DINT) : STRING(79)` to map your fault enum to text.
5. Add a `PRIVATE _StateToString(state) : STRING(31)` helper for the state name.
6. In every accepted command method: `_AcceptCommand(eRequester := eRequester);`
7. In the cyclic body: `_fault.Raise(code := E_<Dev>_Fault.X)` on fault detection, `_UpdateHeader(...)` at the end.
8. Override `Reset` only if device-specific cleanup is needed; call `SUPER^.Reset(eRequester := eRequester)` first to preserve the always-accept invariant.

Enum-to-string is always a **dedicated method** (`ResolveFaultString`, `_StateToString`), never an inline `CASE` ladder in the body.

---

## 7.7 Persistence Convention

Only two places in a TcForge device use `VAR PERSISTENT`:

1. `FB_FaultHandler.ring / lastCode / lastTs / lastRequester` — the fault history (inherited automatically through composition).
2. Any last-commanded setpoints the device exposes (e.g. a PID setpoint, a selected mode).

Everything else — `cfg`, `sts`, timers, state, edge-detection — is recomputed each cycle. See [§6 Persistent Variables](6-Persistent-Variables.md) for the full rationale and the UPS configuration.