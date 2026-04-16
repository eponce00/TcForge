# TcForge

An open-source TwinCAT 3 PLC library for industrial automation. **TcForge** provides reusable, well-structured function blocks for Beckhoff controllers — so you can build reliable machine software without reinventing common control logic.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 1 Overview

The library is organized into modules, each covering a domain of industrial control:

| Module | Purpose |
| --- | --- |
| **Common** | Shared types, enums, and validation helpers used across all modules |
| **Sequencing** | State machine control, sequence steps with lifecycle, permissive evaluation |
| **Pneumatics** | Pneumatic actuator control with feedback monitoring |

More modules will be added as the library grows (motors, analog control, alarms, etc.).

### 1.1 Key Patterns

| Pattern | Summary |
| --- | --- |
| Method-centric commands | All command logic lives in RPC methods exposed via OPC UA. The FB body handles only cyclic monitoring. |
| Command source control | Every command identifies its source (`PROG` or `OPERATOR`) and can be locked to program-only during automatic operation. |
| Unified validation | `F_ValidateRequester` provides consistent source, fault, and permission checks across all FBs. |
| Permissive system | `FB_Permissives` evaluates safety interlocks with `MapReason` and reports via `sts.OK`. |
| Step lifecycle | `FB_Step` provides `Entry` / `Execute` / `Exiting` phases with per-step permissives and dynamic branching. |

---

## 2 Project Organization

The library is organized around **modules** — self-contained domains of functionality. Each module groups its function blocks and related data types together. Code is organized by *what it does* (e.g., sequencing, pneumatics), not by *what it is* (e.g., DUTs, POUs).

- `TwinCAT/TcForge.sln` — solution entry point
- `TcForge/` — reusable library PLC project, organized into modules
- `TcForgeExample/` — example PLC application consuming the library (MAIN + 6 sequences)
- `docs/` — design documentation

See [§1.2 Project Organization Philosophy](docs/1-Programming-Standards.md#12-project-organization-philosophy) for the full set of principles.

---

## 3 Getting Started

1. Open `TwinCAT/TcForge.sln` in TwinCAT XAE (Visual Studio).
2. Build the solution.
3. Explore `TcForgeExample` for a working implementation with homing, running, stopping, pausing, aborting, and proceeding sequences.
4. Use `TcForge` as the reusable library — adapt the example sequences to your machine.

---

## 4 Documentation Index

| # | Document | Description |
|---|----------|-------------|
| 1 | [Programming Standards](docs/1-Programming-Standards.md) | Coding conventions, naming, organization philosophy, FB structure patterns |
| 2 | [Command Source Control](docs/2-Command-Source-Control.md) | Requester validation, source locking, method pattern |
| 3 | [RPC Method Response](docs/3-RPC-Method-Response.md) | Standardized response codes, method inventory, OPC UA usage |
| 4 | [HMI Integration](docs/4-HMI-Integration.md) | OPC UA pragmas, cfg/sts exposure, RPC method connectivity |
| 5 | [Sequencing](docs/5-Sequencing.md) | State model, FB_StateMachine, FB_Step lifecycle, sequence authoring, permissives |
| 6 | [Persistent Variables](docs/6-Persistent-Variables.md) | PERSISTENT vs RETAIN, what to persist, 1-second UPS configuration |

Each document uses section numbering consistent with this index (e.g., Programming Standards = Chapter 1, sections 1.1–1.x).

---

## 5 License

MIT License — free to use, modify, and distribute in any project, commercial or otherwise. See [LICENSE](LICENSE) for the full text.
