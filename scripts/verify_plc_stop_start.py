"""Exercise PLC STOP/RUN during simulated motion on an explicit dedicated bench.

This verifies missed-cycle recovery, not physical output behavior while PLC code
is stopped. No XAE, download, system restart or persistent-data reset is used.
"""

import argparse
import json
import os
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET

from tcforge_sim.live import AssemblySession, RpcTransport
from tcforge_sim.models import AssemblyPlant


def require(value, message):
    if not value:
        raise AssertionError(message)


def exercise(args, pyads, hold, evidence, trace):
    rpc = session = None
    original_error = None
    with pyads.Connection(args.target, args.port) as plc:
        require(plc.read_state()[0] == pyads.ADSSTATE_RUN, "PLC must initially be RUN")
        try:
            if args.lifecycle_state:
                from lifecycle_fixture import capture

                evidence["persistent_before"] = capture(
                    args.target, args.port, args.lifecycle_state
                )
            rpc = RpcTransport(args.transport, args.target, args.port)
            session = AssemblySession(rpc, trace, AssemblyPlant(0.5))
            session.until(lambda s: s["state"] == 0, command=4)
            session.tick()
            require(session.tick(5)["response"] == 0, "Initial Reset rejected")
            session.tick()
            session.until(lambda s: s["state"] == 16, command=1)
            session.until(
                lambda s: s["clamp_advance"] == 1
                and 0.1 < session.plant.clamp.position < 0.8,
                command=2,
            )
            session.plant.clamp.jammed = True
            before = session.tick()
            require(
                before["clamp_advance"] == 1 and not before["faulted"],
                "No healthy advance before STOP",
            )
            evidence["before"] = before
            old_boot, old_session, old_frame = (
                session.boot,
                session.session,
                session.sequence,
            )
            plant = session.plant
            plc.write_control(
                pyads.ADSSTATE_RESET
                if args.operation == "ads-reset"
                else pyads.ADSSTATE_STOP,
                0,
                0,
                pyads.PLCTYPE_BYTE,
            )
            require(plc.read_state()[0] == pyads.ADSSTATE_STOP, "STOP not confirmed")
            evidence["stopped_coils"] = [
                plc.read_by_name("MAIN.simulation.outAdvance", pyads.PLCTYPE_BOOL),
                plc.read_by_name("MAIN.simulation.outRetract", pyads.PLCTYPE_BOOL),
            ]
            time.sleep(hold)
            plc.write_control(pyads.ADSSTATE_RUN, 0, 0, pyads.PLCTYPE_BYTE)
            require(plc.read_state()[0] == pyads.ADSSTATE_RUN, "RUN not confirmed")
            deadline = time.perf_counter() + 2
            after = rpc.snapshot()
            while (
                not (
                    after["boot"] != old_boot
                    and after["owner"] > 0
                    and after["cycle"] > 0
                )
                and time.perf_counter() < deadline
            ):
                time.sleep(0.002)
                after = rpc.snapshot()
            evidence["after"] = after
            if args.lifecycle_state:
                from lifecycle_fixture import capture, validate_restored

                evidence["persistent_after"] = capture(args.target, args.port)
                evidence["persistent_validation"] = validate_restored(
                    evidence["persistent_before"],
                    evidence["persistent_after"],
                    args.lifecycle_state,
                )
            require(
                after["boot"] != old_boot and after["session"] == 0,
                "Resumed execution retained the previous epoch/session",
            )
            require(
                not after["clamp_advance"]
                and not after["clamp_retract"]
                and after["inhibited"],
                "Old motion resumed after missed execution",
            )
            evidence["stale_claim"] = rpc.call("claim", old_session, old_boot)
            evidence["stale_exchange"] = rpc.call(
                "exchange",
                old_session,
                old_boot,
                old_frame + 1,
                before["cycle"],
                0,
                0,
                1,
                1,
                2,
            )
            require(
                evidence["stale_claim"] == 34 and evidence["stale_exchange"] == 34,
                "Stale operation was not rejected",
            )
            session = None
            plant.clamp.jammed = False
            session = AssemblySession(rpc, trace, plant)
            require(not session.tick()["clamp_advance"], "Claim resumed old motion")
            session.until(lambda s: s["state"] == 0, command=4)
            session.tick()
            require(session.tick(5)["response"] == 0, "Recovery Reset rejected")
            session.tick()
            session.until(lambda s: s["state"] == 16, command=1)
            session.until(lambda s: s["clamp_advance"] == 1, command=2)
            session.until(lambda s: s["clamp_retract"] == 1)
            evidence["recovered"] = session.until(lambda s: s["state"] == 16)
            require(
                plant.clamp.position == 0,
                "Recovery cycle did not return the clamp home",
            )
        except BaseException as exc:
            original_error = exc
            raise
        finally:
            # Preserve the original failure and independently attempt every cleanup.
            cleanup_errors = []
            try:
                if plc.read_state()[0] == pyads.ADSSTATE_STOP:
                    plc.write_control(pyads.ADSSTATE_RUN, 0, 0, pyads.PLCTYPE_BYTE)
            except Exception as exc:
                cleanup_errors.append("Restore RUN: " + str(exc))
            try:
                if session and rpc:
                    evidence["release"] = session.close()
            except Exception as exc:
                cleanup_errors.append("Release session: " + str(exc))
            try:
                if rpc:
                    time.sleep(0.3)
                    evidence["cleanup"] = rpc.snapshot()
                    require(
                        not evidence["cleanup"]["clamp_advance"]
                        and not evidence["cleanup"]["clamp_retract"],
                        "Cleanup did not leave coils off",
                    )
            except Exception as exc:
                cleanup_errors.append("Verify coils: " + str(exc))
            try:
                if rpc:
                    rpc.close()
            except Exception as exc:
                cleanup_errors.append("Close transport: " + str(exc))
            try:
                if args.lifecycle_state:
                    from lifecycle_fixture import clear_outputs

                    evidence["persistent_cleanup"] = clear_outputs(
                        args.target, args.port
                    )
            except Exception as exc:
                cleanup_errors.append("Lifecycle fixture cleanup: " + str(exc))
            evidence["cleanup_errors"] = cleanup_errors
            if cleanup_errors and original_error is None:
                raise RuntimeError("; ".join(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation", choices=("stop-start", "ads-reset"), default="stop-start"
    )
    parser.add_argument("--lifecycle-state", choices=("seed", "safe", "reset"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--transport", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.lifecycle_state and args.operation != "ads-reset":
        parser.error(
            "--lifecycle-state requires --operation ads-reset; STOP/RUN preserves volatile state"
        )
    if os.name != "nt" or not 1 <= args.port <= 65535:
        parser.error("Requires Windows ADS router and a valid PLC port")
    args.transport = args.transport.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    dll_directory = os.add_dll_directory(
        r"C:\Program Files (x86)\Beckhoff\TwinCAT\Common64"
    )
    import pyads

    suite = ET.Element("testsuite", name="PLC stop/start", tests="2")
    results = []
    for hold in (0.03, 0.5) if args.operation == "stop-start" else (0.03,):
        evidence = {
            "target": args.target,
            "port": args.port,
            "hold_seconds": hold,
            "operation": args.operation,
            "passed": False,
        }
        case = ET.SubElement(
            suite, "testcase", name=f"{args.operation}DuringAdvance_{hold}s"
        )
        start = time.perf_counter()
        try:
            with (args.output / f"trace-{hold}.jsonl").open(
                "w", encoding="utf-8"
            ) as trace:
                exercise(args, pyads, hold, evidence, trace)
            evidence["passed"] = True
        except Exception as exc:
            evidence["failure"] = traceback.format_exc()
            ET.SubElement(case, "failure", message=str(exc)).text = evidence["failure"]
        case.set("time", str(time.perf_counter() - start))
        results.append(evidence)
        print("PASS" if evidence["passed"] else "FAIL", case.get("name"), flush=True)
    suite.set("tests", str(len(results)))
    suite.set("failures", str(sum(not r["passed"] for r in results)))
    (args.output / "evidence.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    ET.ElementTree(suite).write(
        args.output / "junit.xml", encoding="utf-8", xml_declaration=True
    )
    dll_directory.close()
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
