# 8 Alarms

TcForge alarms are process-condition detectors. They live alongside devices but are **not** devices: they do not own I/O, they do not carry a fault code, and they do not extend `FB_DeviceBase`. Instead they expose a small, uniform status surface (`ST_Alarm_Sts`) with debounce, ack/latch, severity tagging, and timestamps — so HMIs, aggregators, and device FBs can consume them identically regardless of the underlying detection rule (boolean, threshold, limit ladder, deviation, rate of change…).

> **Navigation:** [← Sequencing](7-Sequencing.md) · [README / TOC](../README.md) · [HMI Integration →](9-HMI-Integration.md)

---

## 8.1 Alarms vs. Faults

TcForge draws a clean line between the two concepts:

| Concept | Lives on | Raised by | Lifetime | Operator action |
| ------- | -------- | --------- | -------- | --------------- |
| **Fault** (`E_<Dev>_Fault`) | `FB_DeviceBase` fault state / `ST_DeviceHeader_Sts` | The device itself, via the inherited `_Raise(code, source, reason)` helper. The device is broken, hung, or misconfigured. | Persists until `Reset()` on the device. | Reset the device after fixing the underlying issue. |
| **Alarm** (`FB_Alarm*`) | Standalone alarm instance or `ST_*_Sts` on a device | A separate detector watching a signal or value. The signal condition is outside the expected range. | Follows the condition, optionally latches for ack. | Acknowledge; condition clears when the signal returns. |

Both can promote into each other — a device can read `alarm.sts.stsActive` and call its own `_Raise(...)`, or an alarm can monitor a device's header (`stsFaulted`). They share the same HMI vocabulary (active / acked / severity / timestamps) but keep distinct storage so diagnostic queries stay unambiguous.

This also means: alarms **do not live in the device fault ring buffer**. If you need an alarm-history ring, run the alarm through the device's fault pipeline by promoting it to an `E_<Dev>_Fault` code — that's a deliberate authoring decision, not automatic.

---

## 8.2 Severity Model

Every alarm carries a severity tag the HMI uses to drive colour, stacklight tower, siren, etc.

```iecst
TYPE E_AlarmSeverity :
(
    NONE     := 0,     // bookkeeping: alarm disabled or inactive
    INFO     := 1,     // informational, no operator action required
    WARNING  := 2,     // operator should investigate
    CRITICAL := 3,     // urgent; process may be about to lose control
    SHUTDOWN := 4      // interlock-grade; a controller is already acting
) USINT;
```

Numeric order is meaningful: `WARNING > INFO`, etc. Aggregators can compute `MAX(severity)` over a collection and light the highest tier. Pick a level per site-wide convention and stick to it; keeping names instead of `LEVEL_0..3` makes review diffs self-explanatory.

---

## 8.3 Common Status: `ST_Alarm_Sts`

Every alarm block fills the same status struct (analogous to `ST_DeviceHeader_Sts` for devices). The HMI always knows what it's reading.

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `stsEnabled` | `BOOL` | Echo of `cfg.bEnable`. Disabled alarms always report all flags FALSE. |
| `stsRaw` | `BOOL` | Instantaneous condition, *before* debounce. Useful for waveforms / diagnostics. |
| `stsDebounced` | `BOOL` | After `tOnDelay` / `tOffDelay`. This is what actually trips the alarm. |
| `stsActive` | `BOOL` | The alarm's public "is it firing?" bit. With ack required, this is the **latch**; without, it mirrors `stsDebounced`. |
| `stsLatched` | `BOOL` | TRUE while the alarm is latched awaiting ack. Always FALSE when `cfg.bRequireAck = FALSE`. |
| `stsAcked` | `BOOL` | TRUE once an operator has acknowledged the current latch. Cleared when the alarm re-latches. |
| `eSeverity` | `E_AlarmSeverity` | Echo of `cfg.eSeverity` while active; `NONE` when inactive. HMIs read this directly. |
| `sMessage` | `STRING(79)` | Echo of `cfg.sMessage` — the operator-facing one-liner for this alarm. |
| `ackRequester` | `E_Requester` | Who acknowledged the current latch (`PROG` / `OPERATOR`). |
| `tsTripped` | `LTIME` | Timestamp of the most recent rising edge of `stsDebounced`. |
| `tsCleared` | `LTIME` | Timestamp of the most recent falling edge of `stsDebounced`. |
| `tsAcked` | `LTIME` | Timestamp of the most recent accepted `Ack` call. |

