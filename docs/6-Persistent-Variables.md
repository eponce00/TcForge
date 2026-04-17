# 6 Persistent Variables

This document covers how to use TwinCAT persistent variables correctly — which keyword to use, what to persist, how to configure the IPC hardware, and the risks to be aware of.

> **Navigation:** [← README](../README.md) · [Programming Standards](1-Programming-Standards.md) · [HMI Integration](4-HMI-Integration.md) · [Sequencing](5-Sequencing.md) · [Architecture →](7-Architecture.md) · [I/O Binding →](8-IO-Binding.md)

---

## 6.1 Keyword Definitions

TwinCAT provides two keywords for remanent (surviving) variables:

| Keyword | Written to | Survives |
|---------|-----------|---------|
| *(none)* | Standard RAM | Online Change only |
| `RETAIN` | NovRam (battery-backed) | Power failure, Reset cold, Download |
| `PERSISTENT` | File on disk | Reset cold, Download |
| `PERSISTENT RETAIN` | NovRam + disk | Everything above |

### 6.1.1 Behavior Matrix

| Event | Normal | RETAIN | PERSISTENT | PERSISTENT RETAIN |
|-------|--------|--------|------------|-------------------|
| Online Change | Kept | Kept | Kept | Kept |
| Download | **Reset** | Kept | Kept | Kept |
| Reset cold | **Reset** | Kept | Kept | Kept |
| Reset origin | **Reset** | **Reset** | **Reset** | **Reset** |
| Power failure (uncontrolled) | **Reset** | Kept | **Reset**\* | Kept |

