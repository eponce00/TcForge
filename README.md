# TcForge

A TwinCAT 3 library of reusable function blocks for Beckhoff PLCs, plus an example application that consumes it.

[License: MIT](LICENSE)

## Modules


| Module     | What it covers                                                                               |
| ---------- | -------------------------------------------------------------------------------------------- |
| Common     | Shared types, enums, validation helpers, `F_Now`, `FB_DeviceBase` (owns the fault ring + header).|
| Sequencing | State machines and sequence steps with an Entry/Execute/Exiting lifecycle, plus permissives. |
| Pneumatics | Actuator control with feedback monitoring.                                                   |
| IO         | `FB_DigitalInput` / `FB_DigitalOutput` / `FB_AnalogInput` / `FB_AnalogOutput` — debounce, pulse modes, UNION-based raw terminals, scaling, IIR filter. Process-limit alarms compose externally via `FB_AlarmLimit`. |
| Alarms     | `FB_AlarmSimple` / `FB_AlarmThreshold` / `FB_AlarmLimit` / `FB_AlarmDeviation` / `FB_AlarmRateOfChange` — uniform debounce / latch / ack / severity / timestamps surface via `FB_AlarmBase` + `I_Alarm`. |


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
| 2   | [Architecture](docs/2-Architecture.md)                     | `FB_DeviceBase`, unified fault model, device header pattern.    |
| 3   | [Command Source Control](docs/3-Command-Source-Control.md) | Requester validation and source locking.                        |
| 4   | [RPC Method Response](docs/4-RPC-Method-Response.md)       | Response codes and method inventory.                            |
| 5   | [I/O Binding](docs/5-IO-Binding.md)                        | `ST_*_IO` pattern, `@AT %I*/%Q*`, scaling to plant-sized I/O.   |
| 6   | [Persistent Variables](docs/6-Persistent-Variables.md)     | PERSISTENT vs RETAIN and UPS configuration.                     |
| 7   | [Sequencing](docs/7-Sequencing.md)                         | `FB_StateMachine`, `FB_Step`, authoring sequences, permissives. |
| 8   | [Alarms](docs/8-Alarms.md)                                 | `FB_AlarmBase`, severity model, ack semantics, alarm catalog.   |
| 9   | [HMI Integration](docs/9-HMI-Integration.md)               | OPC UA pragmas, cfg/sts exposure, RPC over OPC UA.              |


See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT. See [LICENSE](LICENSE).