# TcForge

Reusable **TwinCAT 3 function blocks for machine control**: sequencing, I/O,
pneumatics, alarms, and shared device contracts for Beckhoff PLC applications.

[Get started](14-Using-TcForge.md){ .md-button .md-button--primary }
[Browse the source](https://github.com/eponce00/TcForge){ .md-button }

!!! warning "Foundation under development"
    Local builds and PLC tests are running; production qualification remains open.
    Follow the [qualification procedure](10-Qualification.md) before adopting the
    library, and review the [progress tracker](https://github.com/eponce00/TcForge/blob/main/PROGRESS.md)
    for remaining work.

    These guides describe the current development workspace. The accompanying PLC
    and simulation update has not yet been published to `main`, so some described
    files and APIs are not available in the public source checkout yet.

## Build on shared contracts

TcForge provides method-based commands, requester validation, consistent device
status and faults, and application-owned hardware mapping. The integrated clamp
reference application shows how these pieces work together in an owning cyclic task.

| Area | What you will find |
| --- | --- |
| [Architecture](2-Architecture.md) | Device base, scan ownership, fault reporting, and extension patterns. |
| [I/O](5-IO-Binding.md) | Digital and analog signal boundaries and hardware mapping. |
| [Sequencing](7-Sequencing.md) | State machines, steps, permissives, and recovery. |
| [Alarms](8-Alarms.md) | Threshold, limit, deviation, and rate-of-change alarms. |
| [HMI integration](9-HMI-Integration.md) | Operator commands and OPC UA RPC integration. |

## Start with the reference application

1. [Build and install TcForge](14-Using-TcForge.md) in TwinCAT XAE on Windows.
2. Read the [reference machine contract](11-Reference-Machine.md) for scan order,
   operation, and recovery.
3. Follow the [qualification gates](10-Qualification.md), including PLC tests and
   restart checks.

## Develop and contribute

Use the [programming standards](1-Programming-Standards.md) when adding modules.
The [simulation guide](12-Simulation.md) describes current coverage and planned
live exchange work. See [contributing](https://github.com/eponce00/TcForge/blob/main/CONTRIBUTING.md)
for reporting issues and documenting validation.

TcForge is [MIT licensed](https://github.com/eponce00/TcForge/blob/main/LICENSE).
The related [TwinCAT MCP Server](https://github.com/eponce00/twincat-mcp) provides
TwinCAT build, deployment, testing, and ADS tools; TcForge can be used independently.
