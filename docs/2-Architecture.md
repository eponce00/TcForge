# 2 Architecture

TcForge is a modular PLC library. Device behavior, sequence orchestration and
process alarms are separate responsibilities.
see [qualification](10-Qualification.md) before adopting it.

## Ownership and scan contract

One task owns each FB instance and all program calls to its methods. Consumers must not
share mutable instances across PLC tasks. The application owns command ordering,
configuration, IO mapping and the authenticated external-command boundary.

A control cycle samples inputs, evaluates conditions, consumes commands, updates
state, applies the final output policy and publishes status. State-machine requests
are consumed once with Abort > Stop > ordinary command precedence. Device methods
may record intent immediately; observe the next cyclic status for application of
that intent. RPC wrappers only submit to the instance mailbox. The owning cyclic
body validates and dispatches remote commands. See [source control](3-Command-Source-Control.md).

## Device base

`FB_DeviceBase` owns source arbitration, accepted-command timestamps, active faults,
last-fault metadata, and an eight-entry persistent fault ring. Device FBs extend it
and publish a `ST_DeviceHeader_Sts` through `_UpdateHeader`.

- `_Raise(code, source, reason)` ignores zero and repeated current codes. A different
  code records a new entry. The ring index is bounded before indexing restored data.
- `_ClearFault()` clears active diagnostic state; history remains.
- `IsFaulted()` is the authoritative active-fault query. RPC response codes describe
  one command request and are not stored as device faults.
- `Reset()` clears base diagnostics. Overrides define device recovery: output and
  actuator resets also inhibit output; the state machine requires STOPPED, good
  running interlocks and no active submodule fault. Reset is not a stop command.
- `LockSource()` arbitrates program/operator commands; it is application-only.
- `header.ready` means no fault, no busy condition and source unlocked. It is not
  permission to execute every command. Use command results and device readiness.

Device status publishes after the cyclic body. A method invoked afterward can
change fault/intent before that snapshot is refreshed. Use `IsFaulted()` for live
logic; do not use an older status snapshot as the internal fault gate.

## Devices and alarms

Digital/analog output blocks implement explicit startup, invalid-quality and
fallback behavior. The two-position actuator applies output permissions from the
final state, so a detected fault removes coils in the same cyclic call. Abort and
Reset inhibit hold coils until a new motion command is accepted.

`FB_AlarmBase` and `I_Alarm` provide composed process alarms. Process limits are not
device faults. Input diagnostic faults can self-clear as the underlying condition
recovers; output faults latch and require Reset. The distinction is deliberate:
recovering a sensor need not imply restarting equipment.

Device blocks have a single public signal input/output boundary. Only the
application allocates and maps process-image variables. Tests and simulations use
the same boundary and supply quality explicitly.
A process-image output is a commanded value, not physical feedback.

## Adding a device

Define configuration, status with the common header, fault/state types and its IO
boundary. Specify startup, reset, abort, invalid quality, stale inputs, configuration
changes and persistence before implementing commands. Ordinary commands validate
source/fault state; operational stop/fallback commands have explicit precedence.
Keep internal methods out of RPC. Operator wrappers submit only to the mailbox.
Call `_ProcessOperatorCommands()` once at the start of the owning cyclic body;
alarm subclasses inherit consumption through `_Evaluate`. Extend the protected
`_DispatchOperatorCommand` method with fixed OPERATOR identity and delegate unknown
commands to SUPER. Dispatch must be bounded and nonblocking: its mailbox lock is
held until the command returns. Do not recursively consume or expose these internal
methods as RPC. New shutdown/recovery methods must cancel pending normal commands
through `_operatorMailbox.CancelNormal()` only after validation succeeds.
Add public-behavior tests, multi-scan tests and a hardware acceptance procedure.
Do not add interfaces unless a real consumer needs polymorphic behavior.
