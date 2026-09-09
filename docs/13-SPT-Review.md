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
