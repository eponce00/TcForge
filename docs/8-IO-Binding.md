# 8 I/O Binding

How TcForge devices connect to physical Beckhoff hardware. The library stays portable because every hardware reference lives behind a single `_IO` struct that is **internal to the device FB**. The consuming application binds the FB's I/O to real terminals by dropping `TcLinkTo` pragmas on the FB instance declaration — typically in a centralized `GVL_HW`. There is no `VAR_IN_OUT` plumbing to thread through the application.

> **Navigation:** [← Architecture](7-Architecture.md) · [README](../README.md) · [Alarms →](9-Alarms.md)

---

## 8.1 The `_IO` Struct Convention

Every device ships with three structs: `_Cfg`, `_Sts`, `_IO`. The `_IO` struct is the **only** place hardware symbols appear. Each primitive I/O field carries an `AT %I* / %Q`* pragma so the compiler generates an unresolved PLC symbol that can be linked from the I/O tree.

```iecst
TYPE ST_TwoPosActuator_IO :
STRUCT
    // Input feedbacks from field
    inFbkAdvanced   AT %I* : BOOL;
    inFbkRetracted  AT %I* : BOOL;

    // Output commands to field
    outValveAdvance AT %Q* : BOOL;
    outValveRetract AT %Q* : BOOL;
END_STRUCT
END_TYPE
```

Rules:

- `in*` fields on `%I*`, `out*` fields on `%Q*`. Prefix must match direction.
- No scaling, no filtering, no logic — raw hardware only.
- Type is always primitive (`BOOL`, `INT`, `REAL`…) **or** the shared 32-bit UNION `U_IoRaw_In` / `U_IoRaw_Out` for analog terminals (see §8.2.1). Never a nested regular struct.
- Naming mirrors the field tag: `inFbkAdvanced`, `outValveAdvance`.

The device FB holds the struct as an **internal variable**:

```iecst
FUNCTION_BLOCK FB_TwoPosActuator EXTENDS FB_DeviceBase
VAR
    io : ST_TwoPosActuator_IO;   // linked externally via TcLinkTo on the instance
END_VAR
```

The FB body reads `io.inFbkAdvanced` and writes `io.outValveAdvance` directly. The application never touches `io` — it is owned by the FB.

### 8.1.1 Analog Terminals Use a 32-bit UNION

Analog terminals come in many flavours: signed INT (16-bit DAC), REAL (some EL375x), UDINT (counter), WORD (bit-packed). Writing one `FB_AnalogInput` per primitive type would explode the library. TcForge ships a single 32-bit UNION instead:

```iecst
TYPE U_IoRaw_In :
UNION
    dw  AT %I* : DWORD;   // the hardware-linked member
    r          : REAL;
    w          : WORD;
    i          : INT;
    ui         : UINT;
    di         : DINT;
    udi        : UDINT;
END_UNION
END_TYPE
```

`FB_AnalogInput` holds its raw input as `U_IoRaw_In`; `FB_AnalogOutput` holds `U_IoRaw_Out` (same shape, `AT %Q*`). The project links the `**.dw` member** of that UNION to the terminal, regardless of the terminal's native type, and the FB picks the correct reinterpretation via `cfg.cfgInputType` / `cfg.cfgOutputType` (a `__SYSTEM.TYPE_CLASS` enum).

```iecst
{attribute 'TcLinkTo' :=
    '.io.inRaw.dw  := TIID^Device 1 (EtherCAT)^EL3068^AI Standard Channel 1^Value'}
PRESSURE_TRANSDUCER : FB_AnalogInput;

// In the consuming program:
cfgPressure.cfgInputType := __SYSTEM.TYPE_CLASS.TYPE_INT;   // EL3068 is INT
cfgPressure.cfgRawMin    := 0.0;
cfgPressure.cfgRawMax    := 32767.0;
cfgPressure.cfgEuMin     := 0.0;
cfgPressure.cfgEuMax     := 10.0;        // bar
cfgPressure.cfgUnit      := E_Unit.BAR;
```

Common selections:


| Terminal family             | `cfgInputType` / `cfgOutputType` |
| --------------------------- | -------------------------------- |
| EL3061 / 3062 / 3064 / 3068 | `TYPE_INT`                       |
| EL3104 / 3124               | `TYPE_INT`                       |
| EL3751, EL3773              | `TYPE_REAL` or `TYPE_DWORD`      |
| EL3681 (counter)            | `TYPE_UDINT`                     |
| EL4102 / 4104 / 4132 / 4134 | `TYPE_INT`                       |
| EL4112 (0-20 mA)            | `TYPE_INT`                       |


