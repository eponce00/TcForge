# 11 Assembly example and focused clamp fixture

## Main example: discrete assembly station

Open `TcForgeExample` in `TwinCAT/TcForge.sln`. Its source folders combine block
and type definitions by purpose:

- `Assembly`: `MAIN`, application IO structures, `GVL_HW` and `FB_AssemblyStation`.
- `Actuators`: reusable `FB_CylinderAssembly` plus feedback/output structures.
  Three instances operate the locating clamp, press and ejector.
- `Inspection`: photoelectric part/discharge sensors and analog pressure/height
  conditioning. The example scales INT terminal values to 0..10 bar and 0..20 mm.
- `ClampCycle`: the small `FB_ReferenceMachine` used for focused lifecycle tests.
- `Simulation`: the ADS bridge that runs the complete assembly station against
  the Python plant model.

Testing and Simulation use a source reference to TcForgeExample. The example
owns these definitions once; no TcForgeReference project is needed. The main
example uses the assembly station, not the small clamp-cycle fixture.

### Assembly recipe

| Step | Action | Completion evidence |
|---|---|---|
| 1000 | Home press and ejector | Both retracted |
| 1002 | Open locating clamp | Clamp retracted |
| 3000 | Wait for a part | Part sensor |
| 3002 | Locate part | Clamp advanced |
| 3004 | Press assembly | Press advanced |
| 3006 | Inspect assembly | Height between 9.5 and 10.5 mm |
| 3008 | Withdraw press | Press retracted |
| 3010 | Release part | Clamp retracted |
| 3012 | Eject finished part | Ejector advanced and part sensor clear |
| 3014 | Park ejector | Ejector retracted; return to READY |

Pressure must remain between 5 and 8 bar and IO quality must be GOOD. Each
recipe phase has a ten-second timeout. This is an example recipe, not a
commissioned press process: it does not implement force control, a reject lane
or safety-rated control. Failed inspection faults the sequence instead of
silently passing or ejecting the part.

The press advance permissive requires a located part. Clamp motion requires
the press retracted. Ejection requires a retracted press/clamp and clear
discharge. Retracting the press/ejector remains possible during homing even
when the locating clamp is not home. Directional permissives are checked in
the reusable actuator assembly, including while movement is in progress.

`MAIN` maps `GVL_HW.inputs` into the station and copies its final outputs back.
The structures are unlinked software channels until an application IO adapter
maps physical terminals or a simulator. All quality values default UNKNOWN;
no GOOD values or simulated feedback are hidden in the station. The Python ADS
bridge supplies one coherent frame for all three cylinders, both photoeyes, and
the pressure and height channels; the PLC executes this same station block.

Stop and Abort remove coil requests and wait for independent shutdown feedback.
Reset is stationary and requires trusted shutdown and healthy inputs; it does
not restart motion. Return a command to `None` before repeating it.

## Focused clamp-cycle fixture

`ClampCycle/FB_ReferenceMachine` remains a small test composition for lifecycle,
online-change and simulation regressions. The following contract describes that
fixture, not the larger assembly recipe above.

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
