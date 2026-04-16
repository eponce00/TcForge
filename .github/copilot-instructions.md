# TwinCAT Open Library

An open-source TwinCAT 3 PLC library for industrial automation. Provides reusable function blocks for state machine control, device management, permissive evaluation, and sequence execution — built to scale across automation domains.

## Documentation

- [Programming Standards](../docs/1-Programming-Standards.md) — coding conventions, naming, folder layout, method-centric pattern
- [Command Source Control](../docs/2-Command-Source-Control.md) — E_Requester, F_ValidateRequester, source locking
- [RPC Method Response](../docs/3-RPC-Method-Response.md) — E_RpcMethodResponse codes and usage
- [HMI Integration](../docs/4-HMI-Integration.md) — OPC UA / HMI connectivity

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

## TwinCAT XML File Editing Rules

When creating or editing `.TcPOU` and `.TcDUT` files:

- **No UTF-8 BOM** — TcXaeShell rejects XML with BOM bytes. The `create_file` tool adds BOM; use `[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding $false))` instead.
- **`create_file` race condition** — may append to recently-deleted files. Always verify a single `<?xml` declaration.
- **Folder elements in TcPOU** — `<Folder>` IS supported inside `<POU>` but as a **sibling** of `<Method>`, not a wrapper. Use self-closing `<Folder Name="Private" Id="{...}" />` and reference via `FolderPath="Private\"` attribute on `<Method>`. Nesting `<Method>` as a child of `<Folder>` crashes TcXaeShell.
- **GUIDs** — Fabricated GUIDs for new methods/folders are fine.
- **LineIds** — `Count="0"` is acceptable.
- **Encoding** — Avoid PowerShell `Set-Content` which can change encoding; use `[System.IO.File]` methods.

## Build

- Use the `twincat_build` MCP tool with `solutionPath: "F:\Twincat Projects\Twincat_State_Machine\TwinCAT\Core.sln"`.
- If build fails with RPC error, use the `twincat_kill_stale` MCP tool to kill stale TcXaeShell/devenv processes, then retry.
- TwinCAT version: 3.1.4026.17, TcPOU ProductVersion: 3.1.4026.12
- Available libraries: Tc2_Standard, Tc2_System, Tc3_Module (NO Tc2_Utilities)
- `Exit` is a reserved keyword in Structured Text.
