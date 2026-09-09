# Using TcForge in a PLC project

The development library is not production-qualified. Follow the qualification
tracker before adopting a release. Current toolchain and exact direct dependency
versions are recorded in `toolchain.json` at the repository root.

## Build and install the development library

1. Use the configured Windows XAE environment and the built sibling `twincat-mcp`
   helper described in [Qualification](10-Qualification.md).
2. From the repo root run
   `powershell.exe -NoProfile -File scripts/build_twincat.ps1`.
   This exports and installs `artifacts/TcForge.library`, then compiles both
   consumers. Export alone is not proof of compilation.
3. In another PLC project's References node, choose Add Library and select the
   installed TcForge version. The current development identity is
   `TcForge, 2.0.0.0 (Home)` with namespace `TcForge`, as used by the example.
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