\* With the [1-second UPS](#63-ipc-configuration-1-second-ups) enabled, `PERSISTENT` also survives uncontrolled power loss. This is the recommended configuration.

> **Important:** The `AT` declaration for I/O mapping (`AT %I*`, `AT %Q*`) cannot be combined with `VAR RETAIN` or `VAR PERSISTENT`. I/O variables are refreshed from the image every cycle — they don't need persistence.

---

## 6.2 Use PERSISTENT — Not RETAIN

### Why not RETAIN?

`RETAIN` requires:
1. A **NOV-DP-RAM device** added to the TwinCAT IO configuration
2. One or more **Retain Handlers** configured under that device
3. The retain handler writes to NovRam **every PLC cycle** — adding per-cycle overhead with no benefit over PERSISTENT when a UPS is present

Additionally, `RETAIN` alone does not survive a download. To cover that scenario you'd need `PERSISTENT RETAIN`, which requires both the NOV-DP-RAM hardware and a UPS — maximum complexity for no gain over `PERSISTENT` + UPS alone.

### PERSISTENT + 1-Second UPS is sufficient

Beckhoff CX-series IPCs include a **1-second UPS** (UltraCap capacitor) that keeps the processor alive during power loss long enough for TwinCAT to write persistent data to disk. With this enabled, `PERSISTENT` covers all failure scenarios:

| Scenario | Without 1-sec UPS | With 1-sec UPS |
|----------|------------------|----------------|
| Download / Reset cold | ✅ Retained | ✅ Retained |
| Controlled shutdown | ✅ Retained | ✅ Retained |
| Uncontrolled power loss | ❌ Lost | ✅ Retained |

**Decision:** Use `VAR PERSISTENT` only. No NOV-DP-RAM, no per-cycle write cost.

---

## 6.3 What to Persist

### The minimum principle

Not everything in an FB should be persistent. The goal is to persist the smallest amount of state that allows the machine to restart in a predictable, safe condition — without losing the last intentional commanded setpoints.

**Persist:**
- Last commanded setpoints — the values an operator or program explicitly configured (output targets, position setpoints, PID setpoints, mode selections)
- Any operator preference that would be frustrating or unsafe to lose on a power cycle

**Do not persist:**
- `cfg` structures — these are set by application code at startup and should be declared with correct defaults
- `sts` / status structures — derived every scan from state and inputs
- Working / intermediate variables — recalculated every scan
- Fault latches — safe defaults (`FALSE`) are correct on restart
- Timers, edge detection, debounce state — rebuilt from physical inputs within a scan cycle
- Interface references or pointers — addresses change on download; Beckhoff explicitly warns against persisting these

### Example: what to persist in a device FB

```iecst
// What the operator or program last commanded — persist this
VAR PERSISTENT
    _lastSetpoint : REAL;          // last commanded output value
    _lastTargetState : E_MyState;  // last commanded state
END_VAR

// Everything else — safe defaults on restart
VAR
    cfg : ST_MyDevice_Cfg;
    sts : ST_MyDevice_Sts;
    _timer : TON;
    _faulted : BOOL;
END_VAR
```

### Validate persisted values on first scan

After a power cycle, persisted values may be stale (changed process conditions, code changes that added fields, etc.). Always validate before acting on them:

```iecst
VAR
    _firstScan : BOOL := TRUE;
END_VAR
---
IF _firstScan THEN
    _firstScan := FALSE;
    // Clamp or validate persisted setpoints
    _lastSetpoint := MAX(cfg.fMin, MIN(cfg.fMax, _lastSetpoint));
END_IF;
```

---

## 6.4 How to Declare Persistent Variables

The `PERSISTENT` keyword goes on the **`VAR` block**, not on individual variables. Add a dedicated `VAR PERSISTENT` block and put only the minimum state into it:

```iecst
FUNCTION_BLOCK FB_MyDevice

VAR PERSISTENT
    // Last commanded setpoints — restored correctly after power cycle
    _lastSetpoint : REAL;
END_VAR

VAR
    cfg : ST_MyDevice_Cfg;
    sts : ST_MyDevice_Sts;
    _timer : TON;
    _faulted : BOOL;
    _firstScan : BOOL := TRUE;
END_VAR
```

Keep the persistent block small — the 1-second UPS can reliably save up to **1 MB** over the device's lifespan. Even a large system with hundreds of FB instances should stay well under this when only setpoints are persisted.

---

## 6.5 IPC Configuration: 1-Second UPS

The 1-second UPS must be configured for `PERSISTENT` to survive uncontrolled power loss.

### Step 1: Enable in BIOS

Activate the 1-second UPS in the IPC BIOS. On CX51x0 hardware this is a dedicated BIOS option. See [Beckhoff — BIOS settings (CX51x0)](https://infosys.beckhoff.com/content/1033/cx51x0_hw/9127354251.html).

### Step 2: Configure the Windows write filter

The Windows write filter must allow writes to the path where TwinCAT stores persistent data (`\TwinCAT\3.1\Boot\Plc\Port_85x.bootdata`). Without this, the data cannot reach disk. See [Beckhoff — Windows write filter](https://infosys.beckhoff.com/content/1033/cx51x0_hw/3489028491.html).

### Step 3: Call the UPS function block cyclically

Call `FB_S_UPS_CX51x0` at the **top of the fastest task**, before all application logic. On power-fail detection, skip the rest of the application immediately — this maximizes the time available to write persistent data:

```iecst
// MAIN — fastest task
fbUps();

IF NOT fbUps.bPowerFailDetect THEN
    // All application code goes inside this guard
    fbMyDevice();
    fbStateMachine(...);
    // ...
END_IF;
```

> **Important:** Always call the UPS block first. Application logic running during power-fail detection consumes the capacitor hold time that is needed to flush persistent data to disk.

### Step 4: Select UPS mode

Configure the function block to write persistent data then execute a controlled shutdown on power failure. See [Beckhoff — UPS data types and modes](https://infosys.beckhoff.com/content/1033/cx51x0_hw/2537056523.html).

### Step 5: Validate persistent data on startup

TwinCAT provides a validity status output on `FB_S_UPS_CX51x0`. Check it on startup and fall back to safe defaults if the persistent file was not written cleanly. See [Beckhoff — Checking validity of persistent variables](https://infosys.beckhoff.com/content/1033/cx51x0_hw/2516793867.html).

### How the persistent file is managed

| Event | What happens |
|-------|-------------|
| Controlled shutdown or UPS power-fail trigger | `Port_85x.bootdata` written to disk |
| Next startup | File loaded, backed up as `Port_85x.bootdata-old`, then deleted |
| Startup with no `.bootdata` file | Persistent variables use declared default values |

---

## 6.6 Risks and Mitigations

### Stale setpoint after a download or code change

Persistent variables survive a download with their previous values. If a `VAR PERSISTENT` block gains a new field between downloads, the new field initializes at its declared default — usually correct, but should be validated.

**Mitigation:** Validate all persisted values on first scan. Apply bounds checks for numeric setpoints.

### Persisted setpoint may not match current process state

After a dual power loss the FB resumes at the persisted setpoint. If process conditions changed during the outage (e.g., a vessel emptied), the old setpoint may no longer be appropriate.

**Mitigation:** The application layer — not the FB — is responsible for deciding whether to act on a persisted setpoint. The FB exposes it; the sequence validates whether conditions allow using it.

### UPS capacitor aging

The UltraCap degrades over time. Beckhoff guarantees reliable 1 MB writes over the full device lifespan, but only if the capacitor is not overstressed by persisting too much data.

**Mitigation:** Keep persistent data minimal. If only setpoints are persisted, a typical system uses single-digit kilobytes total.

### Never persist pointers or interface references

Beckhoff explicitly warns: variable addresses change when the PLC project is downloaded again. Persisting a `POINTER TO` or an interface reference results in a dangling pointer on restart.

**Mitigation:** Interface references and pointers always live in the regular `VAR` block and are re-initialized in `FB_Init`.
