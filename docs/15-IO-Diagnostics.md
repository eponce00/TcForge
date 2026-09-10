# IO diagnostics and freshness

`FB_IOQualityMonitor` converts source health into `E_IO_Quality` without commanding
or resetting devices. Use one instance per coherent data source, called once per
owning PLC task cycle. Keep application hardware mappings outside the library.

## Producer contract

Supply `enabled`, `communicationGood`, `deviceGood`, `sampleValid`, a monotonically
increasing `sampleSequence`, and a positive `timeout`. Defaults are unqualified.
The producer advances its sequence only after publishing a complete valid update.
It must not increment merely because the consuming PLC task ran.

The first observation establishes a baseline. A subsequent valid new sequence
qualifies GOOD. Duplicate sequences cannot refresh the deadline. A stable sensor
value is perfectly valid when new producer updates continue to arrive.
Communication/device faults and invalid samples make quality BAD immediately.
Disable makes it UNKNOWN. A zero timeout is invalid; changing timeout reacquires
fresh data. Sequence rollback, including wrap, invalidates the old baseline.

A missed deadline is detected before admitting a newly arrived frame. Repeated
stale data remains BAD. After fault recovery, another valid producer update is
required. Quality recovery never resets downstream faults or rearms outputs.
The output still requires its own fresh accepted command.

The TON is restarted in the same scan as the accepted update. Expiry is observed
on the first owner scan at or after the deadline; this is task-quantized detection,
not a hardware safety watchdog or a promise about scheduling under overload.

## EtherCAT mapping

`F_EtherCATSlaveDataValid` combines explicit `diagnosticsAvailable`, slave `WcState`
and `InfoData.State`. It requires OP, rejects working-counter and documented
identity/missing/link/error flags, and allows communication-port status bits.
An unmapped diagnostic source must leave `diagnosticsAvailable` FALSE.

`WcState` may describe a shared command/SyncUnit failure, so it does not identify
which slave caused the problem. `InfoData.ChangeCnt` counts diagnostic-image
changes and is **not a heartbeat**. These mappings follow Beckhoff's
[diagnostic definitions](https://infosys.beckhoff.com/content/1033/tcsystemmanager/1089009035.html).

Example application composition (the producer and linked symbols are supplied
by the application, not by TcForge):

```iecst
slaveGood := TcForge.F_EtherCATSlaveDataValid(
    diagnosticsAvailable := diagnosticsMapped,
    wcState := slaveWcState,
    slaveState := slaveInfoState);
health(enabled := ioEnabled,
    communicationGood := busOperational,
    deviceGood := slaveGood,
    sampleValid := producerFrameValid,
    sampleSequence := producerSequence,
    timeout := T#100MS);
inputDevice(inSignal := terminalBit, inpQuality := health.quality);
```

For terminal IO, use a verified cyclic bus-update indication/counter appropriate
to the mapped driver/task. If no trustworthy freshness source is available, do
not invent one from a sensor value or a task counter. Native bus watchdog and
working-counter diagnostics still need target-specific mapping and acceptance.
The example project leaves qualities UNKNOWN until the application supplies
its diagnostics. This does not claim a commissioned EtherCAT or Profinet adapter.

## Provenance and acceptance

These are original TcForge implementations of documented diagnostic semantics.
No SPT implementation was copied. SPT's periodic device discovery, master/SyncUnit
monitoring and event reporting informed separation of supervisory diagnostics
from the per-cycle quality gate; see the [SPT review](13-SPT-Review.md).

The PLC regression suite covers startup, producer reset, duplicate expiry, the
freshness deadline boundary, configuration changes, device/communication loss,
recovery without output rearming, and the documented EtherCAT error/port bits.
Actual bus mapping, bus interruption and loaded-task timing remain hardware
qualification work.