If the user leaves `cfgInputType` at default (`TYPE_INT`), a standard 0-10 V or 4-20 mA terminal works out of the box.

---

## 8.2 `AT %I* / %Q*` + `TcLinkTo`: How Binding Works

Two pieces collaborate:

1. `**AT %I* / %Q***` inside the `_IO` struct declares each raw bit as an **unresolved** symbol. When the FB is instantiated, TwinCAT creates a concrete unlinked symbol at `<instance>.io.<field>` under the PLC node in the I/O tree.
2. `**{attribute 'TcLinkTo' := '<path>'}`** placed above the FB instance declaration resolves each unlinked symbol to a physical terminal path. The link is written into the project the same way a drag-and-drop link would be, except that it lives in source control as text next to the instance.

Benefits:

- The library compiles with **zero** hardware attached. CI builds never need an EtherCAT simulator.
- The same library runs on different hardware by swapping the `TcLinkTo` paths in the consuming project.
- I/O wiring is a **code artifact** — reviewable in diffs, portable across branches, regenerable with a script.
- No `VAR_IN_OUT` plumbing. Application programs call `fbClamp(cfg := ..., sts => ...)` without ever threading `io`.

What `%I* / %Q`* does **not** do: it does not auto-allocate. The build fails the Activate step if any `*` is left unlinked. This is a feature — you'll never silently deploy unwired I/O.

---

## 8.3 Instance-Level Binding with `TcLinkTo`

Drop `TcLinkTo` attributes on the FB **instance** declaration, one per bit in the `_IO` struct. The attribute syntax is a pipe-separated list of field-to-path pairs (one pair per line is the conventional layout):

```iecst
{attribute 'TcLinkTo' :=
    '.io.inFbkAdvanced   := TIID^Device 1 (EtherCAT)^EL1008^Channel 1^Input;
     .io.inFbkRetracted  := TIID^Device 1 (EtherCAT)^EL1008^Channel 2^Input;
     .io.outValveAdvance := TIID^Device 1 (EtherCAT)^EL2008^Channel 1^Output;
     .io.outValveRetract := TIID^Device 1 (EtherCAT)^EL2008^Channel 2^Output'}
fbClamp : FB_TwoPosActuator;
```

Notes:

- Paths start with `TIID^` (TwinCAT I/O Device) followed by the device, terminal, channel, and signal name.
- The left-hand side is relative to the instance, so it always begins with `.io.<field>`.
- One `TcLinkTo` attribute lists every linked field for that instance. Fields not listed remain unlinked and Activate will fail — this is intentional.
- The same pragma works on a local `VAR`, a `VAR_GLOBAL` in a GVL, or a `VAR` in a `PROGRAM`. Use whichever scope matches your project layout.

---

## 8.4 Where FB Instances Live

### 8.4.1 Inline (tiny projects)

For a one-off test bench with a handful of devices, declare the instance and its link pragma directly in the program that uses it:

```iecst
PROGRAM PRG_Bench
VAR
    {attribute 'TcLinkTo' :=
        '.io.inSignal := TIID^Device 1 (EtherCAT)^EL1008^Channel 1^Input'}
    fbStartButton : FB_DigitalInput;
END_VAR
```

This is fine for 5–10 devices. Past that, the program file becomes a wiring manifest and the logic gets buried.

### 8.4.2 Centralized `GVL_HW` (recommended for anything larger)

Put every hardware-backed FB instance in a single `GVL_HW` so wiring is one searchable file, separate from the logic that uses it. This is the pattern the `TcForgeExample` project demonstrates.

```iecst
{attribute 'qualified_only'}
VAR_GLOBAL
    {attribute 'TcLinkTo' :=
        '.io.inFbkAdvanced   := TIID^Device 1 (EtherCAT)^EL1008^Channel 1^Input;
         .io.inFbkRetracted  := TIID^Device 1 (EtherCAT)^EL1008^Channel 2^Input;
         .io.outValveAdvance := TIID^Device 1 (EtherCAT)^EL2008^Channel 1^Output;
         .io.outValveRetract := TIID^Device 1 (EtherCAT)^EL2008^Channel 2^Output'}
    CLAMP_A : FB_TwoPosActuator;

    {attribute 'TcLinkTo' :=
        '.io.inSignal := TIID^Device 1 (EtherCAT)^EL1008^Channel 3^Input'}
    SENSOR_PART_PRESENT : FB_DigitalInput;

    {attribute 'TcLinkTo' :=
        '.io.outSignal := TIID^Device 1 (EtherCAT)^EL2008^Channel 3^Output'}
    LAMP_CYCLE : FB_DigitalOutput;

    {attribute 'TcLinkTo' :=
        '.io.inRaw.dw := TIID^Device 1 (EtherCAT)^EL3024^AI Standard Channel 1^Value'}
    TANK_LEVEL : FB_AnalogInput;
END_VAR
```

