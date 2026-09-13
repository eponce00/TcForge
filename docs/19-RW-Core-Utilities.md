# rw-core utilities and engineering-unit review

The local `rw-twincat-core` repo is a useful design reference, but its utility
folder includes process-plant and project-specific code. TcForge targets discrete
assembly machines. This review selects behavior for a real TcForge consumer rather
than importing an entire category. No utility implementation was copied.

| Reference area | Decision | Reason |
| --- | --- | --- |
| Task cycle time, first-order low-pass filter, IO quality | Already covered in TcForge | `F_GetTaskCycleTime`, `FB_LPF_FirstOrder_IIR`, and `FB_IOQualityMonitor` have explicit task, finite-value, freshness and recovery behavior. |
| `FB_CycleGuard` | Do not import | Skipping a second call silently could hide a double-owner wiring error. Its test-build bypass also means tests do not exercise the same behavior. TcForge requires one cyclic owner and detects execution gaps. |
| Bitmask functions and `FB_Select` | Defer | `FB_BitMatrix64` serves current bit-state users. The selector assumes matching array bounds and needs a defined no-match and mismatch policy before becoming a common API. |
| Moving average, ramp/setpoint limiters, PWM, stopwatch | Defer | These can help specific sensors or drives, but need a real consumer and explicit startup, invalid-sample, task-timing and safe-output semantics. The reference stopwatch measures system time; sequence timing should use the PLC task/timer contract. |
| CoE SDO, Modbus TCP, module registries, response generators and mock VFD | Keep out of the core for now | They bind to specific buses, hardware, application composition or simulations. Add an optional adapter or test model when a machine needs one. |

`E_Unit` lives with analog IO, not in the utility folder. The earlier TcForge
version inherited a process-heavy catalog (pH, turbidity, conductivity, liquid
and gas flows) and defaulted every analog channel to `PERCENT`. We have no
external consumers yet, so the enum now uses explicit codes for common discrete
machine measurements: position, angle, speed, force, torque, mass, pneumatic
pressure, temperature, electrical values, count and time. Unconfigured channels
publish `UNSPECIFIED`. The assembly example explicitly labels its pressure and
height sensors. The enum is HMI metadata, not a unit-conversion system.
