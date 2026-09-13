import itertools
import math
import unittest

from tcforge_sim.control_loop import ControlLoopTransport, GOOD, SYMBOL


class FakeControlFixture:
    def __init__(self, *, acknowledge=True, fail_commit=False):
        self.values = dict(
            appliedFrame=0,
            outputCv=0.0,
            ready=False,
            watchdogExpired=False,
            watchdogTrips=0,
            ownerTask=1,
            cycleCounter=10,
        )
        self.writes = []
        self.acknowledge = acknowledge
        self.fail_commit = fail_commit

    def read_by_name(self, symbol):
        return self.values[symbol.removeprefix(SYMBOL)]

    def read_list_by_name(self, symbols):
        return {symbol: self.read_by_name(symbol) for symbol in symbols}

    def write_list_by_name(self, values):
        for symbol, value in values.items():
            self.write_by_name(symbol, value)
        return {symbol: "no error" for symbol in values}

    def write_by_name(self, symbol, value):
        field = symbol.removeprefix(SYMBOL)
        self.writes.append((field, value))
        self.values[field] = value
        if field == "requestFrame":
            if self.acknowledge:
                self.values["appliedFrame"] = value
                self.values["outputCv"] = 25.0
                self.values["ready"] = True
                self.values["cycleCounter"] += 1
            if self.fail_commit:
                raise TimeoutError("reply lost after frame commit")


class ControlLoopTransportTests(unittest.TestCase):
    def test_payload_precedes_commit_and_acknowledged_cv_is_read(self):
        fixture = FakeControlFixture()
        transport = ControlLoopTransport(fixture)

        state = transport.exchange(pv=12.5, quality=GOOD, setpoint=60.0, enable=True)

        self.assertEqual(state.frame, 1)
        self.assertEqual(state.cv, 25.0)
        self.assertTrue(state.ready)
        self.assertEqual(
            [name for name, _ in fixture.writes],
            ["requestEnable", "requestPv", "requestQuality", "requestSetpoint", "requestFrame"],
        )

    def test_uncertain_commit_cannot_be_replayed(self):
        fixture = FakeControlFixture(fail_commit=True)
        transport = ControlLoopTransport(fixture)

        with self.assertRaisesRegex(TimeoutError, "reply lost"):
            transport.exchange(pv=0.0, quality=GOOD, setpoint=60.0, enable=True)
        count = len(fixture.writes)
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            transport.exchange(pv=0.0, quality=GOOD, setpoint=60.0, enable=True)
        self.assertEqual(len(fixture.writes), count)

    def test_missing_acknowledgement_ends_session(self):
        fixture = FakeControlFixture(acknowledge=False)
        ticks = itertools.count()
        transport = ControlLoopTransport(
            fixture, clock=lambda: next(ticks) * 0.2, sleep=lambda _: None
        )

        with self.assertRaisesRegex(TimeoutError, "acknowledge"):
            transport.exchange(pv=0.0, quality=GOOD, setpoint=60.0, enable=True)
        self.assertTrue(transport.failed)

    def test_invalid_numeric_input_is_rejected_before_any_write(self):
        fixture = FakeControlFixture()
        transport = ControlLoopTransport(fixture)

        with self.assertRaises(ValueError):
            transport.exchange(pv=math.nan, quality=GOOD, setpoint=60.0, enable=True)
        self.assertEqual(fixture.writes, [])
        self.assertFalse(transport.failed)


if __name__ == "__main__":
    unittest.main()
