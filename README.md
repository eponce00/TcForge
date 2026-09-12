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

**Foundation under development — local builds and PLC tests are running; production qualification remains open.**

See [Progress tracker](PROGRESS.md) for completed foundation work, remaining architecture gaps, and qualification tasks. Update it as work progresses.

TcForge is a library for Beckhoff PLC applications, with reusable blocks for sequencing, I/O, pneumatics, and alarms. An example application shows how the modules fit together.

## Modules


| Module     | What it covers                                                                               |
| ---------- | -------------------------------------------------------------------------------------------- |
| Common     | Shared types, enums, validation helpers, `F_Now`, `FB_DeviceBase` (owns the fault ring + header).|
| Sequencing | State machines and sequence steps with an Entry/Execute/Exiting lifecycle, plus permissives. |
| Pneumatics | Actuator control with feedback monitoring.                                                   |
| IO         | `FB_DigitalInput` / `FB_DigitalOutput` / `FB_AnalogInput` / `FB_AnalogOutput` — debounce, pulse modes, UNION-based raw terminals, scaling, IIR filter. Process-limit alarms compose externally via `FB_AlarmLimit`. |
| Alarms     | `FB_AlarmSimple` / `FB_AlarmThreshold` / `FB_AlarmLimit` / `FB_AlarmDeviation` / `FB_AlarmRateOfChange` — uniform debounce / latch / ack / severity / timestamps surface via `FB_AlarmBase` + `I_Alarm`. |


## Conventions

- **Method-centric commands.** Program methods own command logic; Operator RPC wrappers queue selected commands in a bounded mailbox. The owning cyclic task validates and executes them with fixed operator identity, then applies state and output policy.
- **Requester tracking.** Accepted commands record source (`PROG` or `OPERATOR`). The application owns program-only source locking.
- **Shared validation.** `F_ValidateRequester` provides normal source/fault gating; recovery and de-energization commands have explicit device-specific rules.
- **Permissive system.** `FB_Permissives` evaluates mapped conditions and required-mask freshness, reporting through `sts.bOK`.

The docs below cover these in detail.

## Project layout

- `TwinCAT/TcForge.sln`: main development workspace: library source, Example, Testing and Simulation in one TwinCAT project.
- `TwinCAT/TcForgeReference.plcproj`: source-only support library holding the shared reference machine and simulation bridge once; all consumers use this same implementation.
- `TwinCAT/TcForge.Library.sln`: isolated library export.
- `TwinCAT/TcForge.Example.sln`: isolated example runtime.
- `TwinCAT/TcForge.Tests.sln`: isolated test application.
- `TwinCAT/TcForge.Simulation.sln`: isolated simulation runtime.
- `TwinCAT/TcForge/`: the reusable library.
- `TwinCAT/TcForgeExample/`: the integrated clamp reference application; see [its operating contract](docs/11-Reference-Machine.md).
- `TwinCAT/Testing.plcproj`: PLC test project, sharing the reference application source.
- `TwinCAT/Testing/`: PLC test suites and fixtures.
- `python/`: deterministic plant simulation primitives and test infrastructure; see [simulation guide](python/README.md).
- `docs/`: design docs.

## Getting started

Clone the repository and open the solution in TwinCAT XAE on Windows:

```powershell
git clone https://github.com/eponce00/TcForge.git
cd TcForge
```

Open **[TwinCAT/TcForge.sln](TwinCAT/TcForge.sln)** in XAE 3.1.4026.26. Under PLC,
expand **TcForge → TcForge Project** to edit the reusable blocks. Example, Testing
and Simulation reference `[TcForge]` directly. Library edits are available to
their next build without exporting, installing or changing the version. The
source-only `TcForgeReference` project shares application/fixture code without
copying it or adding it to the reusable core library.

```powershell
python scripts/check_repository.py
powershell.exe -NoProfile -File scripts/build_development.ps1
powershell.exe -NoProfile -File scripts/run_tcunit.ps1 -Development -Target <bench-AMS-Net-ID> -Platform "TwinCAT RT (x64)"
```

The development build does not activate a runtime. The test command replaces the
selected bench configuration with the isolated Testing runtime, builds from source,
and verifies individual TcUnit results. Example and Simulation are separate PLC
applications with separate instances; changes are applied to each application
through its own build/login workflow. Simply saving source does not change a
running PLC. The combined workspace does not autostart the test/simulation tasks;
use the isolated scripts when deploying one application.

`scripts/build_twincat.ps1` and `run_tcunit.ps1` without `-Development` retain the
separate exported/installed-artifact qualification workflow. They temporarily
select installed references and restore the source-reference profiles afterward.
See [foundation qualification](docs/10-Qualification.md) for release evidence.

## Documentation

Read the [TcForge documentation site](https://eponce00.github.io/TcForge/) for searchable guides,
or browse the Markdown files below. To preview or update the site, see
[Maintaining this site](docs/documentation-site.md).

| #   | Document                                                   | Covers                                                          |
| --- | ---------------------------------------------------------- | --------------------------------------------------------------- |
| 1   | [Programming Standards](docs/1-Programming-Standards.md)   | Naming, organization, FB structure patterns.                    |
| 2   | [Architecture](docs/2-Architecture.md)                     | `FB_DeviceBase`, unified fault model, device header pattern.    |
| 3   | [Command Source Control](docs/3-Command-Source-Control.md) | Requester validation and source locking.                        |
| 4   | [RPC Method Response](docs/4-RPC-Method-Response.md)       | Response codes and method inventory.                            |
| 5   | [I/O Binding](docs/5-IO-Binding.md)                        | Public signal boundaries and application-owned hardware mapping.   |
| 6   | [Persistent Variables](docs/6-Persistent-Variables.md)     | PERSISTENT vs RETAIN and UPS configuration.                     |
| 7   | [Sequencing](docs/7-Sequencing.md)                         | `FB_StateMachine`, `FB_Step`, authoring sequences, permissives. |
| 8   | [Alarms](docs/8-Alarms.md)                                 | `FB_AlarmBase`, severity model, ack semantics, alarm catalog.   |
| 9   | [HMI Integration](docs/9-HMI-Integration.md)               | OPC UA pragmas, cfg/sts exposure, RPC over OPC UA.              |
| 10  | [Qualification](docs/10-Qualification.md) | Build, PLC tests, restart and commissioning gates. |
| 11  | [Reference Machine](docs/11-Reference-Machine.md) | Owning task, quality, sequencing, shutdown and cyclic integration tests. |


See [toolchain.json](toolchain.json) for the qualification baseline.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for reporting issues, proposing changes, and documenting validation. Include your TwinCAT build and a minimal example when reporting unexpected behavior.

## Related project

[TwinCAT MCP Server](https://github.com/eponce00/twincat-mcp) connects AI clients to TwinCAT build, deployment, testing, and ADS tools. TcForge can be used independently.

## License

MIT. See [LICENSE](LICENSE).

This is an independent project, not affiliated with or endorsed by Beckhoff Automation.
The current foundation contracts and acceptance procedure are in [Foundation qualification](docs/10-Qualification.md).

Simulation and development references: [simulation architecture](docs/12-Simulation.md),
[SPT review](docs/13-SPT-Review.md), and [using TcForge in a project](docs/14-Using-TcForge.md).
