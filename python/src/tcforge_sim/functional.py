"""Execute complete assembly-cell scenarios against the isolated TwinCAT PLC."""

import argparse
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET

from .live import AssemblySession, RpcTransport


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def outputs_off(state):
    return not any(
        state[name]
        for name in (
            "clamp_advance",
            "clamp_retract",
            "press_advance",
            "press_retract",
            "ejector_advance",
            "ejector_retract",
        )
    )


def run(rpc, trace, suite):
    session = AssemblySession(rpc, trace)

    def check(name, action):
        node = ET.SubElement(suite, "testcase", name=name, classname="TcForge.Assembly")
        start = time.perf_counter()
        try:
            action()
            print("PASS", name, flush=True)
        except Exception as exc:
            ET.SubElement(
                node, "failure", message=str(exc)
            ).text = traceback.format_exc()
            print("FAIL", name, str(exc), flush=True)
            raise
        finally:
            node.set("time", str(time.perf_counter() - start))

    def raw_exchange(frame, output_frame, command):
        return rpc.call(
            "exchange",
            session.session,
            session.boot,
            frame,
            output_frame,
            0,
            1,
            0,
            1,
            0,
            1,
            1,
            1,
            19660,
            16384,
            1,
            1,
            command,
        )

    def ready():
        for cylinder in (
            session.plant.clamp,
            session.plant.press,
            session.plant.ejector,
        ):
            cylinder.jammed = False
            cylinder.advanced_override = None
            cylinder.retracted_override = None
        session.plant.discharge_clear = True
        session.plant.pressure_target = 19660
        session.plant.height_target = 16384
        session.quality_good = True
        session.shutdown_confirmed = True

        session.until(lambda state: state["state"] == 0, command=4)
        session.tick()
        state = session.tick(5)
        require(state["response"] == 0, "Explicit Reset rejected")
        session.tick()
        if not session.plant.part_present:
            session.plant.load_part()
        session.until(lambda state: state["state"] == 16, command=1)

    def protocol():
        session.tick()
        require(rpc.call("claim", 0, session.boot) == 30, "Zero client accepted")
        session.tick()
        require(
            rpc.call("claim", session.session + 1, session.boot) == 11,
            "Second writer accepted",
        )
        session.tick()
        require(
            rpc.call("claim", session.session, session.boot + 1) == 34,
            "Wrong boot accepted",
        )
        snapshot = session.tick()
        require(
            raw_exchange(session.sequence + 1, snapshot["cycle"], 99) == 30,
            "Invalid command admitted",
        )
        require(
            rpc.snapshot()["applied"] == session.sequence,
            "Invalid command changed applied sequence",
        )
        state = session.tick()
        require(
            raw_exchange(session.sequence, state["cycle"], 0) == 35,
            "Duplicate frame accepted",
        )
        require(
            rpc.snapshot()["applied"] == session.sequence,
            "Rejected frame changed applied sequence",
        )
        require(state["owner"] > 0, "No cyclic owner")

    def full_cycle():
        ready()
        session.until(lambda state: state["clamp_advance"] == 1, command=2)
        session.until(lambda state: state["press_advance"] == 1)
        session.until(lambda state: state["press_retract"] == 1)
        session.until(lambda state: state["clamp_retract"] == 1)
        session.until(lambda state: state["ejector_advance"] == 1)
        session.until(lambda state: state["ejector_retract"] == 1)
        session.until(lambda state: state["state"] == 16)
        require(not session.plant.part_present, "Finished part did not leave the nest")
        require(session.plant.ejector.position < 1e-9, "Ejector did not park")

    def stop():
        ready()
        session.until(lambda state: state["press_advance"] == 1, command=2)
        state = session.until(lambda value: value["state"] == 0, command=3)
        require(outputs_off(state), "Controlled Stop left an assembly output on")

    def abort():
        ready()
        session.until(lambda state: state["press_advance"] == 1, command=2)
        state = session.until(lambda value: value["state"] == 0, command=4)
        require(outputs_off(state), "Abort left an assembly output on")

    def jam():
        ready()
        session.plant.press.jammed = True
        state = session.until(
            lambda value: value["faulted"] == 1, timeout=13, command=2
        )
        require(outputs_off(state), "Press jam timeout left an output on")

    def contradiction():
        ready()
        session.plant.clamp.advanced_override = True
        session.plant.clamp.retracted_override = True
        state = session.until(lambda value: value["faulted"] == 1)
        require(
            outputs_off(state), "Contradictory clamp sensors did not inhibit outputs"
        )

    def bad_quality():
        ready()
        session.until(lambda state: state["press_advance"] == 1, command=2)
        session.quality_good = False
        state = session.tick()
        require(state["inhibited"], "Lost IO quality did not set inhibition")
        require(outputs_off(state), "Lost IO quality did not inhibit every output")

    def blocked_discharge():
        ready()
        session.plant.discharge_clear = False
        state = session.until(lambda value: value["state"] == 0, timeout=5, command=2)
        require(
            session.plant.ejector.position < 1e-9, "Blocked discharge allowed ejection"
        )
        require(outputs_off(state), "Blocked discharge left an output on")

    def shutdown_confirmation():
        ready()
        session.until(lambda state: state["press_advance"] == 1, command=2)
        session.shutdown_confirmed = False
        state = session.tick(4)
        require(outputs_off(state), "Abort did not remove outputs immediately")
        state = session.until(lambda value: value["faulted"] == 1, timeout=7)
        require(outputs_off(state), "Shutdown timeout energized an output")
        session.tick()
        state = session.tick(5)
        require(state["response"] != 0, "Reset bypassed shutdown confirmation")
        session.shutdown_confirmed = True
        session.tick()
        state = session.tick(5)
        require(state["response"] == 0, "Trusted shutdown did not allow Reset")
        require(outputs_off(state), "Recovery restarted motion")

    def watchdog():
        nonlocal session
        ready()
        session.until(lambda state: state["press_advance"] == 1, command=2)
        plant = session.plant
        time.sleep(0.4)
        state = rpc.snapshot()
        require(
            state["session"] == 0 and not state["healthy"],
            "Stale writer retained session",
        )
        require(outputs_off(state), "Watchdog left an assembly output on")
        require(
            raw_exchange(session.sequence + 1, state["cycle"], 2) == 12,
            "Expired session accepted Start",
        )
        session = AssemblySession(rpc, trace, plant)
        state = session.tick()
        require(outputs_off(state), "Reconnect restarted motion")

    try:
        check("ExclusiveSessionAndRejectedFrames", protocol)
        check("CompleteLocatePressInspectEjectCycle", full_cycle)
        check("ControlledStopRemovesAllOutputs", stop)
        check("AbortRemovesAllOutputs", abort)
        check("JammedPressTimesOut", jam)
        check("ContradictoryClampSensors", contradiction)
        check("LostIOQualityInhibitsAllOutputs", bad_quality)
        check("BlockedDischargePreventsEjection", blocked_discharge)
        check("IndependentShutdownConfirmationAndRecovery", shutdown_confirmation)
        check("SimulatorLossAndExplicitReconnect", watchdog)
        check("ExplicitRecoveryAfterReconnect", ready)
    finally:
        try:
            session.close()
            time.sleep(0.03)
            require(outputs_off(rpc.snapshot()), "Released fixture not inhibited")
        except Exception:
            if not suite.findall(".//failure"):
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--transport", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", name="TcForge discrete assembly functional tests")
    properties = ET.SubElement(suite, "properties")
    for name, value in {
        "target": args.target,
        "port": str(args.port),
        "time_mode": "wall-clock",
    }.items():
        ET.SubElement(properties, "property", name=name, value=value)
    rpc = None
    failed = False
    try:
        rpc = RpcTransport(args.transport, args.target, args.port)
        with (args.output / "assembly-trace.jsonl").open(
            "w", encoding="utf-8"
        ) as trace:
            run(rpc, trace, suite)
    except Exception as exc:
        failed = True
        if not suite.findall(".//failure"):
            node = ET.SubElement(suite, "testcase", name="SetupOrCleanup")
            ET.SubElement(
                node, "failure", message=str(exc)
            ).text = traceback.format_exc()
    finally:
        if rpc:
            rpc.close()
        suite.set("tests", str(len(suite.findall("testcase"))))
        suite.set("failures", str(len(suite.findall(".//failure"))))
        ET.ElementTree(suite).write(
            args.output / "assembly-junit.xml", encoding="utf-8", xml_declaration=True
        )
    if failed:
        raise SystemExit(1)
    print(
        f"All {len(suite.findall('testcase'))} assembly functional scenarios passed against the PLC."
    )


if __name__ == "__main__":
    main()
