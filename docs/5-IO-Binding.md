# 5 IO boundary

Device blocks take ordinary PLC values and return ordinary PLC values. They do not
allocate or link hardware addresses. The application owns the process image,
terminal types, channel quality and final assignment to hardware. Simulation uses
the same public boundary; there is no second IO mode inside a device.

| Block | Inputs | Outputs |
|---|---|---|
| FB_DigitalInput | inSignal, inpQuality | sts.value, quality and edges |
| FB_AnalogInput | inRaw, inpQuality | sts.value, quality and scaling diagnostics |
| FB_DigitalOutput | commands, inpQuality | outSignal and sts |
| FB_AnalogOutput | commands, inpQuality | outRaw and sts |
| FB_TwoPosActuator | inAdvanced, inRetracted, configured conditions | outAdvance, outRetract and sts |

`U_IoRaw_In` and `U_IoRaw_Out` represent typed raw terminal data without any AT
allocation. Assign the union member matching the configured numeric type. Do not
link a 16-bit terminal to an assumed 32-bit field; copy its typed process-image
value at the application boundary. Outputs describe applied commands, not actual
physical feedback.

```iecst
// Illustrative analog application (separate from the clamp reference example).
// Process-image allocations belong in an application GVL.
// GVL_HW.pressureRaw is INT AT %I*; proportionalValve is INT AT %Q*.
rawPressure.nInt := GVL_HW.pressureRaw;
pressure(inRaw := rawPressure, inpQuality := GVL_HW.quality);
valve(inpQuality := GVL_HW.quality);
GVL_HW.proportionalValve := valve.outRaw.nInt;
```

A simulation assigns `rawPressure.nInt` from a model and observes
`valve.outRaw.nInt` directly. No device subclass or hidden-field access is required.

Sample IO/quality, map required conditions, run supervision and commands, run each
device once, then assign the final outputs and publish status. Commands issued
after a device call take effect on its next call. Do not run a device twice per
normal scan to conceal an ordering mistake. FB_Step mappings intentionally take
effect on the following scan; see [sequencing](7-Sequencing.md).

Always supply channel quality from the adapter. GOOD defaults are convenient for
isolated tests and do not establish bus health. Configure the actuator's required
conditions to include adapter quality. The example GVL starts quality UNKNOWN and
contains unlinked application-owned process-image variables; qualification must
verify real channel status and physical feedback.

The [reference machine](11-Reference-Machine.md) implements this call order for a
clamp, including independent shutdown quality and final output inhibition.
