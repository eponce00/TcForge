# TcForge plant simulation

This package models physical counterparts to TcForge devices. The PLC remains
the controller. Pure plant models, IO transports and scenario orchestration are
separate so the same models can be used offline and later against TwinCAT.

Implemented: two-position cylinder travel, jam and sensor overrides; bounded
first-order analog response; ordered read/model/write runner; JSONL traces; a
read-only ADS target probe; live PLC exchange and assembly functional scenarios. No Redwood source or SPT code is copied into this
package. The Redwood prototype informed the separation of physics and IO adapters.

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

## Live assembly testing

Build/install TcForge, build the narrow ADS RPC transport, and activate the isolated
simulation on a dedicated runtime using the commands in the
[simulation guide](../docs/12-Simulation.md). Activation replaces that target's
configuration. The standalone simulation PLC uses port 854; the TcUnit composition
also includes the bridge at port 853.

```powershell
artifacts/sim-venv/Scripts/python.exe -m tcforge_sim.functional --target 192.168.1.108.1.1 --port 854 --transport artifacts/simulation-rpc/SimulationRpc.exe --output artifacts/assembly-e2e
```

The suite runs actual PLC Home/cycle/Stop/Abort and fault/recovery scenarios against
simulated clamp mechanics. It writes `assembly-trace.jsonl` and `assembly-junit.xml`
and exits nonzero when a scenario fails. PLC restart and physical IO acceptance
remain tracked in [PROGRESS.md](../PROGRESS.md).
