# 11 Reference machine

`TwinCAT/TcForgeExample/Reference/FB_ReferenceMachine.TcPOU` composes a two-position
clamp using the public TcForge interfaces. The example MAIN assigns its final
outputs to application-owned `GVL_HW` channels. All channels are unlinked and all
qualities default UNKNOWN. No simulation or assumed bus-health signal is hidden
inside the application block.

## Ownership and scan order

Call the machine once per cycle from a single task. The application owns all
commands and every contained device. Do not call the contained blocks from other
tasks or expose them as remote command targets. Remote ownership is a separate
qualification item (A3/Q5).

1. Sample input/output/shutdown quality and map required conditions.
2. Consume a changed command value once. Return `command` to `None` before repeating
   that same command. `lastResponse` records acceptance or rejection; acceptance
   does not mean the movement has completed. Rejected/held commands do not queue
   latent motion.
3. Run the state machine, then each step exactly once, including inactive steps.
4. Run the actuator with the current feedback. Cancel motion when output policy
   inhibits the machine.
5. Apply the final quality/fault/output policy through both digital-output blocks,
   then publish physical command bits and aggregate status.

Use the top-level `faulted` field for same-scan supervision: it includes faults
raised by the actuator after the state-machine call. The nested `sequence` and
`actuator` snapshots describe their own cyclic evaluation. `outputsInhibited`
indicates the machine output gate; output bits remain commands, not feedback.

## Operation and recovery

| Command | Application behavior |
|---|---|
| Home | Retract and require good IO quality plus exclusive retracted feedback; enter READY |
| Start | Advance, then retract, with quality and position requirements at each step; enter READY |
| Stop | Cancel the current move, then retract; enter STOPPED with outputs inhibited |
| Abort | Remove both coil commands immediately, wait for independent confirmed shutdown |
| Reset | Only while stopped, with good input/output quality, consistent position feedback, and independent shutdown confirmation; clear faults without starting movement |

This application deliberately exposes no Pause/Proceed or auto-run behavior.
Motion steps time out after six seconds; the actuator's five-second travel timer
can fault first. Failed Stop escalates to Abort. Abort confirmation times out after
two seconds and latches failed shutdown, following the framework's sequencing
contract. Adapt those timings and the physical shutdown strategy for the machine.

Input or output quality loss removes coil commands in the detecting call and
inhibits operation. Quality restoration alone cannot clear the latched running
interlock or restart movement. Restore healthy IO, provide independent shutdown
feedback, issue Reset, and issue a fresh Home before Start.

`shutdownConfirmed` must come from appropriate physical feedback, with
`shutdownQuality = GOOD`. Never derive it solely from output command bits or the
STOPPED enum. An actuator may retain stored energy with both coils off. This
reference demonstrates control architecture and is not a safety-rated function.
The IO adapter must report UNKNOWN/BAD on lost communication; a stale hardcoded
GOOD value cannot establish physical channel health.

## Simulation and validation

`TwinCAT/Testing.plcproj` lives at the common source root, allowing its compile
entries and the example project to reference the same application files directly.
The repository checker enforces those shared references.

`FB_ReferenceMachine_Test` runs the same application source as the example. Each
scenario calls its machine once per actual PLC cycle. Simulated position inputs
respond to observed final coil outputs; no library internals are injected.
Scenarios cover unknown-quality startup, Home/Run, held Start, controlled Stop,
trusted Abort feedback, input and output quality loss with explicit recovery,
contradictory feedback, rejected Reset during motion, and a real timed failed
Abort followed by rejected/accepted Reset.

Run the isolated test solution and export complete per-test results using the
[qualification workflow](10-Qualification.md). Hardware commissioning must verify
terminal mapping, channel diagnostics, real motion, shutdown feedback, and timing
on the intended PLC. Local Usermode Runtime results do not close that hardware gate.
