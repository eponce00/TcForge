# 1 Programming Standards

These standards govern the `TcForge` library and any projects built on it. They ensure consistency across all function blocks, from device-level actuators to the state machine.

> **Navigation:** [← README / TOC](../README.md) · [Architecture →](2-Architecture.md)

---

## 1.1 POU Categories

| Category | Purpose | Examples |
| --- | --- | --- |
| Common | Shared types, enums, and validation helpers used across all modules | `E_Requester`, `E_RpcMethodResponse`, `F_ValidateRequester` |
| Sequencing | State machine, sequence steps, and permissive evaluation | `FB_StateMachine`, `FB_Step`, `FB_Permissives` |
| Pneumatics | Physical actuator control with feedback monitoring | `FB_TwoPosActuator` |
| IO | Digital / analog field I/O with scaling, filtering, quality watchdogs | `FB_DigitalInput`, `FB_AnalogInput`, `FB_AnalogOutput` |
| Alarms | Process-condition detectors sharing a uniform status / ack surface | `FB_AlarmThreshold`, `FB_AlarmLimit`, `FB_AlarmDeviation`, `FB_AlarmRateOfChange` |

---

## 1.2 Project Organization Philosophy

The library is organized around **modules** — self-contained domains of functionality (e.g., sequencing, pneumatics, analog control). Each module groups its function blocks and related DUTs together, so everything you need to understand a module lives in one place.

Principles:

- **One module, one folder** — each module has its own directory containing its FBs, DUTs, and any sub-modules.
- **One POU per file** — each function block gets its own `.TcPOU` file; each DUT gets its own `.TcDUT` file.
- **Shared types go to Common** — types used by multiple modules live in a shared `Common` module. Types used by only one module stay alongside that module's FB.
- **Nest by domain, not by POU type** — organize by what the code *does* (e.g., `Pneumatics/TwoPosActuator/`), not by what it *is* (e.g., `DUTs/`, `POUs/`). This keeps related code together as the project scales.
- **Flat within a module** — avoid deep nesting inside a single module. If a module grows too large, split it into sub-modules rather than adding hierarchy.

---

## 1.3 Coding Conventions

### 1.3.1 Naming and Casing

| Element | Convention | Examples |
| --- | --- | --- |
| Variables / FB internals | lower camelCase | `stepTimerSeconds`, `faultLatched` |
| Structures / Enums | PascalCase type name | `ST_TwoPosActuator_Cfg`, `E_SM_State` |
| Function Blocks | `FB_[Descriptor]` | `FB_TwoPosActuator`, `FB_StateMachine` |
| Functions | `F_[Descriptor]` | `F_ValidateRequester` |
| Interfaces | `I_[Descriptor]` | `I_Module` |
| Global Variable Lists | `GVL_[Descriptor]` | With `{attribute 'qualified_only'}` |

### 1.3.2 Variable Prefixes

| Prefix | Scope | Examples |
| --- | --- | --- |
| `in*` | `VAR_INPUT` — field data, permissions, feedbacks | `inPermAdv`, `inFbkAdvanced` |
| `out*` | `VAR_OUTPUT` — outputs to field hardware | `outValveAdvance` |
| `cfg` | `VAR_INPUT` — configuration structure | `cfg : ST_TwoPosActuator_Cfg` |
| `sts` | `VAR_OUTPUT` — status structure | `sts : ST_TwoPosActuator_Sts` |
| `_*` | Internal/private variables and helper instances | `_timer`, `_faultLatched`, `_permissives` |
| `alm*` | Alarm instances | `almTimeout`, `almFeedbackFault` |
| `temp*` | Temporary variables for intermediate calculations (methods) | `tempResult`, `tempIndex` |

Rules:
- `cfg` is always `VAR_INPUT`.
- `sts` is always `VAR_OUTPUT`.
- Outputs that feed other FBs or map to hardware should be explicit `VAR_OUTPUT` fields, not buried inside `sts`. The `sts` struct is for operator/diagnostic visibility only.
- Use `temp*` only inside methods, not as FB-level state.

### 1.3.3 Enumerations

Required attributes on all enums:

