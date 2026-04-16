# TwinCAT Open Library

An open-source TwinCAT 3 PLC library for industrial automation. It provides reusable, tested function blocks that follow consistent patterns — so you can build reliable automation systems without reinventing common control logic.

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

## 2 Repository Layout

```
TwinCAT/
  Core.sln                  Solution entry point
  Core/                     Library PLC project
    Modules/
      Common/               E_Requester, E_RpcMethodResponse, F_ValidateRequester
      Sequencing/
        StateMachine/       FB_StateMachine, FB_Step, FB_SequenceStep + DUTs
        Permissives/        FB_Permissives + ST_PermIntlk_*
      Pneumatics/
        TwoPosActuator/     FB_TwoPosActuator + DUTs
  CoreExample/              Example PLC application (MAIN + 6 sequences)
docs/                       Design documentation
```

---

## 3 Getting Started

1. Open `TwinCAT/Core.sln` in TwinCAT XAE (Visual Studio).
2. Build the solution.
3. Explore `CoreExample` for a working implementation with homing, running, stopping, pausing, aborting, and proceeding sequences.
4. Use `Core` as the reusable library — adapt the example sequences to your machine.

---

## 4 Documentation Index

| # | Document | Description |
|---|----------|-------------|
| 1 | [Programming Standards](docs/Programming-Standards.md) | Coding conventions, naming, folder layout, FB structure patterns |
| 2 | [Command Source Control](docs/Command-Source-Control.md) | Requester validation, source locking, method pattern |
| 3 | [RPC Method Response](docs/RPC-Method-Response.md) | Standardized response codes, method inventory, OPC UA usage |
| 4 | [HMI Integration](docs/HMI-Integration.md) | OPC UA pragmas, cfg/sts exposure, RPC method connectivity |

Each document uses section numbering consistent with this index (e.g., Programming Standards = Chapter 1, sections 1.1–1.x).

---

## 5 License

This library is open source. See [LICENSE](LICENSE) for details.
