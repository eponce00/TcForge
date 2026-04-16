# TwinCAT Open Library

An open-source TwinCAT 3 PLC library for industrial automation. Provides reusable function blocks for state machine control, device management, permissive evaluation, and sequence execution — built to scale across automation domains.

## Documentation

- [Programming Standards](../docs/Programming-Standards.md) — coding conventions, naming, folder layout, method-centric pattern
- [Command Source Control](../docs/Command-Source-Control.md) — E_Requester, F_ValidateRequester, source locking
- [RPC Method Response](../docs/RPC-Method-Response.md) — E_RpcMethodResponse codes and usage
- [HMI Integration](../docs/HMI-Integration.md) — OPC UA / HMI connectivity

## TwinCAT Project Entry Points

- Solution: [Core.sln](../TwinCAT/Core.sln)
- Library project: [Core.plcproj](../TwinCAT/Core/Core.plcproj)
- Example project: [CoreExample.plcproj](../TwinCAT/CoreExample/CoreExample.plcproj)

## Module Structure

```
Core/Modules/
  Common/          Shared enums, types, validation functions
  Sequencing/      State machine, sequence steps, permissives
  Pneumatics/      Pneumatic actuator control
```

New modules are added as peer folders under `Modules/`. See [Programming Standards](../docs/Programming-Standards.md) for conventions.
