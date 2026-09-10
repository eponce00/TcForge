# Configuration and device lifecycle

The application owns each block and its configuration in one cyclic task. Write
configuration coherently before calling the block or a direct command. Remote
operator methods submit to the mailbox; they do not write configuration or run
the device body. Cross-task writes to public configuration are not supported.

## Operating configuration

Digital outputs, analog outputs and two-position actuators snapshot their first
configuration without discarding an explicitly issued first command. Subsequent
behavioral configuration changes discard active and saved operating intent,
reset relevant timers, and cancel queued commands that could reuse old intent.
Existing faults remain latched.

Synchronization occurs before cyclic mailbox dispatch and after requester
validation in direct commands. Thus a fresh direct command explicitly issued
for the new configuration can be accepted; an old command cannot silently acquire
a new meaning. Analog engineering-unit labels are metadata and do not invalidate
intent. Changes to numeric scaling, raw type, pulse/inversion/hold behavior and
other operational configuration do.

Digital/analog outputs apply configured electrical fallback, including when
bad-quality hold was enabled. The application must select the correct physical
fallback; it is not necessarily Boolean FALSE or raw zero. Actuator configuration
changes cancel movement and remove both coil commands. Position observations can
update while motion remains inhibited.

Queued `SetOff` also needs cancellation: with inversion it can energize the output.
The mailbox carries that cancellation across deferred consumption and lock
contention, while preserving urgent Abort and ForceSafe requests.

## Input conditioning

Analog inputs reject unsupported raw types and nonfinite/invalid scaling settings.
Unusable samples or configuration publish BAD quality and hold the last published
value and conditioning history. They cannot rescale stale raw data or advance a
filter using an invalid sample. Recovery with unchanged interpretation resumes
the existing history. A filter configured before the first valid sample retains
the zero-seeded startup behavior.

After valid data has been processed, changes to raw type, raw/EU scaling ranges,
raw bypass, or filter enabled/disabled state discard the old filtering history.
The next usable sample seeds the filter in the current engineering units, then
normal filtering resumes. Invalid configuration or quality cannot consume this
pending reseed. Changing only a nonzero time constant retains history, so tuning
does not cause a measurement jump. Engineering-unit labels are metadata and do
not reset conditioning.

`FB_LPF_FirstOrder_IIR.Seed(value)` supports explicit initialization by the owning
task. It accepts only finite values; a rejected seed changes neither history nor
output. It is not exposed as an operator RPC.

Digital inputs hold the established value and raw sample during unusable quality,
reset pending debounce timers, and suppress edges. Recovery must complete a full
fresh transition delay. Inversion and debounce configuration changes discard old
timing credit; changes during invalid quality cannot reinterpret the held raw value.

Digital input quality watchdogs cover every value other than GOOD/CLAMPED,
including UNKNOWN. A configured watchdog cannot be bypassed by an absent source.

## Reassigning an application signal

A library block cannot identify a different physical sensor when its ordinary
PLC input values and configuration have the same representation. The application
must treat source reassignment as an explicit configuration operation in the
owning task, with dependent machine operation inhibited.

For an analog input, call `ReassignInput()` before supplying the new source.
It immediately publishes UNKNOWN quality, clears the previous source's raw,
scaled and filtered measurements to zero, and requests a new filter seed.
Keep input quality UNKNOWN/BAD until the adapter supplies a fresh sample from
the new binding. The first usable sample initializes new history even when the
numeric configuration is identical. Zero is an invalid placeholder during this
interval; consumers must use quality rather than interpreting it as a reading.

For a digital input, `ReassignInput()` immediately publishes UNKNOWN, clears old
raw/debounced history without emitting an edge, and resets debounce and watchdog
timers. Keep adapter quality unusable until the new binding has a fresh sample;
that sample then follows the current inversion and full debounce delay.

For other digital conditions and output/actuator bindings, inhibit the owning machine,
apply output fallback/Abort, and update the binding and required-condition mapping
coherently. Keep adapter quality unusable until the new source is verified, then
require explicit machine recovery and a fresh command. Changing which signal
feeds an existing condition bit is not detectable from the Boolean alone; do not
reuse a prior good bit as evidence of the new source. This is an application
commissioning operation, not a generic online-change guarantee.

## Readiness and reset

`header.ready` reports idle, fault-free and not source-locked. It is not proof of
valid IO, completed initialization, homing, or permission to move. Use device
quality, inhibition, required conditions and machine state for those decisions.
Reset clears only the faults/recovery state allowed by the device contract;
it is not an instruction to resume old motion.

The canonical reference machine composes quality and shutdown confirmation before
command handling and gates physical output last. Simulation exercises that same
composition. See [reference machine](11-Reference-Machine.md) and
[simulation](12-Simulation.md).

## Execution continuity in the application

The reference machine calls `FB_ExecutionContinuity` from its owning task on
each system-task cycle. It supplies the task index, that task's
`TwinCAT_SystemInfoVarList._TaskInfo[index].CycleCount`, and the application's
`TwinCAT_SystemInfoVarList._AppInfo.OnlineChangeCnt`. The first valid observation
establishes a baseline. A missing cycle, counter rewind, task-source change,
invalid task index reports an execution interruption. `onlineChanged` separately
reports an online-change counter transition. `interrupted` combines a real
execution interruption with the application's `recoverOnOnlineChange` policy
(default `TRUE`). Setting that policy to `FALSE` does not suppress execution
gaps, owner changes or invalid context.
Normal UDINT wraparound is accepted. Repeated observations in one cycle do not
report a gap; this does not permit calling the machine from multiple tasks.

