# Using TcForge in a PLC project

The development library is not production-qualified. Follow the qualification
tracker before adopting a release. Current toolchain and exact direct dependency
versions are recorded in `toolchain.json` at the repository root.

## Work on TcForge itself

Open `TwinCAT/TcForge.sln`. The core library, Example, Testing and Simulation are in the same TwinCAT project. Consumers reference
`[TcForge]` from source, so edits require a build but no library installation or
version change. See the [development and qualification workflows](10-Qualification.md).

## Build and install into another project

1. Use the configured Windows XAE environment and the built sibling `twincat-mcp`
   helper described in [Qualification](10-Qualification.md).
2. From the repo root run
   `powershell.exe -NoProfile -File scripts/build_twincat.ps1`.
   This exports and installs `artifacts/TcForge.library`, then compiles all three
   consumers. Export alone is not proof of compilation.
3. In another PLC project's References node, choose Add Library and select the
   installed TcForge version. The current development identity is
   `TcForge, 2.0.0.0 (Home)` with namespace `TcForge`.
   Publisher/version cleanup belongs to D2 before a company release.
4. Pin that exact version and verify resolved dependencies. Replacing a development
   artifact under the same version requires reinstall/rebuild; release artifacts
   must have immutable version/hash identity.
5. Instantiate blocks with the `TcForge` namespace. The application owns hardware
   mappings, signal quality, command ordering and one cyclic owner per instance.
   Start with the [reference machine](11-Reference-Machine.md) rather than mapping
   physical IO into the library internals.

To install a supplied `.library` manually, use the XAE Library Repository dialog's
Install operation, then add its exact reference to the consumer. Library
installation, adding a project reference and activating a runtime configuration
are distinct steps; the build script does not activate a runtime.

## Planned company distribution

D2 will package reviewed releases in a TwinCAT library repository folder with
versioned artifacts and checksums. XAE can add such a folder as a repository
location, as demonstrated by [SPT's setup guide](https://beckhoff-usa-community.github.io/SPT-Libraries/Getting_Started/setup.html).
That repository is a planned release output, not a folder currently provided by
TcForge. A browsable Material for MkDocs site now builds from these Markdown files;
see [Maintaining this site](documentation-site.md) for preview and publishing instructions.

## Source organization and readability

Group files by machine area or purpose. Put a block, its configuration/status
UDTs and the code using them together when they describe the same area. Do not
create a separate project merely to separate definitions from instances.
Generic device contracts belong in TcForge; application-specific compositions
belong in TcForgeExample and can be shared through its project reference.

Use one statement per line and blank lines between declaration groups and scan
phases. Expand IF/ELSE bodies, and put long named argument lists on separate
lines. Align related declarations where useful. For a long cyclic body, use
named methods for meaningful phases, preserving a visible call order in the
body. Inline comments should explain intent, units, required call order and
non-obvious failure behavior; avoid comments that just repeat the assignment.
 Number recipe steps and give each a physical description. Keep device policy
 out of the recipe so a reader can follow the machine's actual operation.

## Analog engineering units

The default analog scale is a numeric 0..100 example, not an asserted physical
unit. Configure `cfg.unit` together with the real sensor or actuator scaling;
the default is `E_Unit.UNSPECIFIED`. Status echoes this value for the HMI. The
enum is display metadata only: it does not convert values or verify that the
scale matches the unit. The application/HMI maps an enum such as `MILLIMETER`
to its display symbol. Add a new unit to `E_Unit` when a machine device needs it,
using a new explicit numeric code and leaving published codes unchanged.
