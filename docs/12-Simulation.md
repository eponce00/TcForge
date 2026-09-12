# Simulation and functional testing

Python models a discrete assembly cell; TwinCAT runs the actual library and
assembly-station controller. The plant contains locating-clamp, press and ejector
cylinders, part/discharge photoeyes, and pressure/height analog channels. Plant
physics, transport and test orchestration are separate. The process-plant
prototype informed that separation; no project-specific or SPT implementation
was copied.

## IO boundary

Hardware allocations (`AT %I*` / `AT %Q*`) belong to the application. Device blocks
receive public signals and quality. The standalone `TcForge.Simulation.sln` uses
the same canonical reference-machine source, with no hardware mappings and no
TcUnit dependency. Its PLC port is 854 and default task period is 10 ms.

The simulator feeds the application signal boundary through `FB_SimulationBridge`.
It does not write PLC-owned coil outputs or device internals. ADS writes to actively
mapped inputs could be overwritten by the IO driver. An AT allocation does not
turn Python into an EtherCAT/Profinet device or reproduce bus diagnostics/timing.

## Live exchange contract

The fixed RPC endpoint is `MAIN.simulation`, identity
`TcForge.DiscreteAssembly/2`. A small C# ADS transport validates that identity
and exposes only the simulation protocol to Python. The bridge is test application
code, outside the reusable library and production example.

- `Claim` binds one nonzero client session to the current PLC boot identity.
  Competing clients and wrong boot identities reject. Repeating Claim does not
  refresh the watchdog or reset sequence tracking.
- `Exchange` admits a complete sensor/quality/shutdown/command frame under a
  nonblocking mutex. One pending frame is allowed. The owning PLC task consumes
  the whole frame, executes the reference machine and publishes gated outputs.
- Input sequence numbers must be consecutive; output acknowledgements must advance
  and refer to published cycles. Duplicate, invalid, wrong-session and wrong-boot
  frames reject. BUSY means the frame was not admitted. An uncertain transport
  outcome fails the Python session; it is never automatically replayed.
- A 250 ms PLC watchdog invalidates quality, expires the session and drops both
  simulation coils. Timer and exchange state use the same bounded lock; a busy
  scan returns without executing the machine. Extended RPC contention and task
  load must be measured during timing qualification. Release invalidates the session; the owning scan applies the
  normal quality/output policy. A conflicting cyclic caller latches an ownership
  fault and cannot execute the machine in its task.
- Reconnect needs an explicit new Claim and normal machine recovery. It does not
  restart motion. Restart detection uses a volatile boot timestamp; a normal runtime
  restart has been verified to clear sessions and reject the previous boot identity.
  In-motion restart and online-change acceptance remain open qualification items.

`Snapshot` is a mutex-protected CSV record: result, boot, cycle, applied frame,
six cylinder coil commands, machine state, faulted, inhibited, command response,
session, owning task, healthy and current recipe step. A BUSY snapshot contains
only `22`.

## Running the assembly scenarios

