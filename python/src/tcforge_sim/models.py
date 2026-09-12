"""Deterministic plant primitives. Time is supplied by the runner, never a wall clock."""

from dataclasses import dataclass
import math


def positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class CylinderFeedback:
    advanced: bool
    retracted: bool
    position: float
    conflicting_coils: bool


class TwoPositionCylinder:
    """Double-solenoid cylinder; both coils off hold position in this plant model.

    Both coils on stop travel and report a conflict. Actual valve/pneumatic
    behavior is machine-specific; this is not a safety or pressure model.
    Sensor overrides affect feedback without changing physical position.
    """

    def __init__(self, travel_s: float = 0.5, position: float = 0.0):
        positive(travel_s, "travel_s")
        if not math.isfinite(position) or not 0 <= position <= 1:
            raise ValueError("position must be finite and within [0, 1]")
        self.travel_s = travel_s
        self.position = position
        self.jammed = False
        self.advanced_override: bool | None = None
        self.retracted_override: bool | None = None

    def step(self, advance: bool, retract: bool, dt: float) -> CylinderFeedback:
        positive(dt, "dt")
        if type(advance) is not bool or type(retract) is not bool:
            raise ValueError("Coil commands must be BOOL values")
        if not self.jammed and advance != retract:
            direction = 1 if advance else -1
            self.position = min(
                1.0, max(0.0, self.position + direction * dt / self.travel_s)
            )
        advanced = self.position >= 1 - 1e-12
        retracted = self.position <= 1e-12
        return CylinderFeedback(
            advanced if self.advanced_override is None else self.advanced_override,
            retracted if self.retracted_override is None else self.retracted_override,
            self.position,
            advance and retract,
        )


class FirstOrderAnalog:
    """Bounded first-order response using the exact constant-input solution."""

    def __init__(self, tau_s: float, initial: float, low: float, high: float):
        positive(tau_s, "tau_s")
        if (
            not all(map(math.isfinite, (initial, low, high)))
            or not low <= initial <= high
            or low >= high
        ):
            raise ValueError("Invalid analog range or initial value")
        self.tau_s, self.value, self.low, self.high = tau_s, initial, low, high

    def step(self, command: float, dt: float) -> float:
        positive(dt, "dt")
        if not math.isfinite(command):
            raise ValueError("command must be finite")
        target = min(self.high, max(self.low, command))
        self.value += (target - self.value) * -math.expm1(-dt / self.tau_s)
        return self.value


@dataclass(frozen=True)
class AssemblyOutputs:
    clamp_advance: bool = False
    clamp_retract: bool = False
    press_advance: bool = False
    press_retract: bool = False
    ejector_advance: bool = False
    ejector_retract: bool = False


@dataclass(frozen=True)
class AssemblyFeedback:
    clamp: CylinderFeedback
    press: CylinderFeedback
    ejector: CylinderFeedback
    part_present: bool
    discharge_clear: bool
    pressure_raw: int
    height_raw: int


class AssemblyPlant:
    """Deterministic three-cylinder assembly cell with discrete and analog IO."""

    def __init__(self, travel_s: float = 0.12):
        self.clamp = TwoPositionCylinder(travel_s, position=0.0)
        self.press = TwoPositionCylinder(travel_s, position=0.0)
        self.ejector = TwoPositionCylinder(travel_s, position=0.0)
        self.pressure = FirstOrderAnalog(0.05, 19660.0, 0.0, 32767.0)
        self.height = FirstOrderAnalog(0.05, 16384.0, 0.0, 32767.0)
        self.pressure_target = 19660.0  # approximately 6 bar
        self.height_target = 16384.0  # approximately 10 mm
        self.part_present = True
        self.discharge_clear = True

    def load_part(self) -> None:
        if self.ejector.position > 1e-12:
            raise RuntimeError("Cannot load a part while the ejector is extended")
        self.part_present = True

    def step(self, outputs: AssemblyOutputs, dt: float) -> AssemblyFeedback:
        if not isinstance(outputs, AssemblyOutputs):
            raise ValueError("outputs must be an AssemblyOutputs frame")
        clamp = self.clamp.step(outputs.clamp_advance, outputs.clamp_retract, dt)
        press = self.press.step(outputs.press_advance, outputs.press_retract, dt)
        ejector = self.ejector.step(
            outputs.ejector_advance, outputs.ejector_retract, dt
        )

        # The part leaves the nest only after the ejector physically reaches its
        # forward sensor. PLC output bits alone never fabricate plant feedback.
        if ejector.advanced and outputs.ejector_advance:
            self.part_present = False

        pressure = round(self.pressure.step(self.pressure_target, dt))
        height = round(self.height.step(self.height_target, dt))
        return AssemblyFeedback(
            clamp=clamp,
            press=press,
            ejector=ejector,
            part_present=self.part_present,
            discharge_clear=self.discharge_clear,
            pressure_raw=pressure,
            height_raw=height,
        )