```iecst
{attribute 'qualified_only'}
{attribute 'strict'}
{attribute 'to_string'}
TYPE E_Example :
(
    VALUE_ONE := 0,
    VALUE_TWO := 1
);
END_TYPE
```

- Values use `UPPER_SNAKE_CASE`.
- Always assign explicit integer values.

### 1.3.4 Structures

Use descriptive suffixes:

| Suffix | Purpose | Example |
| --- | --- | --- |
| `_Cfg` | Configuration (timeouts, options) — always `VAR_INPUT` | `ST_TwoPosActuator_Cfg` |
| `_Sts` | Status (state, booleans, fault info) — always `VAR_OUTPUT` | `ST_TwoPosActuator_Sts` |
| `_IO` | Hardware IO mapping | `ST_TwoPosActuator_IO` |
| `_Request` | Commanded setpoints written by methods — the state that should survive power loss | `ST_SM_StepInfo` |

---

## 1.4 Method-Centric Pattern

All command logic lives inside **methods**. The FB body handles only cyclic monitoring. See [§3 Command Source Control](3-Command-Source-Control.md) for the full command pattern.

### 1.4.1 Method Responsibilities

Each method follows a validation chain:

1. **`F_ValidateRequester(eRequester, bSourceLocked, bFaulted)`** — source lock + fault check
2. **State check** — is the FB in a valid state for this command?
3. **Permissive check** — are required permissives met?
4. **Execute** — write outputs, set state, clear conflicting flags
5. **Book-keep** — call `_AcceptCommand(eRequester)` on acceptance so the fault ring and header record who issued the command.

Safety commands (`Reset`, `Abort`, `Stop`) always accept — they don't call `F_ValidateRequester` at all.

### 1.4.2 Body Responsibilities

The FB body is **cyclic monitoring only**:

- Evaluate permissives (call `FB_Permissives` instances)
- Monitor feedback and detect faults (timeouts, conflicting feedback)
- Update state based on feedback transitions
- Generate status structures and diagnostic strings
- **No command processing** — methods handle that

### 1.4.3 Method Organization

- Use `{attribute 'TcRpcEnable' := '1'}` on all public command methods for OPC UA exposure.
- Private helper methods use `_` prefix.
- Organize methods and properties into **folders** inside the POU for visual clarity in TcXaeShell:

| Folder | Contents |
| --- | --- |
| `Public` | Command methods exposed to callers (`Advance`, `Retract`, `Reset`, `Start`, `Stop`, etc.) |
| `Internal` | Methods accessible within the same library but hidden from consumers — use `METHOD INTERNAL` |
| `Private` | Internal helpers not callable outside the FB — use `METHOD PRIVATE` |
| `Properties` | All properties of the FB grouped together |

**XML structure** — folders are self-closing sibling elements of methods, linked via `FolderPath` attribute:

```xml
<Folder Name="Public" Id="{guid}" />
<Folder Name="Internal" Id="{guid}" />
<Folder Name="Private" Id="{guid}" />
<Folder Name="Properties" Id="{guid}" />
<Method Name="Advance" Id="{guid}" FolderPath="Public\">
  ...
</Method>
<Method Name="SetNextStep" Id="{guid}" FolderPath="Internal\">
  ...
</Method>
<Method Name="_DetectFault" Id="{guid}" FolderPath="Private\">
  ...
</Method>
```

> **Important:** Methods must NOT be nested as children of `<Folder>`. The `FolderPath` attribute on `<Method>` is the only linkage. Trailing backslash is required.

---

## 1.5 Permissives vs Interlocks

These two concepts are often confused but have distinct roles:

**Permissives** are about operational readiness. They check whether conditions are suitable to *begin or continue* an operation. They track real-time conditions without latching — when the condition is met the permissive is OK; when it is not, it is not OK. No acknowledgment required. The moment conditions recover, the permissive automatically becomes OK again.

> Example: A vessel must be above 10% full before filling starts. The permissive tracks level in real time. The instant level drops below 10% it is not OK; the instant it recovers it is OK again. No reset needed.

**Interlocks** are about protection. They prevent unsafe conditions from happening or continuing. Once triggered they may latch and require a deliberate acknowledgment to clear — even if the real-world condition has already recovered. This forces someone to verify it is safe to continue.

