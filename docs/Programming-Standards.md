# Programming Standards

These standards govern the `Core` library and any projects built on it. They ensure consistency across all function blocks, from device-level actuators to the state machine.

---

## POU Categories

| Category | Purpose | Examples |
| --- | --- | --- |
| Common | Shared types, enums, and validation helpers used across all modules. | `E_Requester`, `E_RpcMethodResponse`, `F_ValidateRequester` |
| Sequencing | State machine, sequence steps, and permissive evaluation. | `FB_StateMachine`, `FB_SequenceStep`, `FB_Permissives` |
| Pneumatics | Physical actuator control with feedback monitoring. | `FB_TwoPosActuator` |

---

## File and Folder Layout

```
Core/
  Modules/
    Common/              Shared enums, structs, functions
    Sequencing/
      StateMachine/      FB_StateMachine + related DUTs
      Permissives/       FB_Permissives + ST_PermIntlk_*
      SequenceStep/      FB_SequenceStep
    Pneumatics/
      TwoPosActuator/    FB_TwoPosActuator + related DUTs
```

- One DUT per `.TcDUT` file.
- One FB per `.TcPOU` file.
- Place types used by multiple modules in `Modules/Common/`.
- Place types used by a single module alongside that module's FB.

---

## Coding Conventions

### Naming and Casing

- **Variables and FB internals:** lower camelCase — `stepTimerSeconds`, `faultLatched`.
- **Structures and Enums:** PascalCase type names — `ST_TwoPosActuator_Cfg`, `E_SM_State`.
- **Function Blocks:** `FB_[Descriptor]` — `FB_TwoPosActuator`, `FB_StateMachine`.
- **Functions:** `F_[Descriptor]` — `F_ValidateRequester`.
- **Interfaces:** `I_[Descriptor]` — `I_Module`.
- **Global Variable Lists:** `GVL_[Descriptor]` with `{attribute 'qualified_only'}`.

### Variable Prefixes

| Prefix | Scope | Examples |
| --- | --- | --- |
| `in*` | `VAR_INPUT` — field data, permissions, feedbacks | `inPermAdv`, `inFbkAdvanced` |
| `out*` | `VAR_OUTPUT` — outputs to field hardware | `outValveAdvance`, `outRetry` |
| `cfg` | `VAR_INPUT` — configuration structure | `cfg : ST_TwoPosActuator_Cfg` |
| `sts` | `VAR_OUTPUT` — status structure | `sts : ST_TwoPosActuator_Sts` |
| `b*` | Internal BOOL flags | `bSourceLockedToProg` |

- `cfg` is always `VAR_INPUT`.
- `sts` is always `VAR_OUTPUT`.
- Any output from an FB instance that feeds into another FB or maps to hardware should be an explicit `VAR_OUTPUT`, not just a field inside `sts`. The `sts` structure holds additional information useful for debugging and HMI display.

### Enumerations

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

- Values use UPPER_SNAKE_CASE: `STARTING_UP`, `REJECTED_WRONG_STATE`.
- Always assign explicit integer values.

### Structures

Use descriptive suffixes:

| Suffix | Purpose | Example |
| --- | --- | --- |
| `_Cfg` | Configuration (timeouts, options) | `ST_TwoPosActuator_Cfg` |
| `_Sts` | Status (state, booleans, fault info) | `ST_TwoPosActuator_Sts` |
| `_IO` | Hardware IO mapping | `ST_TwoPosActuator_IO` |

---

## Command Source Control

Commands are issued through **RPC methods**, not through input variables. Each method receives an `eRequester` parameter of type `E_Requester` to identify the command source.

### E_Requester

```iecst
E_Requester.PROG      := 0   // Default — PLC program / sequence logic
E_Requester.OPERATOR   := 1   // HMI / OPC UA operator action
```

### Source Locking

Each FB has an internal `bSourceLockedToProg : BOOL` and a `LockSource` method:

```iecst
fbActuator.LockSource(bLock := TRUE);   // Lock to PROG only
fbActuator.LockSource(bLock := FALSE);  // Unlock for OPERATOR
```

When locked, any method call with `eRequester := E_Requester.OPERATOR` is rejected with `REJECTED_SOURCE_NOT_ALLOWED`.

### F_ValidateRequester

All methods use `F_ValidateRequester` as the first validation step:

