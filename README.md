# TwinCAT Open Library

An open-source TwinCAT 3 PLC library for industrial automation. It provides reusable, tested function blocks that follow consistent patterns — so you can build reliable automation systems without reinventing common control logic.

## What It Provides

The library is organized into modules, each covering a domain of industrial control:

| Module | Purpose |
| --- | --- |
| **Common** | Shared types, enums, and validation helpers used across all modules |
| **Sequencing** | State machine control, sequence step execution, permissive evaluation |
| **Pneumatics** | Pneumatic actuator control with feedback monitoring |

More modules will be added as the library grows (motors, analog control, alarms, etc.).

## Key Patterns

- **Method-centric commands** — All command logic lives in RPC methods exposed via OPC UA. The FB body handles only cyclic monitoring.
- **Command source control** — Every command identifies its source (`PROG` or `OPERATOR`) and can be locked to program-only during automatic operation.
- **Unified validation** — A shared `F_ValidateRequester` function provides consistent source, fault, and permission checks across all FBs.
- **Permissive system** — `FB_Permissives` evaluates safety interlocks and operator permissions with bypass support for maintenance.

## Repository Layout

```
TwinCAT/
  Core.sln              Solution entry point
  Core/                 Library PLC source
    Modules/
      Common/           Shared enums, types, functions
      Sequencing/       State machine, sequence steps, permissives
      Pneumatics/       Pneumatic actuator control
  CoreExample/          Example PLC application
docs/                   Design documentation and standards
```

## Getting Started

1. Open `TwinCAT/Core.sln` in TwinCAT XAE (Visual Studio)
2. Build the solution
3. Explore `CoreExample` for a working implementation with homing, running, stopping, pausing, and aborting sequences

## Documentation

- [Programming Standards](docs/Programming-Standards.md) — coding conventions, naming, folder layout
- [Command Source Control](docs/Command-Source-Control.md) — requester validation and source locking
- [RPC Method Response](docs/RPC-Method-Response.md) — response codes and usage
- [HMI Integration](docs/HMI-Integration.md) — OPC UA connectivity

## Getting Started

1. Open `TwinCAT/Core.sln` in TwinCAT XAE
2. Use `CoreExample` as the reference example for how the library is consumed
3. Use `Core` as the source PLC for the reusable library objects
4. Build the unified solution and adapt the example state programs to your machine
5. Configure safety permissions and HMI interface for your application

This library transforms complex automation sequences into manageable, structured code that's easier to develop, debug, and maintain.
