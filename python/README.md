# TcForge plant simulation

This package models physical counterparts to TcForge devices. The PLC remains
the controller. Pure plant models, IO transports and scenario orchestration are
separate so the same models can be used offline and later against TwinCAT.

Implemented: three-cylinder assembly-cell travel, jams and sensor overrides;
part-presence and discharge photoeyes; bounded pressure and height analog
responses; ordered read/model/write exchange; JSONL traces; a read-only ADS
target probe; and live PLC functional scenarios. No Redwood source or SPT code
is copied into this package. The Redwood prototype informed the separation of
physics and IO adapters.

## Run locally

From the repository root:

```powershell
python -m venv artifacts/sim-venv
artifacts/sim-venv/Scripts/python.exe -m pip install --upgrade pip
artifacts/sim-venv/Scripts/python.exe -m pip install -e "./python[ads]"
artifacts/sim-venv/Scripts/python.exe -m unittest discover -s python/tests -v
artifacts/sim-venv/Scripts/python.exe -m tcforge_sim --trace artifacts/cylinder-trace.jsonl
artifacts/sim-venv/Scripts/python.exe -m tcforge_sim.ads --target 192.168.1.108.1.1 --port 853
```

Offline execution uses explicit simulated time. It does not execute Structured
Text or prove PLC behavior. The cylinder assumes a double-solenoid plant that
holds position with both coils off. Configure a different model for spring-return
valves, pressure decay, inertia or a different de-energized response. Shutdown
confirmation must have its own plant model; it cannot be inferred from coil bits.

The offline runner rejects duplicate/restarted output frames and stops after an
uncertain write. The live runner uses a PLC-owned frame exchange, exclusive session,
boot identity and watchdog. It advances physics using wall-clock time and requires
explicit recovery after lost communication.

The C# transport validates the simulation identity and RPC signatures at startup,
then retains method handles for its connection lifetime. Each RPC uses one ADS
read/write round trip. A method failure terminates the transport; it does not
refresh a handle and replay an uncertain command. Identity/signature discovery
has a separate 30-second startup deadline before any IO session is claimed. This
does not relax the 200 ms live scheduling or 150 ms frame-confirmation budgets.

Use `scripts/benchmark_simulation_rpc.py --target <AMS-Net-ID> --port 854
--transport artifacts/simulation-rpc/SimulationRpc.exe --output artifacts/rpc-timing.json`
to measure read-only snapshot latency. This benchmark does not qualify cyclic IO.

## Live assembly testing

Build/install TcForge, build the narrow ADS RPC transport, and activate the isolated
simulation on a dedicated runtime using the commands in the
[simulation guide](../docs/12-Simulation.md). Activation replaces that target's
configuration. The standalone simulation PLC uses port 854; the TcUnit composition
also includes the bridge at port 853.

```powershell
artifacts/sim-venv/Scripts/python.exe -m tcforge_sim.functional --target 192.168.1.108.1.1 --port 854 --transport artifacts/simulation-rpc/SimulationRpc.exe --output artifacts/assembly-e2e
```

The suite runs the actual PLC locate, press, inspect and eject recipe plus
Stop/Abort, jam, sensor contradiction, bad quality, blocked discharge, shutdown
confirmation, watchdog and reconnect recovery scenarios. It writes
`assembly-trace.jsonl` and `assembly-junit.xml` and exits nonzero when a scenario
fails. PLC restart and physical IO acceptance remain tracked in
[PROGRESS.md](../PROGRESS.md).
