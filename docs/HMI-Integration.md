# HMI Integration

## Overview

This document describes the OPC UA / HMI integration strategy for function blocks. The PLC exposes **`cfg`**, **`sts`**, and **selected OPC UA properties** directly.

### Design Philosophy

1. **Expose `cfg`, `sts`, and properties directly** — No parallel HMI-only structures.
2. **Composed modules expose themselves** — Alarms, interlocks, and permissives that are OPC-visible appear as nested instances with their own `cfg` / `sts` (and tags) under the parent FB.
3. **Read-only data plane** — Structures and atomic tags use read-only OPC access (`Access := '1'`). Ignition binds to them for display and history only.
4. **Commands via RPC methods** — Writes use OPC UA method calls (`TcRpcEnable`), not writable "command" tags.

### Benefits

- **Less duplication** — No second copy of status for the HMI.
- **Single source of truth** — `cfg` and `sts` are the values operators see.
- **Simpler maintenance** — New status fields are automatically available on OPC when pragmas are correct.
- **Fewer sync bugs** — No drift between PLC logic and a separate HMI mirror.

## TwinCAT Implementation

### OPC UA Pragma Reference

#### Pragma Summary

| Pragma | Purpose | Notes |
|--------|---------|--------|
| `{attribute 'OPC.UA.DA' := '1'}` | Expose to OPC | `'1'` = visible, `'0'` = hidden |
| `{attribute 'OPC.UA.DA.Access' := '1'}` | Read-only access | `'1'` = read, `'3'` = read/write |
| `{attribute 'OPC.UA.DA.StructuredType' := '1'}` | Expose as structured type | Required on structure types |
| `{attribute 'OPC.UA.DA.Description' := '...'}` | OPC node description | Human-readable description |
| `{attribute 'TcRpcEnable' := '1'}` | Enable RPC method call | Required on callable methods |
| `{attribute 'TcEncoding' := 'UTF-8'}` | String encoding | For `STRING` types |

#### Function Block OPC Pattern

**Design principles:**

1. **Expose the FB at the top level** — The function block is visible on OPC.
2. **Expose `cfg` and `sts` directly** — With read-only access for operators.
3. **Expose composed FBs** that should be visible — Alarms, interlocks, and permissives are not hidden if they carry operator-relevant data.
4. **Hide internals** — Working variables, timers, raw I/O as appropriate.
5. **RPC for commands** — No writable OPC tags for operator commands.

**Declaration pattern:**

```iecst
{attribute 'OPC.UA.DA' := '1'}  // Expose FB to OPC
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

#### Config and Status Structure Pattern

Mark config and status structures at the **type** level. Always include `StructuredType`:

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

#### Properties for Derived Values

Use properties with OPC attributes when values are computed or need special handling:

```iecst
{attribute 'OPC.UA.DA.Property' := '1'}
{attribute 'monitoring' := 'call'}
PROPERTY bIsFaulted : BOOL
```

> **Note:** PLC properties on OPC require TwinCAT 3.1 Build 4024+. Use both `OPC.UA.DA.Property` and `monitoring := 'call'`. The parent FB must have `OPC.UA.DA := '1'`.

### Method Pattern (RPC)

```iecst
{attribute 'TcRpcEnable' := '1'}
METHOD PUBLIC SetSetpoint : BOOL
VAR_INPUT
    fSetpoint : REAL;
END_VAR
// Validate and apply...
SetSetpoint := TRUE;
END_METHOD
```

**Requirements:**
1. Function block exposed to OPC UA: `{attribute 'OPC.UA.DA' := '1'}`
2. Method has RPC enabled: `{attribute 'TcRpcEnable' := '1'}`
3. Method is `PUBLIC`

## Adding HMI/OPC Support to a New Function Block

### Checklist

1. Add `{attribute 'OPC.UA.DA' := '1'}` to the function block declaration.
2. Add OPC attributes to `cfg` (`OPC.UA.DA := '1'`, `Access := '1'`).
3. Add OPC attributes to `sts` (`OPC.UA.DA := '1'`, `Access := '1'`).
4. Add `{attribute 'OPC.UA.DA.StructuredType' := '1'}` to the `cfg` and `sts` structure type definitions.
5. Add `{attribute 'OPC.UA.DA.Description' := '...'}` to each field in `cfg` and `sts`.
6. Leave composed FBs visible when operators need them; hide only by design.
7. Add OPC attributes to relevant properties.
8. Add `{attribute 'TcRpcEnable' := '1'}` to all public command methods intended for the HMI.

### What to Avoid

- **No `ST_*_HMI` structures** — Use `cfg` / `sts` directly (and properties).
- **No `_UpdateHMI()`** — Derive in `Evaluate()` or the main body.
- **No writable OPC tags for operator commands** — Use RPC methods.
- **No ad-hoc command booleans** on OPC for operator actions.
