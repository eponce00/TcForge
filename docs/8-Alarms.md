# 8 Alarms

TcForge alarms detect assembly-machine conditions such as missing parts, clamp feedback, force limits and abnormal position rates. They expose debounce, acknowledgment, severity and evaluation validity independently of device faults.

> **Navigation:** [← Sequencing](7-Sequencing.md) · [Documentation home](index.md) · [HMI Integration →](9-HMI-Integration.md)

## 8.1 Alarms vs. Faults

| Concept | Owner | Recovery |
| --- | --- | --- |
| Device fault | `FB_DeviceBase` and the device's fault definitions | Explicit device `Reset()` after correcting the cause. |
| Alarm | A standalone alarm instance or an alarm composed by a device | Valid clear evidence, configured off-delay, and acknowledgment when required. |

Alarms do not extend `FB_DeviceBase`, own physical IO or automatically write the device fault history. An application may explicitly promote a selected alarm to a device fault. An alarm can also display a device's existing `sts.header.faulted` condition.

## 8.2 Severity Model

`E_AlarmSeverity` contains `NONE`, `INFO`, `WARNING`, `CRITICAL` and `SHUTDOWN` in increasing numeric order. `NONE` remains a valid configured value. Unknown enum values produce `InvalidConfig`.

An inactive alarm reports `NONE`. A valid active evaluation publishes `cfg.common.eSeverity`; invalid evaluation preserves the last established severity. `FB_AlarmLimit` reports the highest severity among its four child statuses. Severity is a display/classification value; it does not itself issue a machine stop.

## 8.3 Common Status: `ST_Alarm_Sts`

| Field | Meaning |
| --- | --- |
| `enabled` | Echo of `cfg.common.bEnable`. |
| `valid` | TRUE only when the alarm has a usable evaluation. |
| `evaluationState` | `Disabled`, `Valid`, `InvalidInput`, `InvalidConfig` or `Initializing`. |
| `raw` | Current condition before debounce when valid. FALSE during invalidity is not evidence that the condition cleared. |
| `debounced` | Established condition after trip/clear delays; held during invalid evaluation. |
| `active` | TRUE while the debounced condition or an outstanding latch remains. |
| `latched` | An outstanding latch awaits acknowledgment, even if `bRequireAck` was subsequently disabled. |
| `acked` | The outstanding latch has been acknowledged; this does not prove the condition cleared. |
| `eSeverity` | Active severity, held during invalidity; `NONE` when inactive. |
| `sMessage` | Echo of `cfg.common.sMessage`. |
| `ackRequester` | Requester of the most recent acknowledgment of a latch. |
| `tsTripped`, `tsCleared` | Last rising/falling edge timestamps of the established debounced condition. |
| `tsAcked` | Last accepted acknowledgment timestamp when a latch existed. |

The alarm owns its status. Consumers should display both `active` and `valid`: an inactive alarm with invalid evidence does not establish that the machine condition is normal.

### Validity and recovery

Every concrete alarm has `inpValid : BOOL := TRUE`. Bind it to application signal quality when a value can be stale, disconnected or unavailable. Numeric alarms also classify IEEE NaN and infinity through integer-bit helpers before floating-point comparisons, arithmetic or conversions.

Invalid input/configuration and rate-history initialization reset pending transition timing. They preserve established debounced/active state, latch, severity and trip/clear timestamps. Ack may be recorded while invalid, but cannot release a latch without later valid clear evidence. Recovery starts the full off-delay from fresh valid clear samples; time without trustworthy evidence does not count toward clearing.

`cfg.common.bEnable := FALSE` is an explicit suppression operation that clears active/latch/ack state and reports `Disabled`. Use `inpValid` for communication loss. Changing `bRequireAck` affects future trips and cannot erase an existing unacknowledged latch.

## 8.4 Common Config: `ST_Alarm_Cfg`

Each concrete configuration contains `common : ST_Alarm_Cfg`. For example, use `alarm.cfg.common.bEnable`, not a flattened enable field. `FB_AlarmLimit` has a separate nested common configuration per level, such as `alarm.cfg.Hi.common.bEnable`.

| Field | Default | Meaning |
| --- | --- | --- |
| `bEnable` | FALSE | Explicitly enable evaluation; FALSE clears and suppresses the alarm. |
| `tOnDelay` | `T#0MS` | Continuous valid trip evidence required before activation. |
| `tOffDelay` | `T#0MS` | Continuous valid clear evidence required before releasing the condition. |
| `bRequireAck` | FALSE | New trips create an acknowledgment latch when TRUE. |
| `eSeverity` | `NONE` | Severity classification for valid active evaluation. |
| `sMessage` | Empty | Operator message, for example `Clamp force above limit`. |

TIME is unsigned in TwinCAT. Zero disables the corresponding delay. The application writes configuration in the owning cyclic task; configuration and status are published read-only to OPC UA. Do not use external field writes as a configuration update mechanism.