```iecst
METHOD Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR
---
Advance := F_ValidateRequester(eRequester, bSourceLockedToProg, sts.Faulted, FALSE, FALSE);
IF Advance <> E_RpcMethodResponse.ACCEPTED THEN RETURN; END_IF;
// ... device-specific checks and execution
```

Parameters:
- `eRequester` — who is calling
- `bSourceLocked` — is source locked to PROG
- `bFaulted` — is the FB in a faulted state
- `bAllowWhenFaulted` — TRUE for Reset-type methods
- `bSkipSourceCheck` — TRUE for safety commands (Abort, Stop)

### E_RpcMethodResponse

Every method returns one of:

| Value | Meaning |
| --- | --- |
| `ACCEPTED` | Command executed |
| `REJECTED_SOURCE_NOT_ALLOWED` | Source locked, operator blocked |
| `REJECTED_WRONG_STATE` | FB not in a valid state for this command |
| `REJECTED_FAULTED` | FB is faulted, command not allowed |
| `REJECTED_ALREADY_AT_TARGET` | Already in the requested state |
| `REJECTED_PERMISSIVE_NOT_MET` | Required permissive not satisfied |
| `REJECTED_INTERLOCKED` | Interlock condition active |
| `REJECTED_UNKNOWN` | Catch-all |

### Default Requester

`eRequester` defaults to `E_Requester.PROG`, so PLC sequence code can call methods without specifying it:

```iecst
fbActuator.Advance();                                    // PROG (default)
response := fbActuator.Advance(E_Requester.OPERATOR);   // OPERATOR (from HMI/OPC)
```

---

## Method-Centric Pattern

All command logic lives inside **methods**. The FB body handles only cyclic monitoring.

### Method Responsibilities

Each method follows a validation chain, then executes:

1. **F_ValidateRequester** — source lock + fault check
2. **State check** — is the FB in a valid state for this command?
3. **Permissive check** — are required permissives met? (where applicable)
4. **Interlock check** — are interlocks satisfied? (where applicable)
5. **Execute** — write outputs, set state, clear conflicting flags

Safety commands (Abort, Stop) skip source and fault checks.

### Body Responsibilities

The FB body is **cyclic monitoring only**:

- Evaluate permissives (call FB_Permissives instances)
- Monitor feedback and detect faults (timeouts, conflicting feedback)
- Update state based on feedback transitions
- Generate status structure and diagnostic strings
- **No command processing** — methods handle that

### Methods Organization

- Use `{attribute 'TcRpcEnable' := '1'}` on all public command methods for OPC UA exposure.
- Private helper methods use `_` prefix.
- When an FB has both public RPC methods and private helpers, organize into subfolders:

```
FB_TwoPosActuator/
  Request Methods/     Advance, Retract, AllOff, Reset, LockSource
  Private Methods/     _EvaluateFeedback, _UpdateStatus
```

- **Request Methods** — public methods that modify FB behavior or issue commands.
- **Private Methods** — internal helpers called by the body or other methods.

---

## Permissions (Permissives)

- Use `FB_Permissives` for all permission and interlock evaluations.
- Inputs carrying live permissive bits are `INT` and use two's complement (`-1` = all bits OK).
- Permission configuration (names, descriptions, bypass) is set through `ST_PermIntlk_cfg`.
- Methods check permissive results before executing commands.

---

## State Machines and Timers

- Prefer small explicit enums for device states: `Undefined`, `Retracted`, `Advancing`, `Advanced`, `Retracting`, `Fault`.
- Require feedback transitions to confirm success; otherwise time out to Fault.
- Use `TON` timers for motion timeouts. Configure in seconds via `cfg` fields.
- On success, support hold outputs via `cfg` hold options.

---

## Status and Faults

- Group public statuses in a `_Sts` struct: state enum, booleans, fault code, last fault code.
- Fault codes use an enum (`E_*_Fault`) with specific reasons: `None`, `AdvanceTimeout`, `RetractTimeout`, `BothFeedbackOn`, `UndefinedState`, etc.
- Latch faults until explicitly cleared via a `Reset` method.
- The `Reset` method uses `F_ValidateRequester` with `bAllowWhenFaulted := TRUE`.

---

## IO Mapping

- Use a single `VAR_IN_OUT` IO struct for mapping field IO to the FB: inputs (feedbacks) and outputs (valve commands) together.
- FB logic only drives `out*` fields; it never writes `in*` fields.