> Example: A high-pressure interlock trips at 100 psi. Pressure drops to 90 psi. The interlock stays active. An operator must explicitly clear it: "I have seen the event, understood it, and verified it is safe to proceed."

### 1.5.1 Using FB_Permissives

- Use `FB_Permissives` for all permission and readiness evaluations.
- Map each bit via `MapInput(bitIndex, value)` and name it via `cfg.aNames[bitIndex]`.
- Check `sts.bOK` for the aggregate result.
- Configuration: `ST_Permissive_Config` (bypassable mask, names).
- Status: `ST_Permissive_Status` (bOK, nPermissives, nBypassMask, aFaceplates).
- Per-bit HMI data: `ST_Permissive_Faceplate` (name, stsOK, stsMapped, stsBypassed, cfgBypassable).
- Bypass control via `SetBypass(bitIndex, bEnable)` — only bits marked in `cfg.nBypassable` can be bypassed.
- Permissive instances live on the FB that owns the condition. See [§7 Sequencing](7-Sequencing.md#75-permissives) for the state-machine wiring pattern.

### 1.5.2 Using FB_Interlock

`FB_Interlock` has the same mapping / bypass / faceplate API as `FB_Permissives`, but every mapped bit **latches** when it goes bad and stays bad until `Reset()` is called — even after the real-world condition has recovered. Additional status fields: `nLatched` (per-bit latch state) and `stsLive` / `stsLatched` on each faceplate. Bits that were bad at the moment their mapping stopped are remembered and block `sts.bOK` until `Reset()` is called.

Choose per use case:
- Real-time readiness that should clear itself → `FB_Permissives`
- Safety protection that requires human acknowledgment → `FB_Interlock`

### 1.5.3 Interlock command ordering

When enforcing an interlock that requires commanding a device to its safe state, always **command before mapping the interlock condition**. If you map the interlock first, the device is already interlocked and will reject the safe-state command.

```iecst
// CORRECT: command safe state first, then register the condition
IF bHighPressure THEN
    fbActuator.Retract();                                         // 1. command safe state
END_IF;
fbActuator.advancePermissives.MapInput(0, NOT bHighPressure);    // 2. now lock it out

// WRONG: mapping first locks out the safe-state command
fbActuator.advancePermissives.MapInput(0, NOT bHighPressure);    // ← locks out everything
fbActuator.Retract();                                            // ← rejected: already interlocked
```

---

## 1.6 Persistent Variables

Declare a `VAR PERSISTENT` block only for the last commanded setpoints — the values that must survive a power cycle so outputs resume at the correct value on restart. Everything else (cfg, sts, timers, fault latches, interface references) belongs in the regular `VAR` block.

```iecst
VAR PERSISTENT
    // Last commanded setpoints — restored after power cycle
    _lastSetpoint : REAL;
END_VAR
```

- Always validate persisted values on the first scan before acting on them (clamp to configured limits, check consistency).
- Never place pointers or interface references in `VAR PERSISTENT` — addresses change on download.
- The `PERSISTENT` keyword requires a **1-second UPS** on the IPC for the data to survive uncontrolled power loss. See [§6 Persistent Variables](6-Persistent-Variables.md) for configuration steps and the full decision matrix.

---

## 1.7 Device State Machines and Timers

- Use small explicit enums for device states: `Undefined`, `Retracted`, `Advancing`, `Advanced`, `Retracting`, `Fault`.
- Require feedback transitions to confirm success; otherwise time out to `Fault`.
- Use `TON` timers for motion timeouts. Configure in seconds via `cfg` fields.
- On success, support hold outputs via `cfg` hold options.

---

## 1.8 Status and Faults

- Group public statuses in a `_Sts` struct with `header : ST_DeviceHeader_Sts` as the first field; device-specific fields follow.
- Fault codes use an enum (`E_*_Fault`) with specific reasons. Number codes per the range convention in [§2.3.3](2-Architecture.md#233-fault-code-range-convention).
- Raise faults via the inherited `_Raise(code, source, reason)` helper (see [§2.4](2-Architecture.md#24-fault-book-keeping)). Faults latch until explicitly cleared via `Reset` (which calls `_ClearFault()`).
- `Reset` is always accepted — it does **not** call `F_ValidateRequester`. `F_ValidateRequester(eRequester, bSourceLocked, bFaulted)` takes exactly three inputs; there is no "allow when faulted" or "skip source check" flag.

---

## 1.9 IO Mapping

- Each device holds its I/O as an internal `VAR io : ST_<Dev>_IO` — **never** `VAR_IN_OUT`. Hardware symbols appear only inside `_IO`, linked via `TcLinkTo` on the FB instance. See [§5 I/O Binding](5-IO-Binding.md) for the full contract.
- FB logic only drives `out*` fields; it never writes `in*` fields.

---

## 1.10 Error Handling and Safety

- De-energize all outputs on fault and on undefined state.
- Never energize opposing outputs simultaneously (e.g., advance + retract valves).
- Enter `Undefined` state if feedback is contradictory; fault accordingly.
- Safety commands (`Abort`, `Stop`) always execute regardless of source lock or fault state.

---

## 1.11 GVL Organization

Global Variable Lists hold hardware module instances and shared resources. Well-organized GVLs make it easy to find a signal, determine which panel it belongs to, and understand which fieldbus it uses.

### 1.11.1 Group by physical panel

Declare variables in blocks per physical panel (or junction box). Use a banner comment that states the panel tag, description, and fieldbus:

```iecst
{attribute 'qualified_only'}
VAR_GLOBAL

    // =========================================================================
    // Panel: PNL-01 | Conveyor Skid | EtherCAT
    // =========================================================================

    // --- Analog Inputs ---
    inpConveyorSpeed : REAL;      // Speed feedback [m/min]

    // --- Digital Inputs ---
    inpMotorOK       : BOOL;      // Motor contactor feedback

    // --- Digital Outputs ---
    outMotorRun      : BOOL;      // Motor run command

END_VAR
```

Within each panel block, declare in this order: Analog Inputs → Analog Outputs → Digital Inputs → Digital Outputs → Device modules.

### 1.11.2 Fieldbus suffixes

EtherCAT is the default — no suffix. Use a suffix only for non-EtherCAT signals so the origin is visible at every reference site:

| Fieldbus | Suffix |
|---|---|
| EtherCAT | *(none)* |
| PROFINET | `_PN` |
| EtherNet/IP | `_EIP` |
| Modbus TCP | `_MB` |

Device-level FBs that aggregate raw I/O do not carry a fieldbus suffix — their constituent signals already do.

### 1.11.3 Shared resources GVL

Declare system-wide resources (state machine instances, shared permissive references, interlock condition booleans) in a dedicated GVL (e.g., `GVL_System`) separate from hardware I/O. This keeps hardware GVLs readable and gives shared state a single known location.

---

## 1.12 GVL Initialization Order

TwinCAT does not guarantee initialization order between multiple GVLs by default. If one GVL's constructor injects a reference into an object declared in another GVL, the receiving GVL **must be initialized first** — otherwise the reference points to an uninitialized object.

Use the `{attribute 'global_init_slot'}` pragma to enforce order. A **lower** slot number means **earlier** initialization.

| GVL type | Recommended slot |
|---|---|
| Shared resources (state machines, handlers) | `40100` |
| Hardware / area GVLs | `40200` |

Leave a gap of 100 between tiers so new GVLs can be inserted without renumbering:

```iecst
// GVL_System — shared resources, initialized first
{attribute 'global_init_slot' := '40100'}
{attribute 'qualified_only'}
VAR_GLOBAL
    fbStateMachine : FB_StateMachine;
END_VAR

// GVL_Conveyor — hardware, initialized after shared resources
{attribute 'global_init_slot' := '40200'}
{attribute 'qualified_only'}
VAR_GLOBAL
    inpMotorOK : BOOL;
END_VAR
```

> **Important:** The `{attribute 'global_init_slot'}` pragma must appear on the line immediately above `VAR_GLOBAL` — it applies to the entire GVL. Valid user range: `40001–49989` (values ≤ 40000 are reserved by TwinCAT).
