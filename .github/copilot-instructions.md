# TcForge contributor instructions

Read README.md and docs/10-Qualification.md before changing behavior.

- Library: TwinCAT/TcForge/TcForge.plcproj; isolated tests: TwinCAT/TcForge.Tests.sln.
- Develop in TwinCAT/TcForge.sln using source project references. Keep shared
  reference/fixture code in TcForgeReference, outside the core library. Source-only
  libraries have no runtime instances or solution boot-project build entries.
- Preserve UTF-8 without BOM for TwinCAT XML. Methods are POU children; folders
  are siblings referenced with FolderPath, never containers for methods.
- One task owns each FB. Preserve command precedence and final output gating.
- Operator RPC wrappers only submit/query the bounded mailbox; fixed OPERATOR
  identity is applied by the owning cyclic dispatcher. Never call core command
  logic directly from RPC. Validate requester identity before command mutations.
- Only Operator wrappers may have TcRpcEnable. Core commands,
  mapping, source locking and bypass mutation remain application-only.
- Required-condition configuration is independent of refreshed live mappings.
- Add public-behavior regressions for contract changes. Multi-scan tests retain
  device/timer instances in suite scope. Never claim XML checks compile ST.
- Run python scripts/check_repository.py and python -m unittest discover -s scripts/tests -v.
- Dependency versions are locked; current runtime evidence is in PROGRESS.md.
  Do not mark toolchain qualification verified from source checks or development runs.
- Exit is reserved in ST; use Exiting. Preserve supported XML Folder/Method layout.