The counter describes the underlying system task, which can continue while PLC
execution is stopped. See Beckhoff's
[task information](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/714821259.html)
and [application information](https://infosys.beckhoff.com/content/1033/cx5000_hw/6769613195.html)
for the supplied counters.

On a detected interruption, the reference machine cancels sequence and actuator
intent before admitting commands, forces both outputs to fallback, and latches
recovery required. A coincident command is discarded; holding it cannot turn it
into later work. Recovery needs an explicit Reset with the machine stopped,
acceptable quality and trusted shutdown feedback, followed by Home and a fresh
Start. Reset alone cannot resume motion. The simulation bridge also rotates its
epoch and clears its session and pending frames, so the client must reconnect
and recover explicitly.

This is an application composition policy. Standalone devices do not acquire
implicit stop/start or online-change handling by using the library. No PLC code
can enforce output changes while it is stopped; terminal/runtime stop behavior
must be configured and qualified separately. A stop/start that skips no system
task tick cannot be detected from these counters. The guard also cannot detect
a new physical signal binding from unchanged input values.

Both the reference machine and simulation bridge expose `recoverOnOnlineChange`.
The bridge passes the same policy to its machine. The conservative default
invalidates motion and the session on every edit. The experimental `FALSE`
setting allows state/session continuity for a compatible edit if execution and
IO remain healthy. This does not classify edits as compatible: the engineer must
review changed code, references and layout. Do not change this policy as a way
to bypass a fault or watchdog. Declaration/layout preservation is not qualified.

`scripts/online_change_commands.ps1` supplies reusable command selection and
dispatch for an already logged-in XAE session. It never falls back to download,
activation or restart. A dispatch receipt explicitly has `RuntimeVerified=false`;
the qualification runner separately checks the runtime counter and retained state.
The runner uses activation only for baseline preparation/restoration and keeps
that evidence separate. It does not yet provide a general MCP deployment endpoint
or explicit control of the boot-project update option.

To exercise the experimental compatible implementation-edit path on an isolated
bench, use `scripts/verify_online_change.py` with `--kind implementation --mode moving
--policy preserve` and the required target/platform/output arguments. The default
`--policy recover` verifies cancellation and recovery. A simulator scheduling or
watchdog failure makes preservation fail; its timing limits are not relaxed.

A dedicated bench run has verified the explicit preservation policy for a moving
implementation edit at a 10 ms task period: the online-change counter advanced,
the same simulator session remained healthy, and the cycle completed without
reconnect or operator recovery. See the current evidence in `PROGRESS.md` in the
repository. This does not qualify arbitrary declaration/layout changes or
eliminate the need to handle real execution gaps.

Online changes can preserve instance state. Changes to declarations can involve
instance copying and `FB_reinit`, while other changes follow different paths.
Do not infer a general online-change guarantee from a fresh-start test or add
explicit calls to the system initialization methods. See Beckhoff's
[operating cases](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/6415331211.html).

## Persistent operating intent and alarm state

Digital and analog output restart restoration requires the explicit
`restoreCommandOnRestart` option, a saved-command validity marker, and a loaded
non-backup persistent image (`BootDataLoaded AND NOT OldBootData`). A fresh
or missing image cannot turn the default FALSE/zero value into a saved command.
Accepted commands set that marker; ForceSafe, Reset and operational configuration
invalidation clear it. The marker is an operating-intent flag, not a checksum or
proof that the image is current, durable, or compatible with the machine.
Rejected image status clears old saved intent so a later trusted startup cannot
revive it. A fresh accepted command in the current execution remains usable.
A RAM-preserving reset that reports no loaded image therefore inhibits restored
outputs; retention alone does not authorize restoring operating intent.

Restored alarm latches preserve acknowledgment. Unacknowledged latches still
need Ack; acknowledged latches need valid clear evidence without a second Ack
solely because the runtime restarted. A restored latch publishes a recognized
configured severity even with invalid startup input. See
[alarm lifecycle](8-Alarms.md) for suppression and validity behavior.

The application must configure and verify saving and restoring persistent data.
Beckhoff documents persistent retention through cold reset/download and
initialization on reset origin; power-loss durability depends on the storage
and save mechanism. See
[remanent variables](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2528803467.html).
Direct ADS reset, XAE cold reset and orderly system restart have retained-data evidence on the
dedicated bench. Reset-origin also has application-removal and initialization
evidence. The complete matrix, including real backup/invalid images and sudden
power interruption, remains open.

## Bypass permissions and numeric helpers

Permissives and interlocks intersect active bypasses with the currently permitted
bypass mask before cyclic evaluation. Revoking permission removes the bypass;
re-allowing it does not recreate it. Reset preserves only still-authorized bypasses.

The standalone low-pass filter rejects NaN/infinite input or timing before updating
history. Valid finite data can recover on a subsequent call. Its calculation avoids
overflow in intermediate time sums and input differences. Finite zero/negative
sampling periods retain the existing pass-through/error behavior. Filter history
is ordinary instance state, not a retained restart guarantee.

`F_IsFiniteReal` and `F_IsFiniteLReal` inspect IEEE exponent bits before floating
point operations. This matters with TwinCAT FPU exception checking enabled:
comparing NaN with itself or converting it is not a safe validation step. IO
configuration, analog samples and queued analog commands use these guards.

## Remaining lifecycle qualification

The implemented configuration, conditioning, alarm and execution-continuity
policies require target-specific acceptance evidence. Tests that inject saved
fields prove startup decisions, not persistent-image durability. Actual
stop/start, reset classes, online changes and power interruptions have separate
acceptance cases in the [qualification plan](10-Qualification.md); implementation
alone does not complete that matrix.
