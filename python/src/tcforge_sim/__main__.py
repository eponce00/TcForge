"""Run a deterministic offline motion/fault scenario and produce JSONL evidence."""

import argparse
import json
from pathlib import Path
from .models import TwoPositionCylinder
from .runner import CoilFrame, CylinderRunner, MemoryCylinderIO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    io = MemoryCylinderIO()
    plant = TwoPositionCylinder()
    runner = CylinderRunner(io, plant, 0.01)
    args.trace.parent.mkdir(parents=True, exist_ok=True)
    with args.trace.open("w", encoding="utf-8") as trace:
        for tick in range(200):
            plant.jammed = 120 <= tick < 140
            io.output = CoilFrame(tick, tick < 70, tick >= 100)
            row = runner.tick()
            row["faults"] = {"jammed": plant.jammed}
            trace.write(json.dumps(row, allow_nan=False) + "\n")
    if io.feedback is None or not io.feedback.retracted:
        raise RuntimeError("Offline scenario did not retract")
    print(
        f"200 deterministic plant ticks passed; trace: {args.trace}. PLC execution is separate."
    )


if __name__ == "__main__":
    main()