Rules:

- The alarm owns `sts`. A consumer never writes into it.
- `stsActive` is the only field most HMI pages need. Everything else is there for forensics.
- `eSeverity` reports `NONE` while `stsActive = FALSE` so aggregators can naïvely sum or `MAX` without special-casing.

---

## 8.4 Common Config: `ST_Alarm_Cfg`

The shared head of every alarm's config struct. Each concrete alarm's `ST_Alarm<Type>_Cfg` starts with these fields in the same order so the consumer-facing shape is consistent.

| Field | Type | Default | Meaning |
| ----- | ---- | ------- | ------- |
| `bEnable` | `BOOL` | `FALSE` | Master enable. Disabled alarms consume zero state. |
| `tOnDelay` | `TIME` | `T#0MS` | Debounce — the condition must hold this long before the alarm trips. |
| `tOffDelay` | `TIME` | `T#0MS` | Hysteresis — the condition must clear this long before the alarm releases. |
| `bRequireAck` | `BOOL` | `FALSE` | When TRUE, the alarm latches and waits for `Ack`. |
| `eSeverity` | `E_AlarmSeverity` | `NONE` | HMI severity tag. |
| `sMessage` | `STRING(79)` | `''` | Short operator-facing message (e.g. `'Tank 1 high level'`). |

Alarms **default disabled** (`bEnable = FALSE`). Explicit enable at commissioning prevents "forgot to configure it, why is it firing?" discussions.

---

## 8.5 Lifecycle

```
           (condition holds tOnDelay)          (condition clears tOffDelay)
stsRaw   ─┘┐ ┌──────────────────────────────┐   ┌──────────────────┐
           └─┘                              └───┘                  └──
stsDebounced ──────────────┌──────────────────┐   ┌───────────────────
                           │                  │   │
stsActive (no ack)         │                  │   │
                        ───┘                  └───┘...

stsActive (with ack)     ──┘                                     (until Ack())
stsLatched (with ack)    ──┘                                     (until Ack())
stsAcked                 ────────────────────────▲───────────────
                                                 │
                                           Ack(OPERATOR)
```

- **Without `bRequireAck`:** `stsActive` follows `stsDebounced` directly. Self-clearing. `stsLatched` is always FALSE.
- **With `bRequireAck`:** `stsActive` goes TRUE on the rising edge of `stsDebounced` and stays TRUE until `Ack()` is called *and* `stsDebounced` is FALSE. If the operator acks while the condition still holds, `stsAcked` goes TRUE but `stsActive` remains — this lets the HMI stop flashing while clearly showing the condition is still present.

---

## 8.6 `FB_AlarmBase` — The Shared Engine

All concrete alarm FBs extend `FB_AlarmBase`. The base owns:

