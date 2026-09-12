import io
import json
import time
import unittest
from unittest.mock import patch
from tcforge_sim.live import AssemblySession, RpcTransport


class FakeRpc:
    def __init__(self):
        self.boot = 100
        self.session = 0
        self.applied = 0
        self.fail_exchange = False
        self.exchanges = 0
        self.claim_delay = 0

    def snapshot(self):
        return dict(
            boot=self.boot,
            session=self.session,
            applied=self.applied,
            cycle=self.applied + 1,
            clamp_advance=0,
            clamp_retract=0,
            press_advance=0,
            press_retract=0,
            ejector_advance=0,
            ejector_retract=0,
        )

    def call(self, operation, *args):
        if operation == "claim":
            time.sleep(self.claim_delay)
            self.session = args[0]
            return 0
        if operation == "exchange":
            self.exchanges += 1
            if self.fail_exchange:
                raise TimeoutError("reply lost after admission")
            self.applied = args[2]
            return 1


class LiveContractTests(unittest.TestCase):
    def test_session_setup_latency_is_outside_cyclic_budget(self):
        rpc = FakeRpc()
        rpc.claim_delay = 0.21
        client = AssemblySession(rpc, io.StringIO())
        self.assertEqual(client.tick()["applied"], 1)

    def test_restart_rejects_before_plant_or_write(self):
        rpc = FakeRpc()
        client = AssemblySession(rpc, io.StringIO())
        rpc.boot += 1
        with self.assertRaisesRegex(RuntimeError, "restarted"):
            client.tick()
        self.assertEqual(rpc.exchanges, 0)
        self.assertTrue(client.failed)

    def test_uncertain_outcome_is_never_replayed(self):
        rpc = FakeRpc()
        trace = io.StringIO()
        client = AssemblySession(rpc, trace)
        rpc.fail_exchange = True
        with self.assertRaises(TimeoutError):
            client.tick()
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            client.tick()
        self.assertEqual(rpc.exchanges, 1)
        events = [json.loads(line) for line in trace.getvalue().splitlines()]
        self.assertEqual(
            [event["event"] for event in events], ["exchange_attempt", "session_failed"]
        )
        self.assertIn("shutdown_confirmed", events[0]["inputs"])
        self.assertEqual(events[-1]["error_type"], "TimeoutError")

    def test_scheduling_gap_fails_before_exchange(self):
        rpc = FakeRpc()
        client = AssemblySession(rpc, io.StringIO())
        with patch(
            "tcforge_sim.live.time.perf_counter", return_value=client.last_time + 0.21
        ):
            with self.assertRaises(TimeoutError):
                client.tick()
        self.assertEqual(rpc.exchanges, 0)

    def test_admitted_frame_records_applied_feedback(self):
        rpc = FakeRpc()
        trace = io.StringIO()
        client = AssemblySession(rpc, trace)
        result = client.tick()
        self.assertEqual(result["applied"], 1)
        self.assertEqual(client.sequence, 1)
        self.assertIn('"frame": 1', trace.getvalue())
        events = [json.loads(line)["event"] for line in trace.getvalue().splitlines()]
        self.assertEqual(
            events, ["exchange_attempt", "exchange_admitted", "exchange_applied"]
        )

    def test_invalid_scenario_timeout_does_not_touch_transport(self):
        rpc = FakeRpc()
        client = AssemblySession(rpc, io.StringIO())
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                client.until(lambda _: True, timeout=value)
        self.assertEqual(rpc.exchanges, 0)

    def test_broken_trace_sink_prevents_exchange(self):
        class BrokenTrace:
            def write(self, _):
                raise OSError("disk full")

        rpc = FakeRpc()
        client = AssemblySession(rpc, BrokenTrace())
        with self.assertRaisesRegex(OSError, "disk full"):
            client.tick()
        self.assertEqual(rpc.exchanges, 0)
        self.assertTrue(client.failed)

    def test_snapshot_rejects_schema_mismatch(self):
        rpc = object.__new__(RpcTransport)
        rpc.call = lambda *_: "0,100,2"
        with self.assertRaisesRegex(RuntimeError, "schema"):
            rpc.snapshot()


if __name__ == "__main__":
    unittest.main()