## 8.5 Lifecycle

1. Valid trip evidence must remain true for `tOnDelay` before the debounced condition becomes true.
2. An active condition remains established until valid clear evidence lasts for `tOffDelay`.
3. With acknowledgment required, the alarm also remains active until Ack. Ack while the condition holds records acknowledgment without clearing the alarm.
4. Invalid evidence interrupts timing and preserves established state. Recovery must supply fresh evidence.

Changing trip/clear delays or acknowledgment policy restarts pending transition timing. Threshold direction/value and deviation mode/bound changes also restart timing, so new criteria cannot inherit timer credit from old criteria.

Latch and acknowledgment flags are `VAR PERSISTENT`. Persistence requires the application's TwinCAT persistent-data configuration and remains subject to the repository's restart/persistence qualification. Severity and timestamps are not a durable alarm-history store.

When those flags are restored, an unacknowledged latch still requires Ack. An acknowledged latch preserves that acknowledgment and requires valid clear evidence, without a second Ack merely because the runtime restarted. On the first enabled evaluation, a restored latch publishes the configured severity when that severity is recognized, even if process input is invalid. Subsequent invalid evaluations preserve the established severity. Configure the alarm before its first cyclic call; an explicitly disabled call clears the restored latch under the normal suppression policy.

## 8.6 `FB_AlarmBase` — The Shared Engine

`FB_AlarmSimple`, `FB_AlarmThreshold`, `FB_AlarmDeviation` and `FB_AlarmRateOfChange` extend the abstract base. `FB_AlarmLimit` instead composes four threshold instances and implements `I_Alarm`.

The base owns separate `TON` timers for trip and clear transitions, latch/ack state, timestamps, status, source locking and the operator mailbox. A child classifies its configuration and inputs, computes its raw condition only when valid, then calls `_Evaluate` once from its cyclic body:

```iecst
_Evaluate(
    cfgCommon := cfg.common,
    bRawCondition := rawCondition,
    evaluation := evaluationState,
    resetTiming := criteriaChanged
);
```

The child supplies its own local condition, evaluation-state and configuration-change variables. `_Evaluate` is the protected implementation API; there is no `_EvaluateCondition` override or cycle guard. Each alarm instance must have one owning task and one cyclic evaluation per scan. Call only the limit ladder's body when using `FB_AlarmLimit`; its child calls are internal.

## 8.7 Concrete Alarms

### 8.7.1 `FB_AlarmSimple`

Inputs are `cfg : ST_AlarmSimple_Cfg`, `inpActive : BOOL` and `inpValid`. The output is `sts : ST_Alarm_Sts`. Use it for a missing-part condition or a device fault indication whose quality is known separately.

### 8.7.2 `FB_AlarmThreshold`

Inputs are `cfg : ST_AlarmThreshold_Cfg`, `inpValue : REAL` and `inpValid`. Configuration adds `fThreshold`, `bFailHigh` and `bFailLow`.

Exactly one direction must be selected while enabled. Both directions or neither direction produce `InvalidConfig`. Comparisons are strict: equality to the threshold does not trip. Non-finite thresholds are invalid configuration; non-finite input values are invalid input.

### 8.7.3 `FB_AlarmLimit`

Inputs are `cfg : ST_AlarmLimit_Cfg`, `inpPv : REAL` and `inpValid`. The ladder has `HiHi`, `Hi`, `Lo` and `LoLo` threshold configurations and child statuses.

`HiHi` suppresses `Hi` on rollup active flags, and `LoLo` suppresses `Lo`. Individual child statuses remain available. `anyActive` and `eSeverity` aggregate alarm state. The input-valid gate reaches every child; composite validity covers enabled levels only. Disabled unused levels do not invalidate an enabled level, while an entirely disabled ladder reports `Disabled`.

### 8.7.4 `FB_AlarmDeviation`

Inputs are `cfg : ST_AlarmDeviation_Cfg`, `inpPv : REAL`, `inpSetpoint : REAL` and `inpValid`.

- Absolute mode: alarm outside `fLowLimit..fHighLimit`; the limits must be ordered. The unused setpoint does not affect validity.
- Setpoint mode (`bUseSetpoint := TRUE`): alarm above setpoint plus `fHighLimit`, or below setpoint minus `fLowLimit`. Both deviations must be nonnegative.

All participating values must be finite. Bounds use LREAL intermediates so adding or subtracting large finite REAL values does not overflow.

### 8.7.5 `FB_AlarmRateOfChange`

Inputs are `cfg : ST_AlarmRateOfChange_Cfg`, `inpPv : REAL` and `inpValid`. `outRateOfChange : LREAL` reports units per second. Configuration adds finite, nonnegative `fRateLimit`; the alarm tests the absolute rate against it.