Note the `.dw` suffix on the analog terminal path — that's the UNION member actually mapped to `%I*`. See [§8.1.1](#811-analog-terminals-use-a-32-bit-union) for the rationale and type-selection table.

Call the instances from station programs:

```iecst
GVL_HW.CLAMP_A(cfg := cfgClampA, sts => stsClampA);
GVL_HW.SENSOR_PART_PRESENT(cfg := cfgSensor, sts => stsSensor);
```

Advantages at scale:

- The application never sees the `_IO` struct. Renaming a logic variable cannot break wiring.
- `GVL_HW` is the single source of truth for hardware. Diffs on wiring changes are localized.
- The I/O tree shows a flat list of `GVL_HW.<NAME>.io.<field>`, easy to grep and easy to audit for unlinked symbols.
- Branch a test configuration by swapping one GVL — no touch to any program.

---

## 8.5 When to Add a HAL / Conditioning Layer

The `_IO` struct **is** the HAL for most projects. Add a thin pre-processing layer only when one of these applies:

1. **Signal conditioning** — denoise, scale, unit conversion, range clamp before the device sees the value.
2. **Virtualization / simulation** — drive the "field side" of the struct from a simulator when no hardware is present.
3. **Redundancy / voting** — fold three feedbacks into one logical feedback.
4. **Runtime channel remapping** — swap a spare terminal without recompiling.

Because `io` is internal to the FB, a conditioning layer cannot reach into it from outside. Two clean options:

- **Condition on the application side before the FB reads.** Put a cyclic `PROGRAM` between the raw terminals and the FB, writing conditioned copies into a secondary `GVL` that the FB reads via `VAR_INPUT`. Use this when conditioning is cheap and flat.
- **Condition inside the FB itself** using an optional `VAR_INPUT bSimulate` + simulated inputs. The FB reads either `io.<raw>` or the simulated override depending on `bSimulate`. Use this when simulation needs first-class status reporting.

Do **not** bypass the `io` struct by mapping the terminal to two places (raw + conditioned). That path produces two symbols fighting for the same channel and is unreviewable in diffs.

---

## 8.6 Anti-Patterns

- **Hardware symbols in application code.** Never put `AT %I`* on a variable outside an `_IO` struct. It hides wiring from `GVL_HW`.
- **Passing `io` as `VAR_IN_OUT`.** This is the old pattern. It forces the application to own a copy of the struct, breaks the `TcLinkTo` convention, and couples every program to every device's I/O layout.
- **Nested `_IO` structs.** One `_IO` referencing another. TwinCAT's Symbol Mapping can't drill through nested structs cleanly — keep them flat.
- *Mixed `in` / `out`* in the same struct field word.** One direction per field.
- **Computing in the FB body before using the `io` value.** Conditioning belongs in the HAL layer (§8.5), not in the device FB. Keep the device "dumb" about wiring.

---

## 8.7 Checklist for a New Hardware-Connected Device

1. Define `ST_<Dev>_IO` with flat `in`* / `out`* fields, each carrying `AT %I`* or `AT %Q*`.
2. Device FB holds `io : ST_<Dev>_IO` as a private `VAR` — **never** `VAR_IN_OUT` / `VAR_INPUT` / `VAR_OUTPUT`.
3. Consuming application declares the FB instance in `GVL_HW` (preferred) or inline in its owning program.
4. Above the instance declaration, attach a `TcLinkTo` pragma listing every `.io.<field>` and its `TIID^…` path.
5. If conditioning is needed, add a pre-processing program that writes a conditioned mirror the FB reads via `VAR_INPUT` (see §8.5). Keep raw paths reviewable in `GVL_HW`.
6. Device's `_Sts` reports the **conditioned, logical** state. Raw bits stay behind the `_IO` boundary, invisible to the application.

---

## 8.8 Built-in I/O Devices

The four generic I/O blocks that ship with the library. Each one extends `FB_DeviceBase`, owns an internal `io` struct (§8.1), and participates in the shared fault-header model (§7).

### 8.8.1 `FB_DigitalInput`

Signal conditioning for a single `BOOL` field input.

- **Link:** `.io.inSignal` → `EL1xxx` channel
- **Cfg:** `cfgInvert`, `cfgDebounceOn`, `cfgDebounceOff`, `cfgQualityFaultAfter`
- **Sts:** `stsValue` (conditioned), `stsRawValue`, `stsQuality`, `stsRisingEdge`, `stsFallingEdge`
- **Behaviour:** quality-gated read → optional inversion → asymmetric debounce (`TON` on-delay, `TOF` off-delay) → edge detection on the debounced value
- **Fault codes (`E_DigitalInput_Fault`):** `BadQuality` (quality watchdog)

