# Regulatory control

TcForge includes calculation blocks for common bounded analog and time-proportioned control. They accept conditioned process values and quality from the owning cyclic task. They do not select command sources, write `%I` or `%Q`, persist an operator request, or expose RPC methods. The application owns those concerns and routes the calculated demand through its output device and interlocks.

The blocks are inspired by the control patterns in `rw-twincat-core`'s Regulatory Control folder. Their implementation and interfaces follow TcForge's quality, single-owner, and safe-output contracts rather than the reference project's source-handler and persistence design.

| Block | Purpose | Safe response |
| --- | --- | --- |
| `FB_HysteresisControl` | Two-threshold BOOL demand for heating, cooling, filling, or venting | Demand OFF |
| `FB_BangBang` | Maps hysteresis demand to two numeric CV values | CV zero and demand OFF |
| `FB_PID_Full` | Cyclic PID with output limits, ramps, manual/hold, and tracking | Configured `safeCv` |
| `FB_TempController` | PID plus 0–100% cyclic PWM and standby setpoint | Duty zero and PWM OFF |
| `FB_SwitchingPvPid` | Switches between two independently tuned PV/PID channels for one CV | Shared `safeCv` for a bad selected PV; zero for an invalid shared contract |

## Integrating a loop

Call a block once per owning task cycle with `enable`, a finite PV, and `pvQuality := E_IO_Quality.GOOD`. Feed its result to an application-owned output device only when the block reports `sts.ready`; also apply the machine's permissives and interlocks there. The application is responsible for retaining or arbitrating operator setpoints and manual requests. A physical safety function, where required, must remain independent of these software calculations.

Hysteresis uses `low < high`. With `onBelowLow := TRUE`, demand turns ON at or below `low` and OFF at or above `high`; `FALSE` reverses that direction. Invalid quality, enable, thresholds, or PV clears the old demand. On recovery, a PV inside the deadband does not re-energize from remembered state. `FB_BangBang` exposes the same status and maps ON to `highValue`, OFF to `lowValue`.

## PID contract

`ST_PID_Full_Cfg` supports two gain forms:

- Ideal form (`standardForm := FALSE`): `kp` is CV/PV, `ki` is CV/(PV·s), and `kd` is CV·s/PV. The calculated terms are `kp·error`, integrated `ki·error·dt`, and derivative on PV.
- Standard form (`standardForm := TRUE`): proportional gain `kp`, integral time `integralTime`, and derivative time `derivativeTime`; the effective integral gain is `kp/Ti` and derivative gain is `kp·Td`. Zero times disable their respective terms.

Setpoint and CV ramp rates are engineering units per second; zero disables a ramp. `reverseActing` changes the error sign. `derivativeTau` enables a first-order derivative filter. CV and integral limits are independent. Conditional integration stops adding integral in the direction of CV saturation, and `sts.saturated` reports a requested CV beyond the limit even when that addition is rejected. A configuration edit clears prior controller history for one safe scan.

`manual` requests a bounded `manualCv` and tracks the integral bias so automatic control can resume near that value. `hold` freezes the CV while retaining current history. `track` is a one-scan bounded CV handoff for a different controller. These are calculation modes, not authorization or source-priority mechanisms. Resolve competing requests before calling the block.

`cycleTime := T#0MS` reads the owning task period. An explicit `cycleTime` is useful in deterministic test fixtures. `maxDt` bounds that declared calculation period, resets history, and emits `safeCv` when exceeded. It does not measure elapsed wall time or detect skipped task cycles; the owning application should apply its execution-continuity policy to the output device. The block rejects nonfinite REAL input bits before doing floating-point comparisons or arithmetic.

## PWM and PV switching

`FB_TempController` requires PID CV limits of exactly `0..100` percent and `safeCv = 0`, and a `pwmPeriod` from 100 ms to one hour. It advances a cyclic PWM phase using the configured or owning task period; duty is the PID CV. The optional standby request selects `standbySetpoint`. If the PID is not ready, duty and PWM go OFF in the same scan. Size the PWM period to the physical switching device and process; this block does not implement an independent overtemperature cutoff.

`FB_SwitchingPvPid` has one PID configuration per PV and demands identical CV limits and safe CV for both. The inactive PID is reset each scan. On source change, the newly selected PID tracks the previous valid CV for one scan; subsequent scans regulate using its own tuning. A bad selected PV fails to the shared safe CV and invalidates the prior selection, so recovery cannot reuse a stale handoff. The application decides which source is authoritative.

The TcUnit suites `FB_HysteresisControl_Test` and `FB_RegulatoryControl_Test` cover thresholds, quality loss and recovery, proportional/integral action, saturation, ramps, nonfinite input rejection, PWM/standby, and PV switching. The source build and bench test evidence are tracked in [PROGRESS.md](https://github.com/eponce00/TcForge/blob/main/PROGRESS.md).
