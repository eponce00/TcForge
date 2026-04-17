# 8 I/O Binding

How TcForge devices connect to physical Beckhoff hardware. The library stays portable by isolating every hardware reference behind a single struct per device. This doc covers the convention, the TwinCAT `@AT` pragmas, and how to scale the pattern from a 20-signal demo to a plant with thousands of I/O.

> **Navigation:** [← Architecture](7-Architecture.md) · [README](../README.md)

---

## 8.1 The `_IO` Struct Convention

Every device ships with three structs: `_Cfg`, `_Sts`, `_IO`. The `_IO` struct is the **only** place hardware symbols appear inside the library.

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
- Type is always primitive (`BOOL`, `INT`, `REAL` …), never a nested struct.
- Naming mirrors the field tag: `inFbkAdvanced`, `outValveAdvance`.

The device FB takes the struct by **reference**:

```iecst
FUNCTION_BLOCK FB_TwoPosActuator EXTENDS FB_DeviceBase IMPLEMENTS I_Abortable
VAR_IN_OUT
    io : ST_TwoPosActuator_IO;
END_VAR
```

`VAR_IN_OUT` is mandatory — it's the only way a called FB can both read inputs and write outputs without copying the whole struct each cycle.

---

## 8.2 The `@AT %I* / %Q*` Pragma

`%I*` / `%Q*` creates an **unresolved** PLC variable that shows up under the PLC instance in the TwinCAT solution as an unmapped symbol. You link it in the I/O tree the same way you'd link any Task → Device symbol, by drag-and-drop or right-click → **Change Link**.

Benefits:

- The library compiles with **zero** hardware attached — no terminals, no EtherCAT slaves required for CI builds.
- The same library runs on different hardware by relinking in the consuming project.
- The symbol survives `Build → Clean` because it's part of the `.tmc` / `.tpy`.

What `%I*` does **not** do: it does not auto-allocate. The compiler fails the Activate step until every `*` is linked. This is a feature — you'll never silently deploy unwired I/O.

---

## 8.3 Where the `_IO` Struct Lives

The library defines the **type** (`ST_TwoPosActuator_IO`). The consuming application creates the **instance** and passes it into the device. Two common shapes:

### 8.3.1 Inline (small projects, < ~50 devices)

Declare alongside the device FB, in the program that owns the device:

```iecst
PROGRAM PRG_Station1
VAR
    ioClamp  : ST_TwoPosActuator_IO;
    fbClamp  : FB_TwoPosActuator;
END_VAR

fbClamp(io := ioClamp, cfg := cfgClamp, sts => stsClamp);
```

Link the four unresolved symbols (`ioClamp.inFbkAdvanced`, etc.) directly against your terminals.

### 8.3.2 Centralized GVL (large projects, ≥ ~50 devices)

Put all `_IO` instances in a single GVL so the I/O tree shows a flat, searchable list. This is the pattern to adopt once you've got more than one machine section or multiple engineers linking I/O.

```iecst
{attribute 'qualified_only'}
VAR_GLOBAL
    CLAMP_A : ST_TwoPosActuator_IO;
    CLAMP_B : ST_TwoPosActuator_IO;
    EJECTOR : ST_TwoPosActuator_IO;
    SENSOR_PART_PRESENT : ST_DigitalInput_IO;
    // ... one line per device, sorted by functional area
END_VAR
```

```iecst
// Station program passes pointers/refs into the device FBs
fbClamp_A(io := GVL_HW.CLAMP_A, ...);
fbClamp_B(io := GVL_HW.CLAMP_B, ...);
fbEjector(io := GVL_HW.EJECTOR, ...);
```

Advantages at scale:

- I/O mapping is done in one file; program logic lives elsewhere.
- Renaming a device in logic doesn't disturb I/O links.
- Searching the `.tmc` / `.tpy` for a terminal lookup is trivial.
- Version-control diffs for wiring changes are localized to `GVL_HW`.

---

## 8.4 When to Add a HAL Layer

The `_IO` struct **is** the HAL for most projects. You only need an extra mapping layer when one of the following is true:

1. **Signal conditioning** is needed before the raw bit reaches the device — denoise, scale, unit conversion, range clamp.
2. **Virtualization / simulation** — you want to run the logic without hardware, driven by a simulator that writes the "field side" of the struct.
3. **Redundancy / voting** — three feedbacks fold into one logical feedback before reaching the device.
4. **Sub-millisecond remapping** — e.g. rerouting a spare channel at runtime without recompiling.

When any of these apply, introduce a thin mapping program that runs **before** your device FBs each cycle:

```iecst
PROGRAM PRG_HAL_Wiring
VAR_IN_OUT
    hw : ST_PlantHardware;   // nested struct of every device _IO
END_VAR

// Example: scale a 4-20 mA analog input to engineering units before the device sees it
GVL_HW.TANK_LEVEL.rScaled :=
    F_LinearScale(raw := GVL_HW.TANK_LEVEL.inRaw, inLo := 6400, inHi := 32000, outLo := 0.0, outHi := 100.0);

// Example: vote 2oo3 on a safety feedback
GVL_HW.EXIT_GATE.inFbkClosed :=
    (fbkA AND fbkB) OR (fbkA AND fbkC) OR (fbkB AND fbkC);
```

Call `PRG_HAL_Wiring` at the top of `PlcTask`, then call your station programs. Keep device FBs consuming `GVL_HW.*` exactly as in §8.3.2 — they never know a HAL layer exists.

---

## 8.5 Anti-Patterns

- **Hardware symbols inside the FB.** Never put `AT %I*` on a variable inside `FB_*`. The library loses portability.
- **Nested `_IO` structs.** An `_IO` struct referencing another `_IO` struct. TwinCAT's Symbol Mapping can't drill through nested structs cleanly — keep them flat.
- **Mixing `in*` and `out*` in the same word / byte.** You'll get tool confusion and link errors. One direction per struct member.
- **Computing in the FB body before using the IO value.** All conditioning belongs in the HAL program (§8.4), not in the device FB. Keep the device "dumb" about wiring.
- **`_IO` as `VAR_INPUT` / `VAR_OUTPUT` instead of `VAR_IN_OUT`.** Passing by value copies the whole struct every cycle and breaks the bidirectional write-back for outputs.

---

## 8.6 Checklist for a New Hardware-Connected Device

1. Define `ST_<Dev>_IO` with flat `in*` / `out*` fields, each on `%I*` / `%Q*`.
2. Device FB takes `io : ST_<Dev>_IO` as `VAR_IN_OUT`.
3. Consuming application instantiates the struct in `GVL_HW` (or inline for small projects).
4. Link the unresolved symbols in the TwinCAT solution I/O tree.
5. If signal conditioning is needed, add the pre-processing to `PRG_HAL_Wiring` — not to the device FB.
6. Device's `_Sts` reports the **conditioned, logical** state. Raw bits stay behind the `_IO` boundary.
