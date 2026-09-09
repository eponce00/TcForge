# 1 Programming standards

Read the [architecture](2-Architecture.md) and [qualification procedure](10-Qualification.md)
before changing a control contract.

## Names and modules

Use FB_ for function blocks, F_ for functions, ST_ for structures, E_ for enums and
I_ for interfaces. Group a device with its configuration, status, state/fault types
and tests. Configuration uses cfg, status uses sts (the machine uses Status).
Status embeds the common device header. Keep module responsibilities focused.

Public commands return E_RpcMethodResponse. Prefer named arguments at call sites.
Commands track requester identity; command rejection is not a device fault.
Only fixed-identity Operator wrappers carry TcRpcEnable. Internal state and input
signals are hidden from OPC UA; published status is read-only.

## Execution and recovery

One task owns each FB. Run each cyclic body once per application scan. Sample
inputs and map conditions first, then issue commands, update devices and apply
outputs. The state machine makes one state transition per scan. Abort outranks
Stop; output ForceSafe outranks ordinary output commands in the same scan.

Use IsFaulted() as the authoritative internal fault gate. Diagnostic snapshots
refresh at the cyclic publication boundary. Reset follows the concrete recovery
contract, not an unconditional permission to restart. Stop/Abort/ForceSafe have
explicit state/priority rules and bypass the ordinary source/fault gate.

Detect faults before applying final outputs. Device methods record intent;
physical completion comes from feedback. Normal step work stops on faults, while
shutdown steps must remain executable. Positive travel timeouts and output pulse
durations are required. Validate configurable ranges on every cyclic evaluation
so a live edit cannot bypass validation.

## Conditions

A permissive is a non-latching operational condition. An interlock latches a
failure until fresh good input and Reset. Declare nRequired independently of
mapping calls; missing required conditions inhibit operation. nBypassable declares
which present conditions the application may bypass. Missing required conditions
cannot be bypassed. Never treat these standard PLC blocks as safety-rated logic.

Stopping/fallback must not depend on ordinary motion permission. Do not reorder
input mapping to trick a fault gate into accepting a command; use Stop, Abort or
ForceSafe and the device's explicit recovery contract.

## IO, persistence and diagnostics

Hardware AT allocations live only in the application. Library blocks receive
ordinary input values and return output values. Input quality must be supplied by
the adapter and included in required device conditions where appropriate.

Keep retained configuration/history separate from volatile operating state.
Restoration of saved output intent is explicit and disabled by default. Reset and
ForceSafe clear saved output intent. Validate persistent storage on the actual
runtime; declarations alone do not guarantee survival of power loss.

Raise faults with a stable code, short source and actionable reason. Repeated
current codes do not create repeated ring entries. History is bounded to eight
entries. Keep cyclic string work bounded and measure task load on representative
hardware before deployment.

## Source files and tests

TwinCAT XML must be UTF-8 without BOM. Methods are POU children; Folder elements
are siblings referenced by FolderPath. Preserve CDATA for declarations and ST.
Exit is a reserved keyword; use Exiting for the lifecycle signal.

Test public behavior instead of duplicating implementation. Stateful multi-scan
tests retain their FB/timer instances in suite scope. Cover invalid quality,
missing required mappings, conflicting commands, timeouts, reset/retry, startup
and shutdown. Use test probes only for diagnostic or persistent-image injection
that has no ordinary public API. XML checks are not a PLC compiler.