- Debounce timers (`TON` / `TOF`)
- Latch / ack state (`VAR PERSISTENT`, so an unexpected restart doesn't silently "un-latch" an unacknowledged critical alarm)
- Timestamp bookkeeping
- The `Ack(eRequester)` RPC method
- A `_cycleGuard : FB_CycleGuard` equivalent so calling the FB twice in a cycle is a no-op
- A protected hook: `_EvaluateCondition() : BOOL`

Concrete alarms only override `_EvaluateCondition`, returning TRUE when the raw trip condition holds. They never touch timers, latches, or the status struct directly.

```iecst
FUNCTION_BLOCK FB_AlarmThreshold EXTENDS FB_AlarmBase
VAR_INPUT
    cfg      : ST_AlarmThreshold_Cfg;   // includes ST_Alarm_Cfg fields first
    inpValue : REAL;
END_VAR

METHOD PROTECTED _EvaluateCondition : BOOL
    IF cfg.bFailHigh THEN
        _EvaluateCondition := inpValue > cfg.fThreshold;
    ELSIF cfg.bFailLow THEN
        _EvaluateCondition := inpValue < cfg.fThreshold;
    END_IF;
```

The base's body resolves to `_EvaluateCondition → debounce → latch/ack → status`, so every alarm behaves identically around the edges.

---

## 8.7 Concrete Alarms

### 8.7.1 `FB_AlarmSimple`

Debounced / lat-chable boolean mirror. Use to wrap any digital condition the HMI should see as an alarm.

- **Inputs:** `cfg : ST_AlarmSimple_Cfg`, `inpActive : BOOL`
- **Outputs:** `sts : ST_Alarm_Sts`
- **Extra cfg:** *none* (just the common fields)

Typical use: promote a device header flag (`dev.sts.header.stsFaulted`) or a plant condition (`door.sts.stsOpen`) into the alarm display vocabulary without writing any logic.

### 8.7.2 `FB_AlarmThreshold`

Single-direction threshold monitor against a REAL input.

- **Inputs:** `cfg : ST_AlarmThreshold_Cfg`, `inpValue : REAL`
- **Outputs:** `sts : ST_Alarm_Sts`
- **Extra cfg:** `fThreshold : REAL`, `bFailHigh : BOOL`, `bFailLow : BOOL`

Uses strict `>` / `<` (exact threshold does not trip). If both `bFailHigh` and `bFailLow` are TRUE, `bFailHigh` wins — that's almost always a config mistake; check your cfg before expecting both.

### 8.7.3 `FB_AlarmLimit`

Four-level ladder (HiHi / Hi / Lo / LoLo) built on four composed `FB_AlarmThreshold` instances. Each level has its own full `ST_AlarmThreshold_Cfg`, so each can have its own delay, severity, ack requirement, message.

- **Inputs:** `cfg : ST_AlarmLimit_Cfg` (four sub-configs), `inpPv : REAL`
- **Outputs:** `sts : ST_AlarmLimit_Sts` (four `ST_Alarm_Sts` sub-statuses + rollups)
- **Suppression:** `HiHi` suppresses `Hi`, `LoLo` suppresses `Lo` on the rollup flags, so the HMI sees exactly one level active per direction. The individual sub-statuses stay raw for forensics.

### 8.7.4 `FB_AlarmDeviation`

Asymmetric deviation check — absolute limits *or* setpoint-relative.

- **Inputs:** `cfg : ST_AlarmDeviation_Cfg`, `inpPv : REAL`, `inpSetpoint : REAL`
- **Outputs:** `sts : ST_Alarm_Sts`
- **Extra cfg:** `fHighLimit : REAL`, `fLowLimit : REAL`, `bUseSetpoint : BOOL`

- Absolute mode (`bUseSetpoint = FALSE`): alarm when `inpPv > fHighLimit` OR `inpPv < fLowLimit`. `inpSetpoint` is ignored.
- Deviation mode (`bUseSetpoint = TRUE`): alarm when `inpPv > inpSetpoint + fHighLimit` OR `inpPv < inpSetpoint - fLowLimit`. Tracks moving setpoints.

### 8.7.5 `FB_AlarmRateOfChange`

Runaway / sensor-drop detector.

- **Inputs:** `cfg : ST_AlarmRateOfChange_Cfg`, `inpPv : REAL`
- **Outputs:** `sts : ST_Alarm_Sts`, plus `outRateOfChange : REAL` (units per second — always exposed, alarm or not).
- **Extra cfg:** `fRateLimit : REAL` (units / s)

Rate is computed from the task's cycle time via `F_GetTaskCycleTime()`. The first scan initialises the previous sample and reports zero rate — no false trip at power-on.

---

## 8.8 Ack Semantics and `I_Alarm`

The `I_Alarm` interface unifies how any code (HMI gateway, parent device, test harness) talks to an alarm:

```iecst
INTERFACE I_Alarm
    METHOD Ack : E_RpcMethodResponse
        VAR_INPUT
            eRequester : E_Requester := E_Requester.PROG;
        END_VAR
```

Every concrete alarm FB implements `I_Alarm`. `Ack` uses `F_ValidateRequester` the same way device methods do — a source-locked alarm (for program-only acknowledgment) rejects `OPERATOR` calls with `REJECTED_SOURCE_NOT_ALLOWED`. By default alarms are *not* source-locked; the operator always acks.

`Ack` is idempotent — repeated calls on the same latch just refresh `tsAcked` / `ackRequester`. A failing `Ack` (source rejection) is reported through the RPC response and never changes state.

Aggregators can walk a heterogeneous alarm list:

```iecst
VAR
    alarms : ARRAY[0..N] OF I_Alarm;   // populate at init with any alarm FB
END_VAR
FOR i := 0 TO N DO
    IF alarms[i].Ack(eRequester := E_Requester.OPERATOR) = E_RpcMethodResponse.ACCEPTED THEN
        // ok
    END_IF;
END_FOR;
```

---

## 8.9 Wiring Alarms to Devices

Two common patterns:

### 8.9.1 Device composes alarms internally

The device owns several alarm FB instances, reads `alarm.sts.stsActive`, and promotes selected ones to its own fault codes. Used when the alarm is a device-specific concern (a clamp's position-deviation alarm, a pump's pressure Hi).

```iecst
FUNCTION_BLOCK FB_Pump EXTENDS FB_DeviceBase
VAR
    almHighTemp : FB_AlarmThreshold;
END_VAR
// body:
almHighTemp(cfg := cfg.almHighTemp, inpValue := sts.stsMotorTempC);
IF almHighTemp.sts.stsActive AND cfg.bPromoteHighTempToFault THEN
    _Raise(
        code   := E_Pump_Fault.MotorOverTemp,
        source := 'ALM_TEMP',
        reason := almHighTemp.sts.sMessage
    );
END_IF;
```

### 8.9.2 Standalone alarm in `GVL_HW` or a program

The alarm watches a plant signal and is consumed by HMI directly. Use when the condition doesn't belong to any single device — e.g. a building-level tank-overfill alarm.

```iecst
GVL_ALARMS.almTankOverfill.cfg.bEnable   := TRUE;
GVL_ALARMS.almTankOverfill.cfg.fThreshold := 95.0;
GVL_ALARMS.almTankOverfill.cfg.bFailHigh  := TRUE;
GVL_ALARMS.almTankOverfill.cfg.eSeverity  := E_AlarmSeverity.CRITICAL;
GVL_ALARMS.almTankOverfill.cfg.sMessage   := 'Tank 1 level > 95%';
GVL_ALARMS.almTankOverfill(inpValue := GVL_HW.LEVEL_SENSOR_1.sts.stsValue);
```

The HMI binds to `GVL_ALARMS.almTankOverfill.sts.stsActive`, `.eSeverity`, `.sMessage`, `.tsTripped` — and can call `.Ack()` over OPC UA because all alarm FBs expose that method as an RPC.

---

## 8.10 Anti-Patterns

- **Bypassing the alarm module to inline `IF inpValue > limit THEN …` logic in device bodies.** You lose debounce, ack, severity, timestamps, and make diffs noisy. If it's worth warning about, wrap it in an alarm FB.
- **Re-using a fault code as an alarm.** Faults are for device failure, alarms for process conditions. Keep the ring buffer crisp by not mixing them.
- **Setting `bRequireAck = TRUE` on every alarm.** Latching every wiggle creates ack fatigue. Reserve it for `CRITICAL` / `SHUTDOWN` tier alarms and for anything that must be reviewed by an operator.
- **Writing into `sts` from the consumer.** The alarm owns `sts`; mutate `cfg` only.
- **Evaluating an alarm twice in one cycle.** The base's cycle guard handles it safely, but it still indicates confused ownership. One cyclic call per alarm instance.

---

## 8.11 Checklist for a New Alarm FB

1. Define `ST_Alarm<Type>_Cfg` with the six common fields first (`bEnable`, `tOnDelay`, `tOffDelay`, `bRequireAck`, `eSeverity`, `sMessage`) followed by your type-specific knobs.
2. Extend `FB_AlarmBase` and declare `cfg` + any extra signal inputs.
3. Override `_EvaluateCondition : BOOL` — pure function of `cfg` and inputs. No side effects, no state writes.
4. Implement `I_Alarm` — `FB_AlarmBase` already provides the `Ack` body; your FB just has to tag the interface.
5. Update `cfg`'s OPC UA pragmas following §9 so the HMI can drive it.
6. Add an entry to [§8.7](#87-concrete-alarms) so the docs list stays accurate.
