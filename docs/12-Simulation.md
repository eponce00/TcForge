# Simulation and functional testing

Python models the plant; TwinCAT runs the actual library and reference machine.
The plant reads command outputs and publishes physical feedback and quality.
Tests issue application commands and assert machine behavior, not just model
behavior. This complements TcUnit and hardware commissioning.

## IO boundary

Keep `AT %I*` and `AT %Q*` allocations in the application (`GVL_HW`), as they are
today. Device blocks continue receiving the same public signal/quality inputs.
The simulation configuration must have no active fieldbus mapping to simulated
inputs. ADS writes to an actively mapped input can be overwritten by the IO driver.
Never write PLC-owned command outputs or device internals to imitate a plant.

An AT declaration allocates process-image storage; it does not make a Python
process an EtherCAT/Profinet device or reproduce bus timing and diagnostics.
Application functional behavior can be exercised through this boundary; bus and
physical response acceptance remain separate.

## Required live exchange contract (S2, not implemented yet)

Use a dedicated simulation composition that calls the canonical reference machine.
Its PLC task copies a committed input frame into the same application signal
boundary at the start of a scan and publishes an output snapshot after final
output gating. Hardware composition maps terminal data into that boundary.

- A versioned simulation identity and session ID distinguish a test application
  from other PLC programs. Python verifies the identity and expected symbol types
  before claiming a session; the PLC permits only one simulation writer.
- Stage inputs and commit a sequence number through a serialized PLC method or
  an equivalent proven exchange. Multiple ADS symbol writes and sum commands are
  not assumed to be an atomic scan snapshot. Specify and test buffer ownership.
- Correlate feedback with an output-frame sequence. Reject stale, duplicate,
  wrong-session and partial frames. Wrap/restart must require a new handshake.
- A PLC-side watchdog invalidates quality on lost or stale simulation data and
  applies normal output policy. Python cleanup cannot protect against its own
  crash, network loss or power failure. Resuming transport must not restart motion.
- Explicitly distinguish deterministic step-driven test time from wall-clock
  functional runs. Python/network scheduling is not a real-time guarantee.
- Record target/application identity, versions, seed if randomness is introduced,
  frame times/sequences, commands, model faults, PLC state and assertions in test
  evidence. Failures must retain traces and produce a nonzero test result.

Prefer the isolated local runtime for initial protocol development. Deploy the
same simulation application to the dedicated network bench after target inventory,
backup and secure routing are working. Do not put passwords in project files.

## Initial coverage and next scenarios

The Python package currently verifies deterministic cylinder travel/reversal,
conflicting coils, jammed mechanics, independent sensor faults, analog dynamics,
invalid numeric inputs, stale frames and uncertain writes. These are model and
transport-contract tests, not PLC end-to-end evidence.

S3 will exercise the actual reference machine: Home/Run cycle, controlled Stop,
Abort, sensor contradiction, jam/timeout, lost feedback, independent shutdown
confirmation, transport interruption, reconnect and restart. Extend plant models
only as those scenarios require them; avoid recreating command arbitration or
state-machine implementation in Python.

Inspiration: the local Li-Direct prototype separates plant physics from ADS device
adapters and disables conflicting fieldbus mappings for simulation. The new
package is independent of its project-specific equipment and toolkit. ADS API
reference: [pyads connections](https://pyads.readthedocs.io/en/latest/documentation/connection.html).
