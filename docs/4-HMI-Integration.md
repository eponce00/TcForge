# 4 HMI Integration

This document describes the OPC UA / HMI integration strategy for function blocks. The PLC exposes `cfg`, `sts`, and RPC methods directly — no parallel HMI structures.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [Command Source Control](2-Command-Source-Control.md) · [RPC Method Response](3-RPC-Method-Response.md) · [Sequencing →](5-Sequencing.md)

---

## 4.1 Design Philosophy

| Principle | Description |
|-----------|-------------|
| Direct exposure | `cfg` and `sts` are the values operators see — no `ST_*_HMI` mirrors |
| Composed modules | Permissives and interlocks appear as nested FB instances with their own tags |
| Read-only data plane | Structures use read-only OPC access (`Access := '1'`) |
| Commands via RPC | Writes use OPC UA method calls, not writable tags |

### 4.1.1 Benefits

- **Less duplication** — no second copy of status for the HMI.
- **Single source of truth** — `cfg` and `sts` are authoritative.
- **Simpler maintenance** — new fields are automatically OPC-visible when pragmas are correct.
- **Fewer sync bugs** — no drift between PLC logic and an HMI mirror.

---

## 4.2 OPC UA Pragma Reference

### 4.2.1 Pragma Summary

| Pragma | Purpose | Notes |
|--------|---------|--------|
| `{attribute 'OPC.UA.DA' := '1'}` | Expose to OPC | `'1'` = visible, `'0'` = hidden |
| `{attribute 'OPC.UA.DA.Access' := '1'}` | Read-only access | `'1'` = read, `'3'` = read/write |
| `{attribute 'OPC.UA.DA.StructuredType' := '1'}` | Expose as structured type | Required on structure types |
| `{attribute 'OPC.UA.DA.Description' := '...'}` | OPC node description | Human-readable |
| `{attribute 'TcRpcEnable' := '1'}` | Enable RPC method call | Required on callable methods |
| `{attribute 'TcEncoding' := 'UTF-8'}` | String encoding | For `STRING` types |

### 4.2.2 Function Block Declaration Pattern

```iecst
{attribute 'OPC.UA.DA' := '1'}
FUNCTION_BLOCK PUBLIC FB_Example

VAR_INPUT
    {attribute 'OPC.UA.DA' := '1'}
    {attribute 'OPC.UA.DA.Access' := '1'}  // Read-only
    cfg : ST_Example_Config;
    
    {attribute 'OPC.UA.DA' := '0'}         // Hide physical I/O
    inpPv AT %I* : BOOL;
END_VAR

VAR_OUTPUT
    {attribute 'OPC.UA.DA' := '1'}
    {attribute 'OPC.UA.DA.Access' := '1'}  // Read-only
    sts : ST_Example_Status;
END_VAR

VAR
    {attribute 'OPC.UA.DA' := '0'}         // Hide working variables
    _timer : TON;
END_VAR
```

Design rules:

1. Expose the FB at the top level.
2. Expose `cfg` and `sts` with read-only access.
3. Expose composed FBs that carry operator-relevant data.
4. Hide internals (timers, raw I/O, working variables).
5. Use RPC methods for all operator commands.

---

## 4.3 Structure Patterns

### 4.3.1 Config and Status Structures

Mark at the **type** level with `StructuredType`:

```iecst
{attribute 'OPC.UA.DA' := '1'}
{attribute 'OPC.UA.DA.Access' := '1'}
{attribute 'OPC.UA.DA.StructuredType' := '1'}
TYPE ST_Example_Config :
STRUCT
    {attribute 'OPC.UA.DA.Description' := 'Maximum allowed speed in RPM'}
    nMaxSpeedRPM : UINT := 1800;
    
    {attribute 'OPC.UA.DA.Description' := 'Process gain factor'}
    fGain : REAL := 1.0;
END_STRUCT
END_TYPE
```

### 4.3.2 Properties for Derived Values

Use properties with OPC attributes when values are computed:

```iecst
{attribute 'OPC.UA.DA.Property' := '1'}
{attribute 'monitoring' := 'call'}
PROPERTY bIsFaulted : BOOL
```

> **Note:** PLC properties on OPC require TwinCAT 3.1 Build 4024+. Use both `OPC.UA.DA.Property` and `monitoring := 'call'`.

---

## 4.4 RPC Method Pattern

```iecst
{attribute 'TcRpcEnable' := '1'}
METHOD PUBLIC Advance : E_RpcMethodResponse
VAR_INPUT
    eRequester : E_Requester := E_Requester.PROG;
END_VAR
// Validate and execute...
```

Requirements:

1. Parent FB exposed to OPC UA: `{attribute 'OPC.UA.DA' := '1'}`
2. Method has RPC enabled: `{attribute 'TcRpcEnable' := '1'}`
3. Method is `PUBLIC`

See [§3 RPC Method Response](3-RPC-Method-Response.md) for return codes.

---

## 4.5 New Function Block Checklist

When adding a new FB with HMI/OPC support:

1. Add `{attribute 'OPC.UA.DA' := '1'}` to the function block declaration.
2. Add OPC attributes to `cfg` (`OPC.UA.DA := '1'`, `Access := '1'`).
3. Add OPC attributes to `sts` (`OPC.UA.DA := '1'`, `Access := '1'`).
4. Add `{attribute 'OPC.UA.DA.StructuredType' := '1'}` to `cfg` and `sts` type definitions.
5. Add `{attribute 'OPC.UA.DA.Description' := '...'}` to each field in `cfg` and `sts`.
6. Leave composed FBs visible when operators need them; hide only by design.
7. Add OPC attributes to relevant properties.
8. Add `{attribute 'TcRpcEnable' := '1'}` to all public command methods.

---

## 4.6 What to Avoid

- **No `ST_*_HMI` structures** — use `cfg` / `sts` directly.
- **No `_UpdateHMI()` methods** — derive values in the main body.
- **No writable OPC tags for commands** — use RPC methods exclusively.
- **No ad-hoc command booleans** — all commands go through typed methods with `E_RpcMethodResponse`.

---

## 4.7 Sequencing HMI Pattern

For the sequencing module, the HMI reads the active step directly from the state machine:

- `FB_StateMachine.StepInfo.CurrentStep`
- `FB_StateMachine.StepInfo.CurrentStepName`
- `FB_StateMachine.StepInfo.NextStep`
- `FB_StateMachine.StepInfo.StepTimerSeconds`
- `FB_StateMachine.StepPermCfg`
- `FB_StateMachine.StepPermStatus`

This keeps the HMI bound to the one object that owns the sequence rather than browsing individual `FB_Step` instances in each program.

Dynamic branching is still fully online-change friendly: the sequence program recalculates `nNextStep` every scan, and the active step hands that target back to the state machine only after `Exiting` completes.
