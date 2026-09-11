import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wait_runtime_ready import wait_ready

class ReadinessTests(unittest.TestCase):
    def test_requires_finite_positive_budgets(self):
        for value in (0, -1, float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wait_ready(['probe'], value, 3, 1)

    def drive(self, results, timeout=10):
        now = [0.0]
        calls = []
        def run(command, **kwargs):
            calls.append(kwargs['timeout'])
            value = results.pop(0)
            if value == 'timeout':
                now[0] += kwargs['timeout']
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return SimpleNamespace(returncode=0, stdout=value)
        def sleep(duration): now[0] += duration
        result = wait_ready(['probe'], timeout, 3, 1, run=run,
                            clock=lambda: now[0], sleep=sleep)
        return result, calls

    def test_requires_consecutive_success(self):
        result, _ = self.drive(['{"ready":true}', '{"ready":false}',
                                '{"ready":true}', '{"ready":true}'])
        self.assertTrue(result['ready'])
        self.assertEqual(len(result['attempts']), 4)

    def test_hung_probe_cannot_exceed_total_budget(self):
        result, calls = self.drive(['timeout', 'timeout'], timeout=5)
        self.assertFalse(result['ready'])
        self.assertEqual(calls, [3, 1])
        self.assertEqual(result['elapsed_seconds'], 5)

    def test_malformed_response_is_not_readiness(self):
        result, _ = self.drive(['secret stderr is not copied', '{"ready":true}',
                                '{"ready":true}'])
        self.assertEqual(result['attempts'][0]['error'], 'InvalidProbeResponse')
        self.assertNotIn('secret', str(result))

if __name__ == '__main__': unittest.main()
