Read the [TcForge documentation site](https://eponce00.github.io/TcForge/) for searchable guides.

<p align="center">
  <img src="img/banner.png" alt="TcForge" width="800"/>
</p>

<h1 align="center">TcForge</h1>

<p align="center">Reusable TwinCAT 3 function blocks for machine control.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"/></a>
  <img src="https://img.shields.io/badge/platform-TwinCAT%203-0098c7" alt="Platform: TwinCAT 3"/>
  <img src="https://img.shields.io/badge/language-Structured%20Text-555555" alt="Language: Structured Text"/>
</p>

<p align="center">
  <a href="#getting-started">Getting started</a> · <a href="#modules">Modules</a> · <a href="#documentation">Documentation</a> · <a href="CONTRIBUTING.md">Contributing</a>
</p>

TcForge is a library for Beckhoff PLC applications, with reusable blocks for sequencing, I/O, pneumatics, and alarms. An example application shows how the modules fit together.

The foundation is under active development; TwinCAT compilation and runtime qualification are pending.

## Getting started

Clone the repository and open the solution in TwinCAT XAE on Windows:

```powershell
git clone https://github.com/eponce00/TcForge.git
cd TcForge
```

Open [`TwinCAT/TcForge.sln`](TwinCAT/TcForge.sln), build the solution, and explore [`TcForgeExample`](TwinCAT/TcForgeExample) for an example consumer. See the [architecture guide](docs/2-Architecture.md) before integrating the library into your application.

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
- `TwinCAT/TcForge/`: the reusable library.
- `TwinCAT/TcForgeExample/`: an example application that consumes the library.
- `TwinCAT/Testing/`: PLC test project.
- `docs/`: design docs.

## Documentation


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


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for reporting issues, proposing changes, and documenting validation. Include your TwinCAT build and a minimal example when reporting unexpected behavior.

## Related project

[TwinCAT MCP Server](https://github.com/eponce00/twincat-mcp) connects AI clients to TwinCAT build, deployment, testing, and ADS tools. TcForge can be used independently.

## License

MIT. See [LICENSE](LICENSE).

This is an independent project, not affiliated with or endorsed by Beckhoff Automation.