Install Python dependencies and build the transport as described in the
[package guide](https://github.com/eponce00/TcForge/blob/main/python/README.md). Build/install the current library first:

```powershell
powershell.exe -NoProfile -File scripts/build_twincat.ps1
powershell.exe -NoProfile -File scripts/build_simulation_rpc.ps1
```

On a dedicated test runtime, activation replaces its active configuration and
restarts TwinCAT. Supply the intended target and platform explicitly. The local
Usermode runtime uses `TwinCAT OS (x64)`; a Windows kernel runtime uses
`TwinCAT RT (x64)`. A successful build for one platform does not qualify activation
on the other:

```powershell
powershell.exe -NoProfile -File scripts/activate_simulation.ps1 -Target 192.168.1.108.1.1 -Platform "TwinCAT OS (x64)"
artifacts/sim-venv/Scripts/python.exe -m tcforge_sim.functional --target 192.168.1.108.1.1 --port 854 --transport artifacts/simulation-rpc/SimulationRpc.exe --output artifacts/assembly-e2e
```

For bounded in-motion system restart acceptance, first deploy the standalone
simulation, then run the verifier against that dedicated runtime:

```powershell
artifacts/sim-venv/Scripts/python.exe scripts/verify_simulation_restart.py --target 192.168.1.108.1.1 --port 854 --solution TwinCAT/TcForge.Simulation.sln --automation ../twincat-mcp/TcAutomation/bin/Release-v2/TcAutomation.exe --transport artifacts/simulation-rpc/SimulationRpc.exe --output artifacts/in-motion-restart
```

This operation restarts the selected TwinCAT system. It preloads XAE under the
shared `Local\TcForge.Xae` mutex before starting motion, jams the model mid-travel,
and keeps exchanging frames until the restart interrupts the endpoint. A motion
timeout observed before interruption fails acceptance. The verifier records the
last advancing snapshot, changed boot identity, rejected stale requests, inhibited
reconnection and explicit recovered cycle in JSON/JSONL/JUnit files. Script
availability is not passing runtime evidence; power interruption, persistent data
and online changes require their own acceptance runs.

The standalone application also includes `MAIN.lifecycle`, an unmapped qualification
fixture. It uses application-owned persistent configuration and ordinary device
instances to distinguish saved commands/history from volatile execution state.
It is not part of the library or the production reference machine.

Add `--lifecycle-state seed`, `safe`, or `reset` to the system-restart verifier to
check real retained data: valid saved intent, intent invalidated by ForceSafe, or
intent invalidated by Reset. The verifier seeds the fixture before motion, checks
the restored marker, output inhibition, alarm latch and fault history, and clears
fixture outputs afterward. Successful orderly shutdown does not prove sudden
power-loss durability.

`scripts/verify_plc_stop_start.py` uses direct ADS control with an explicit target,
port, transport and output directory. Its default operation tests 30 ms and 500 ms
PLC stops during advance. `--operation ads-reset --lifecycle-state seed` exercises
ADS RESET/RUN with retained-data assertions; `safe` and `reset` select the other
saved-intent cases. It verifies the actual runtime transition, session invalidation,
stale-request rejection and an explicitly recovered cycle. It does not infer that
the distinct XAE ResetColdCmd or ResetOriginCmd operations worked.

On a missed owning-task cycle or changed PLC online-change counter, the bridge
rotates its epoch and discards pending frames. The reference composition cancels
motion and requires explicit recovery. This covers detected execution gaps;
it cannot control hardware while PLC code is stopped, and a stop spanning no
system-task tick cannot be detected by this counter check.

The functional suite records JSONL events and JUnit assertions. Each exchange
records its attempted input frame before transport, then separate admission and
application events. Session failures retain their cause; an uncertain reply never
appears as an applied frame. Sensor values, quality and independent shutdown
confirmation are included for diagnosis. Failure to write the initial trace stops
the session before submitting that frame. It covers exclusive
sessions/rejected frames, the complete locate/press/inspect/eject cycle,
controlled Stop, Abort, press-jam timeout, contradictory clamp sensors, lost
quality, blocked discharge, simulator loss, explicit reconnect and recovery,
and independent shutdown confirmation with timeout and rejected Reset until
trusted feedback is present.
The same bridge can also run alongside TcUnit on test PLC port 853.

## Time and physical assumptions

Offline models use explicit simulated time. Live tests use elapsed wall-clock time
from Python's high-resolution monotonic clock; the PLC keeps its normal task time.
Python and network scheduling are not real-time guarantees. A gap above 200 ms
fails the live client before continuing the plant model; PLC protection is independent.

Each double-solenoid cylinder model holds position with both coils off. Spring-return
valves, pressure loss, inertia and real de-energized behavior need their own models.
Shutdown confirmation is an independent simulated input, never inferred from coils.

Bench routing/licensing, in-motion restart, online change, 1 ms task-load acceptance, physical
IO/bus loss and OPC UA security remain separate qualification work. A no-IO bench
can qualify controller behavior but cannot qualify physical machine response.
