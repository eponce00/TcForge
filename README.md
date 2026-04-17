# TcForge

A TwinCAT 3 library of reusable function blocks for Beckhoff PLCs, plus an example application that consumes it.

[License: MIT](LICENSE)

## Modules


| Module     | What it covers                                                                               |
| ---------- | -------------------------------------------------------------------------------------------- |
| Common     | Shared types, enums, validation helpers, `FB_DeviceBase`, `FB_FaultHandler`, core interfaces.|
| Sequencing | State machines and sequence steps with an Entry/Execute/Exiting lifecycle, plus permissives. |
| Pneumatics | Actuator control with feedback monitoring.                                                   |
| IO         | Digital/Analog input and output skeletons wired to `FB_DeviceBase`.                          |


## Conventions

- **Method-centric commands.** Command logic lives in RPC methods exposed over OPC UA. The FB body only does cyclic monitoring.
- **Requester tracking.** Every command records its source (`PROG` or `OPERATOR`) and can be locked to program-only while automatic is running.
- **Unified validation.** `F_ValidateRequester` runs the same source / fault / permission check everywhere.
- **Permissive system.** `FB_Permissives` evaluates interlocks with `MapReason` and reports through `sts.OK`.

The docs below cover these in detail.

## Project layout

- `TwinCAT/TcForge.sln`: solution entry point.
- `TcForge/`: the reusable library.
- `TcForgeExample/`: an example application that consumes the library.
- `docs/`: design docs.

## Getting started

Open `TwinCAT/TcForge.sln` in TwinCAT XAE, build it, and browse `TcForgeExample` for a working consumer. Use `TcForge` as the library in your own project.

## Docs


| #   | Document                                                   | Covers                                                          |
| --- | ---------------------------------------------------------- | --------------------------------------------------------------- |
| 1   | [Programming Standards](docs/1-Programming-Standards.md)   | Naming, organization, FB structure patterns.                    |
| 2   | [Command Source Control](docs/2-Command-Source-Control.md) | Requester validation and source locking.                        |
| 3   | [RPC Method Response](docs/3-RPC-Method-Response.md)       | Response codes and method inventory.                            |
| 4   | [HMI Integration](docs/4-HMI-Integration.md)               | OPC UA pragmas, cfg/sts exposure, RPC over OPC UA.              |
| 5   | [Sequencing](docs/5-Sequencing.md)                         | `FB_StateMachine`, `FB_Step`, authoring sequences, permissives. |
| 6   | [Persistent Variables](docs/6-Persistent-Variables.md)     | PERSISTENT vs RETAIN and UPS configuration.                     |
| 7   | [Architecture](docs/7-Architecture.md)                     | `FB_DeviceBase`, `FB_FaultHandler`, interfaces, header pattern. |
| 8   | [I/O Binding](docs/8-IO-Binding.md)                        | `ST_*_IO` pattern, `@AT %I*/%Q*`, scaling to plant-sized I/O.   |


## License

MIT. See [LICENSE](LICENSE).