### 8.8.2 `FB_DigitalOutput`

Driver for a single `BOOL` field output with pulse-train options.

- **Link:** `.io.outSignal` → `EL2xxx` channel
- **Commands:** `SetOn(eRequester)`, `SetOff(eRequester)` — both gated by `F_ValidateRequester`
- **Cfg:** `cfgInvert` (Regular mode only), `cfgDebounceOn`, `cfgDebounceOff`, `cfgMode` (`Regular` / `SinglePulse` / `ContinuousPulse`), `cfgPulseOn`, `cfgPulseOff`, `cfgQualityFaultAfter`
- **Sts:** `stsValue` (physical output), `stsCommanded` (persistent request), `stsQuality`, `stsRisingEdge`, `stsFallingEdge`
- **Behaviour:** `VAR PERSISTENT _requestSync` → asymmetric debounce on the commanded value → mode shaping (pulse timers or passthrough) → quality-gated hardware write. Inversion applies only in `Regular` mode (pulse trains shouldn't be inverted).
- **Fault codes (`E_DigitalOutput_Fault`):** `BadQuality`

### 8.8.3 `FB_AnalogInput`

Signal-conditioning pipeline for any 32-bit analog terminal. Conditioning-only — process-limit alarms (HH / HI / LO / LL) live on `FB_AlarmLimit` composed with the published `stsValue` (see [§9 Alarms](9-Alarms.md)).

- **Link:** `.io.inRaw.dw` → `EL3xxx` channel (see §8.1.1 for the UNION and type selection)
- **Cfg:** `cfgInputType` (UNION member select), `cfgUseRawValue` (bypass scaling), `cfgRawMin/Max`, `cfgEuMin/Max`, `cfgUnit`, `cfgClampAsFault`, `cfgFilterTau` (IIR), `cfgQualityFaultAfter`
- **Sts:** `stsValue` (final EU), `stsScaled` (pre-filter EU), `stsRawReal`, `stsUnit`, `stsQuality` (promotes to `CLAMPED` automatically), `stsClampedLow/High/Active`
- **Behaviour:** first-scan config validation + task-dt cache → type-selected UNION read → quality-gated hold → clamp → optional clamp-as-fault → linear scale → optional first-order IIR low-pass
- **Fault codes (`E_AnalogInput_Fault`):** `BadQuality`, `ClampLow`, `ClampHigh`, `BadConfig`

### 8.8.4 `FB_AnalogOutput`

Driver for any 32-bit analog terminal with persistent setpoint.

- **Link:** `.io.outRaw.dw` → `EL4xxx` channel
- **Commands:** `SetValue(rValue, eRequester)` — gated by `F_ValidateRequester`
- **Cfg:** `cfgOutputType` (UNION member select), `cfgUseRawValue`, `cfgMinCv`, `cfgMaxCv`, `cfgEuMin/Max`, `cfgRawMin/Max`, `cfgUnit`, `cfgClampAsFault`, `cfgQualityFaultAfter`
- **Sts:** `stsValue` (clamped EU actually written), `stsCommanded` (persistent, survives power cycle), `stsRawReal`, `stsUnit`, `stsQuality`, `stsClampedLow/High/Active`
- **Behaviour:** `VAR PERSISTENT _requestSync` → first-scan config validation → clamp to `MinCv/MaxCv` → EU-to-raw linear scale → UNION write of the selected primitive → `BAD` quality holds last good value
- **Fault codes (`E_AnalogOutput_Fault`):** `BadQuality`, `ClampLow`, `ClampHigh`, `BadConfig`

### 8.8.5 Shared Helpers

All four I/O FBs rely on:

- `E_IO_Quality` — `UNKNOWN / BAD / GOOD / CLAMPED`; `stsQuality` carries this tag so downstream aggregators can filter bad data.
- `E_Unit` — engineering-unit tag for the HMI (`BAR`, `DEGREE_CELSIUS`, `PERCENT`, …). Copied into `stsUnit` every cycle.
- `U_IoRaw_In` / `U_IoRaw_Out` — 32-bit UNION exposed only on analog blocks, described in §8.1.1.
- `F_GetTaskCycleTime` — returns the task dt; used by `FB_AnalogInput` to initialise its filter on first scan.
- `FB_LPF_FirstOrder_IIR` — exponential low-pass filter; tunable by `cfgFilterTau`.