Rate uses the configured task period through `F_GetTaskCycleTime()` and LREAL arithmetic. The helper has millisecond resolution: use tasks of at least 1 ms. Zero period is invalid configuration. This is a per-task-sample rate, not a measurement of ADS arrival intervals or actual scheduling jitter.

Startup, re-enable, invalid input/configuration, rate-limit or debounce/ack-policy changes, a different task, and task-period changes discard history. The first valid sample reports `Initializing` and zero diagnostic rate; it cannot clear an existing alarm. The second valid sample supplies a usable rate.

Before assigning a different signal source, call application-only `ReassignInput()` in the owning task. It immediately invalidates rate history while preserving the established alarm. The next valid sample establishes the new baseline. A cycle with `inpValid := FALSE` also invalidates history.

## 8.8 Ack Semantics and `I_Alarm`

`I_Alarm` exposes the program methods `Ack(eRequester)` and `LockSource(bLock)`. Direct program calls execute in the owning task. `Ack` validates requester identity and source locking; a locked alarm rejects operator acknowledgment with `REJECTED_SOURCE_NOT_ALLOWED`.

Repeated accepted acknowledgment of an existing latch refreshes `tsAcked` and `ackRequester`. Ack with no latch is an accepted no-op. `FB_AlarmLimit.Ack` cascades to its four levels.

External ADS/OPC UA clients use the queued RPC methods:

1. Call `OperatorAck(requestId)` with a nonzero request ID unique across clients and PLC restarts.
2. `QUEUED` means admitted to the mailbox, not acknowledged yet.
3. Read `OperatorCommandResult(requestId)` for the owning task's execution result.

The RPC wrapper fixes the requester to `OPERATOR`. `Ack` and `LockSource` are not RPC-enabled. Admission may return busy or another rejection; follow the bounded mailbox protocol in [HMI integration](9-HMI-Integration.md). A successful execution result still does not imply the alarm condition cleared.

## 8.9 Wiring Alarms to Devices

### 8.9.1 Device composes alarms internally

A device can own an alarm for a specific concern, such as clamp-force deviation. Its cyclic body supplies the signal and quality, evaluates the alarm once, then explicitly decides whether `sts.active` or invalid evaluation should affect the device. There is no automatic alarm-to-fault conversion.

### 8.9.2 Standalone alarm in a program

This complete program example supplies a clamp-force threshold alarm. The application's IO adapter assigns `clampForceN` and `forceQuality` before the program evaluates the alarm.

```iecst
PROGRAM PRG_ClampAlarm
VAR
    clampForceN : REAL;
    forceQuality : TcForge.E_IO_Quality := TcForge.E_IO_Quality.UNKNOWN;
    alarm : TcForge.FB_AlarmThreshold;
END_VAR

alarm.cfg.common.bEnable := TRUE;
alarm.cfg.common.eSeverity := TcForge.E_AlarmSeverity.WARNING;
alarm.cfg.common.sMessage := 'Clamp force above 500 N';
alarm.cfg.common.tOnDelay := T#50MS;
alarm.cfg.fThreshold := 500.0;
alarm.cfg.bFailHigh := TRUE;
alarm.cfg.bFailLow := FALSE;
alarm(
    inpValue := clampForceN,
    inpValid := forceQuality = TcForge.E_IO_Quality.GOOD
);
```

Here the application deliberately requires `GOOD` quality. Choose how to treat `CLAMPED` according to the signal's meaning. HMI pages bind `alarm.sts.active`, `.valid`, `.evaluationState`, `.eSeverity` and `.sMessage`; acknowledgment uses `OperatorAck(requestId)` and its result query.

## 8.10 Anti-Patterns

- Treating `active = FALSE` as proof of a healthy signal when `valid = FALSE`.
- Disabling the alarm on IO loss instead of setting `inpValid := FALSE`.
- Writing configuration or status through OPC UA; configuration belongs to the application and status to the alarm.
- Calling an instance from multiple tasks or multiple times per scan. There is no automatic duplicate-call suppression.
- Reassigning the rate detector to a new signal without invalidating its history.
- Treating mailbox admission or Ack as proof that the machine condition cleared.

## 8.11 Checklist for a New Alarm FB

1. Define a configuration with nested `common : ST_Alarm_Cfg` and its own criteria.
2. Extend `FB_AlarmBase`, declare the configuration, signal inputs and `inpValid := TRUE`. The base already implements `I_Alarm`.
3. Classify numeric operands before comparisons, conversions or arithmetic. Validate criterion-specific configuration.
4. Compute the condition only for valid evidence and call `_Evaluate` exactly once per cyclic body. Pass `resetTiming` when changed criteria invalidate pending debounce credit.
5. Keep state changes in the owning task, expose configuration/status read-only, and use the inherited queued operator acknowledgment API.
6. Test invalidity, recovery, configuration changes, acknowledgment, timing and numeric extremes; update this page.
