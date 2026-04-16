# 1 Programming Standards

These standards govern the `Core` library and any projects built on it. They ensure consistency across all function blocks, from device-level actuators to the state machine.

> **Navigation:** [← README](../README.md) · [Command Source Control →](2-Command-Source-Control.md) · [RPC Method Response →](3-RPC-Method-Response.md) · [HMI Integration →](4-HMI-Integration.md)

---

## 1.1 POU Categories

| Category | Purpose | Examples |
| --- | --- | --- |
| Common | Shared types, enums, and validation helpers used across all modules | `E_Requester`, `E_RpcMethodResponse`, `F_ValidateRequester` |
| Sequencing | State machine, sequence steps, and permissive evaluation | `FB_StateMachine`, `FB_Step`, `FB_Permissives` |
| Pneumatics | Physical actuator control with feedback monitoring | `FB_TwoPosActuator` |

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
| `b*` | Internal BOOL flags | `bSourceLockedToProg` |

- `cfg` is always `VAR_INPUT`.
- `sts` is always `VAR_OUTPUT`.
- Outputs that feed other FBs or map to hardware should be explicit `VAR_OUTPUT` fields, not buried inside `sts`.

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
| `_Cfg` | Configuration (timeouts, options) | `ST_TwoPosActuator_Cfg` |
| `_Sts` | Status (state, booleans, fault info) | `ST_TwoPosActuator_Sts` |
| `_IO` | Hardware IO mapping | `ST_TwoPosActuator_IO` |

---

## 1.4 Method-Centric Pattern

All command logic lives inside **methods**. The FB body handles only cyclic monitoring. See [§2 Command Source Control](2-Command-Source-Control.md) for the full command pattern.

### 1.4.1 Method Responsibilities

Each method follows a validation chain:

1. **`F_ValidateRequester`** — source lock + fault check
2. **State check** — is the FB in a valid state for this command?
3. **Permissive check** — are required permissives met?
4. **Execute** — write outputs, set state, clear conflicting flags

Safety commands (`Stop`, `Abort`) skip source and fault checks.

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
- Place methods directly under `<POU>` — **do not** use `<Folder>` elements inside TcPOU XML (this crashes TcXaeShell 3.1.4026).

---

## 1.5 Permissives

- Use `FB_Permissives` for all permission and interlock evaluations.
- Call `MapReason(nIndex, sDescription, bValue)` to map each permissive bit.
- Check `sts.OK` for the aggregate result.
- Inputs carrying live permissive bits are `INT` using two's complement (`-1` = all bits OK).
- Permission configuration (names, descriptions, bypass) is set through `ST_PermIntlk_cfg`.

---

## 1.6 State Machines and Timers

- Prefer small explicit enums for device states: `Undefined`, `Retracted`, `Advancing`, `Advanced`, `Retracting`, `Fault`.
- Require feedback transitions to confirm success; otherwise time out to `Fault`.
- Use `TON` timers for motion timeouts. Configure in seconds via `cfg` fields.
- On success, support hold outputs via `cfg` hold options.

---

## 1.7 Step Lifecycle (FB_Step)

`FB_Step` provides three lifecycle phases per sequence step:

| Phase | Purpose |
| --- | --- |
| `Entry` | One-shot on step activation — initialize variables, command actuators |
| `Execute` | Continuous while step is active — monitor conditions, call `MapPerm` |
| `Exiting` | One-shot when all permissives pass — cleanup before advancing |

Additional capabilities:

- `MapPerm(nIndex, sDescription, bValue)` — map per-step permissives.
- `SetNextStep(nStep)` — override default `nNextStep` for dynamic branching.

---

## 1.8 Status and Faults

- Group public statuses in a `_Sts` struct: state enum, booleans, fault code, last fault code.
- Fault codes use an enum (`E_*_Fault`) with specific reasons.
- Latch faults until explicitly cleared via a `Reset` method.
- `Reset` uses `F_ValidateRequester` with `bAllowWhenFaulted := TRUE`.

---

## 1.9 IO Mapping

- Use a single `VAR_IN_OUT` IO struct for mapping field IO: inputs (feedbacks) and outputs (valve commands) together.
- FB logic only drives `out*` fields; it never writes `in*` fields.

---

## 1.10 Error Handling and Safety

- De-energize all outputs on fault and on undefined state.
- Never energize opposing outputs simultaneously (e.g., advance + retract valves).
- Enter `Undefined` state if feedback is contradictory; fault accordingly.
- Safety commands (`Abort`, `Stop`) always execute regardless of source lock or fault state.
