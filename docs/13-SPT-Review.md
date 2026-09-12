# SPT review and adoption decisions

Reviewed 2026-09-09. Upstream inspected at commit
`f598024bfe1cbbbca808f36958914b8497119191` in
[SPT-Libraries](https://github.com/Beckhoff-USA-Community/SPT-Libraries).
This is a reference review, not a source-code equivalence or qualification audit.

## What is in that repository

The library repository includes **SPT Base Types**, **SPT Components**, Utilities,
Diagnostic, EtherCat, Event Logger, Motion Control, Kinematics, NCI, Vision, XTS
and XPlanar. Base Types and Components are the relevant starting points for core
framework/device ideas; no separate dependency called Core Devices is required
to find those families. Distribution contains version directories with `.library`
files and repository metadata rather than an ordinary tree of `.TcPOU` sources.
Inspect any candidate implementation in XAE before adapting it.

Upstream advertises V4 for the newer PackML generation and links separate samples.
Do not interpret a lexically last version directory or the default branch as a
qualified dependency. The repository states MIT licensing; retain applicable
notices and record the exact upstream version for any future copied code. No
SPT implementation is copied or installed as a TcForge dependency in this work.

## Prioritized comparison

| Area | Finding and TcForge action |
|---|---|
| Lifecycle | SPT uses explicit initialization completion before cyclic logic. Audit TcForge configuration readiness, restart and online-change behavior under Q4/A5. Avoid adding another inheritance layer just to match SPT. |
| Components | Review cylinders, sensor wrappers and composition patterns when extending the device catalog. Current first priority is a simulated physical counterpart for existing devices, with end-to-end evidence. |
| Diagnostics | Evaluate bus/device diagnostic adapters that can drive TcForge quality and required conditions. This is a more immediate gap than new motion or vision features. Track A6. |
| Modules | SPT's PackML hierarchy is useful for future parent/child machine coordination. Keep our current sequence contract until a real composition requires PackML or multiple module lifecycles. Track A7. |
| Events | Evaluate an optional Event Logger sink for existing fault/event data; it should not become a mandatory control-path dependency. Track A8. |
| Utilities | Audit concrete functions, numeric bounds and dependency cost individually before adopting them. Existing timing/scaling helpers already have contracts that must be preserved. |

References: [Base Types](https://beckhoff-usa-community.github.io/SPT-Libraries/SPT_Base_Types/index.html),
[Components](https://beckhoff-usa-community.github.io/SPT-Libraries/SPT_Components/index.html),
[Design Guide](https://beckhoff-usa-community.github.io/SPT-Libraries/Getting_Started/DesignGuide.html),
[Diagnostics](https://beckhoff-usa-community.github.io/SPT-Libraries/SPT_Diagnostic/index.html).

## Documentation and consumption

SPT documents adding the cloned `Library Repository` directory to XAE's library
repository locations. Its website identifies Material for MkDocs; this public
repository contains generated HTML, so a complete Markdown authoring/build
pipeline cannot be inferred from this tree alone.

For TcForge, use one Markdown documentation source and build a browsable site from
it. Produce a versioned library repository layout from reviewed release artifacts,
with hashes, dependency versions and installation instructions. Avoid committing
unqualified development binaries or using floating latest references. First
document today's source-build/install path; publish a site and distributable
repository once the build/release evidence is reproducible (D1/D2 and Q2).

References: [SPT setup](https://beckhoff-usa-community.github.io/SPT-Libraries/Getting_Started/setup.html)
and [pinning libraries](https://beckhoff-usa-community.github.io/SPT-Libraries/V4%20Release%20Notes/PinningLibraries.html).

## Implemented diagnostic foundation

The follow-up review compared SPT runtime-device, master and SyncUnit diagnostics.
Its periodic discovery/event reporting belongs outside the cyclic quality gate;
see [SPT diagnostic blocks](https://beckhoff-usa-community.github.io/SPT-Libraries/SPT_Diagnostic/functionblocks.html).
TcForge now provides an original `FB_IOQualityMonitor` and a small EtherCAT slave
status mapping, with no SPT dependency or copied implementation. Tests cover
freshness, communication/device loss and recovery that does not rearm outputs.
See [IO diagnostics](15-IO-Diagnostics.md). Source-level adaptation of SPT components
remains a separate candidate-by-candidate decision.

## Event Logger candidate decision (2026-09-12)

**A8.1 complete: select an original optional adapter; do not import SPT Event
Logger or Utilities wholesale.** A8.2 implementation and A8.3 runtime evidence
remain open. No Event Logger dependency or adapter has been added yet.

The audit used the same upstream commit recorded above. Inspected artifacts:

| Artifact | SHA-256 |
|---|---|
| SPT Event Logger 3.9.0 | `5c576065fbae5258bff06f3e9df3b96013dc70bef4ffec177df533f16564f4e8` |
| SPT Utilities 3.9.0 | `6690d8769c9aa86296bb44c32773a4dea839a4c9372f66a7359572f368d68e0b` |

These are candidate versions, not qualified dependencies. Read-only inspection
of their ZIP archive string tables exposed ST declarations and implementation
lines. This supports the observations below, but is not a reconstructed object
model, XAE compilation, or runtime test of upstream. No upstream code was copied.
The repository's MIT notice is Copyright (c) 2023 Beckhoff Automation LLC; retain
it if later work copies substantial code.

### Adoption findings

| Candidate | Decision and reason |
|---|---|
| Event-class bulk creation | Do not copy. The inspected initializer derives event addresses from a pointer and array index. Its index-minus-one calculation needs a specific array layout; use explicit typed event definitions instead. |
| Raise helpers with error flags | Do not copy. Reporting also changes error flags/IDs. TcForge already owns fault state and requester validation; the logger must only observe it. |
| String argument helpers | Preserve the idea of contextual messages, not the implementation. Keep fixed argument positions, including empty values, so source/reason fields cannot shift. |
| Raise/clear operations | Check each HRESULT. Do not advance adapter state after failure or retry indefinitely within one scan. |
| Numeric comparisons/scaling | Keep existing TcForge contracts. Direct subtraction and scaling arithmetic require finite-value and range analysis before reuse. No demonstrated missing capability justifies replacement. |
| Decimal rounding | Reject the inspected candidate. Its expression scales by decimal-place count times ten, rather than a power of ten; zero places also produces a zero denominator, and conversion passes through DINT. |
| Simple rate limiter | Do not adopt unchanged. Inspected lines cache cycle time and clamp against output bounds; target overshoot, task changes and invalid rates need explicit contracts/tests. |

See the pinned [upstream artifacts](https://github.com/Beckhoff-USA-Community/SPT-Libraries/tree/f598024bfe1cbbbca808f36958914b8497119191/Library%20Repository/Beckhoff%20Automation%20LLC),
[SPT helper API](https://beckhoff-usa-community.github.io/SPT-Libraries/SPT_Event_Logger/functions.html)
and Beckhoff's [FB_TcAlarm API](https://infosys.beckhoff.com/content/1033/tcplclib_tc3_eventlogger/5001926923.html).

### Adapter contract to implement

1. Put vendor integration in a separate optional library project. Core TcForge
   builds without Tc3_EventLogger. The example can opt in through a source-project
   reference, preserving the single-solution development workflow.
2. Begin with device faults, using explicit device identity, fault code and event
   definition. Take a status snapshot after the device's owning cyclic call.
   Do not call Reset, Ack, commands or output methods from the adapter.
3. Mirror current fault state, not a lossless event journal. Unchanged faults do
   not raise repeatedly; clear and code replacement have explicit transitions.
   A clear/re-raise entirely between observations cannot be recovered from a
   current-state snapshot. A durable transition stream is separate future work.
4. Create alarms without mandatory Event Logger confirmation. Acknowledging the
   external display must not acknowledge or reset the device. Alarm-block
   integration is a separate mapping: `ST_Alarm_Sts.active` includes latch policy,
   and invalid input can hold an active alarm; invalidity must not clear it.
5. Check creation, argument, raise and clear results; expose the failed operation
   and HRESULT. Limit work per cyclic call and pace retries. Reconcile current
   state after recovery, and never claim historical delivery while unavailable.
6. Keep event IDs and source identities stable across restart. Validate duplicate
   registrations. Do not cast TcForge LTIME values into vendor timestamps without
   proving matching units and epoch; use the vendor timestamp convention initially.
7. Test the transition policy with a controllable failing sink, then verify the
   real adapter on the bench: first fault, unchanged fault, code replacement,
   clear, retry/recovery and startup with an existing fault. Confirm device
   outputs and reset permissions are unchanged when logging fails. Measure task
   timing before considering a separate logging task; cross-task status sharing
   would require a coherent handoff, not direct concurrent FB access.
