"""Transport-independent, explicit read/model/write phases for one plant tick."""
from dataclasses import asdict, dataclass
from typing import Protocol

from .models import CylinderFeedback, TwoPositionCylinder, positive


@dataclass(frozen=True)
class CoilFrame:
    sequence: int
    advance: bool
    retract: bool


class CylinderIO(Protocol):
    def read_outputs(self) -> CoilFrame: ...
    def write_inputs(self, output_sequence: int, feedback: CylinderFeedback) -> None: ...


class StaleFrameError(RuntimeError):
    pass


class CylinderRunner:
    def __init__(self, io: CylinderIO, model: TwoPositionCylinder, dt: float):
        positive(dt, "dt")
        self.io, self.model, self.dt = io, model, dt
        self.last_sequence = -1
        self.elapsed = 0.0
        self.failed = False

    def tick(self) -> dict:
        if self.failed:
            raise RuntimeError("Runner failed; reconnect with a new session and reconcile plant state")
        try:
            frame = self.io.read_outputs()
            if type(frame.sequence) is not int or frame.sequence <= self.last_sequence:
                raise StaleFrameError("Missing, repeated or restarted output frame")
            feedback = self.model.step(frame.advance, frame.retract, self.dt)
            self.io.write_inputs(frame.sequence, feedback)
            self.last_sequence = frame.sequence
            self.elapsed += self.dt
            return {"time_s": self.elapsed, "output": asdict(frame), "input": asdict(feedback)}
        except Exception:
            # The plant may have advanced before a write failed. Never replay that tick.
            self.failed = True
            raise


class MemoryCylinderIO:
    """Offline transport for model/runner tests; not a substitute for executing ST."""
    def __init__(self):
        self.output = CoilFrame(0, False, False)
        self.feedback: CylinderFeedback | None = None
        self.feedback_sequence = -1

    def read_outputs(self) -> CoilFrame:
        return self.output

    def write_inputs(self, output_sequence: int, feedback: CylinderFeedback) -> None:
        self.feedback_sequence, self.feedback = output_sequence, feedback