---

## Error Handling and Safety

- De-energize all outputs on fault and on undefined state.
- Never energize opposing outputs simultaneously (e.g., advance + retract valves).
- Enter `Undefined` state if feedback is contradictory; fault accordingly.
- Safety commands (Abort, Stop) always execute regardless of source lock or fault state.
# TwinCAT PLC Programming Standards

These standards keep code consistent across libraries and projects. They match the existing State Machine library and extend it for device/actuator FBs.

## Naming and casing

- Use lower camelCase for variables and FB internals: stepTimerSeconds, inPermAdv.
- Prefixes by role:
  - in* for inputs from field/other logic: inPermAdv, inFbkAdvanced.
  - out* for outputs to field/other logic: outValveAdvance.
  - pcmd* for program commands (automatic): pcmdAdvance.
  - ocmd* for operator commands (manual/HMI): ocmdRetract.
  - cmd* for generic commands (e.g., cmdReset).
  - sts* for status flags: stsFaulted, stsMoving.
  - cfg* for configuration: cfgAdvTimeoutS, cfgHoldAtAdvanced.
- Structures/Enums use PascalCase type names: ST_TwoPosActuator_Cfg, ST_TwoPosActuator_Sts, E_TwoPosActuator_State, E_TwoPosActuator_Fault.
- Public FBs use FB_* prefix: FB_TwoPosActuator.

## File and folder layout

- Keep shared DUTs in State Machine/DUTs/<Category>/.
- Keep FBs in State Machine/POUs/ (or a subfolder per device family if desired).
- One DUT per .TcDUT file for clarity.

## Permissions (Permissives)

- Use FB_Permissives for all permission/interlock evaluations.
- Each permission set uses ST_PermIntlk_HMI for HMI binding:
  - Read .cfg from HMI struct to get bypass and descriptions.
  - Write computed .sts.OK and .sts.PermIntlk back to HMI.
- Inputs carrying live permissive bits are INT and use two’s complement -1 to mean “all OK”.

## Commands and modes

- FBs should accept both pcmd* and ocmd* and select the active source by a bool mode input `inAutomatic`:
  - When `inAutomatic=TRUE`, only `pcmd*` are honored.
  - When `inAutomatic=FALSE`, only `ocmd*` are honored.
- Conflicting commands (e.g., advance + retract) after mode selection must fault with a clear code and de-energize outputs.
- Provide cmdReset to clear a latched fault when safe.

## State machines and timers

- Prefer small explicit enums for device states (e.g., Undefined, Retracted, Advancing, Advanced, Retracting, Fault).
- Require feedback transitions to declare success; otherwise time out to Fault.
- Use TON timers for motion timeouts. Configure in seconds via cfg*TimeoutS.
- On success, support hold outputs via cfgHold* options.

## Status and faults

- Group public statuses in a struct (ST_*_Sts): state enum, booleans (stsAdvanced, stsRetracted, stsMoving, stsFaulted), faultCode, and lastFaultCode.
- Fault codes use an enum (E_*_Fault) with specific reasons: None, AdvanceTimeout, RetractTimeout, BothFeedbackOn, UndefinedState, PermissivesNotOK, ConflictingCommands, etc.

## IO mapping

- Prefer a single IN_OUT IO struct for mapping field IO to the FB: inputs (feedbacks) and outputs (valve commands) together.
- FB logic only drives the out* fields; it never writes in* fields.

## HMI integration

- Expose permissive HMI structs (ST_PermIntlk_HMI) per motion direction when relevant, so naming/desc and bypass can be set from HMI.
- Keep FB outputs stable and HMI-friendly (e.g., provide one-shots like osAdvanced/osRetracted if needed by screens).

## Error handling and safety

- De-energize both outputs on fault and on undefined state.
- Never energize opposing valves simultaneously.
- Enter Undefined state if both feedbacks are TRUE or both are FALSE at rest; fault accordingly.

## Example prefixes at a glance

- Inputs: inFbkAdvanced, inPermAdv
- Outputs: outValveAdvance, outValveRetract
- Program commands: pcmdAdvance, pcmdRetract
- Operator commands: ocmdAdvance, ocmdRetract
- Config: cfgAdvTimeoutS, cfgHoldAtAdvanced
- Status: stsMoving, stsFaulted, faultCode
