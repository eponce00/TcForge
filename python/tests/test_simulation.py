import math
import unittest
from tcforge_sim.models import (
    AssemblyOutputs,
    AssemblyPlant,
    FirstOrderAnalog,
    TwoPositionCylinder,
)
from tcforge_sim.runner import (
    CoilFrame,
    CylinderRunner,
    MemoryCylinderIO,
    StaleFrameError,
)


class PlantTests(unittest.TestCase):
    def test_travel_and_reversal(self):
        plant = TwoPositionCylinder(1)
        middle = plant.step(True, False, 0.5)
        self.assertEqual(middle.position, 0.5)
        self.assertFalse(middle.advanced or middle.retracted)
        self.assertTrue(plant.step(False, True, 0.5).retracted)

    def test_coast_holds_and_conflict_does_not_choose_direction(self):
        plant = TwoPositionCylinder(position=0.5)
        self.assertEqual(plant.step(False, False, 1).position, 0.5)
        feedback = plant.step(True, True, 1)
        self.assertTrue(feedback.conflicting_coils)
        self.assertEqual(feedback.position, 0.5)

    def test_jam_does_not_fabricate_position(self):
        plant = TwoPositionCylinder()
        plant.jammed = True
        self.assertTrue(plant.step(True, False, 10).retracted)

    def test_sensor_fault_independent_of_motion(self):
        plant = TwoPositionCylinder()
        plant.advanced_override = True
        feedback = plant.step(False, False, 0.01)
        self.assertTrue(feedback.advanced and feedback.retracted)
        self.assertEqual(feedback.position, 0)

    def test_analog_exact_solution_and_partition_independence(self):
        one = FirstOrderAnalog(1, 0, 0, 100)
        many = FirstOrderAnalog(1, 0, 0, 100)
        for _ in range(10):
            many.step(100, 0.1)
        self.assertAlmostEqual(one.step(100, 1), 100 * (1 - math.exp(-1)))
        self.assertAlmostEqual(one.value, many.value)

    def test_analog_large_step_stays_bounded(self):
        model = FirstOrderAnalog(1, 50, 0, 100)
        self.assertEqual(model.step(1000, 1000), 100)
        self.assertEqual(model.step(-1000, 1000), 0)

    def test_invalid_time_leaves_plant_unchanged(self):
        for dt in (0, -1, math.nan, math.inf):
            model = TwoPositionCylinder()
            with self.assertRaises(ValueError):
                model.step(True, False, dt)
            self.assertEqual(model.position, 0)

    def test_invalid_parameters(self):
        for tau in (0, -1, math.nan):
            with self.assertRaises(ValueError):
                FirstOrderAnalog(tau, 0, 0, 100)
        with self.assertRaises(ValueError):
            TwoPositionCylinder(position=2)

    def test_assembly_cell_moves_each_axis_independently(self):
        plant = AssemblyPlant(travel_s=1)
        feedback = plant.step(AssemblyOutputs(clamp_advance=True), 0.5)
        self.assertEqual(feedback.clamp.position, 0.5)
        self.assertTrue(feedback.press.retracted)
        self.assertTrue(feedback.ejector.retracted)
        self.assertTrue(feedback.part_present)

    def test_part_leaves_only_at_ejector_forward_limit(self):
        plant = AssemblyPlant(travel_s=1)
        plant.step(AssemblyOutputs(ejector_advance=True), 0.5)
        self.assertTrue(plant.part_present)
        feedback = plant.step(AssemblyOutputs(ejector_advance=True), 0.5)
        self.assertTrue(feedback.ejector.advanced)
        self.assertFalse(feedback.part_present)

    def test_load_part_requires_parked_ejector(self):
        plant = AssemblyPlant(travel_s=1)
        plant.part_present = False
        plant.step(AssemblyOutputs(ejector_advance=True), 0.1)
        with self.assertRaisesRegex(RuntimeError, "ejector"):
            plant.load_part()
        plant.step(AssemblyOutputs(ejector_retract=True), 0.1)
        plant.load_part()
        self.assertTrue(plant.part_present)

    def test_assembly_analog_channels_are_bounded(self):
        plant = AssemblyPlant()
        plant.pressure_target = 100000
        plant.height_target = -100000
        feedback = plant.step(AssemblyOutputs(), 10)
        self.assertEqual(feedback.pressure_raw, 32767)
        self.assertEqual(feedback.height_raw, 0)


class RunnerTests(unittest.TestCase):
    def test_read_model_write_frame_correlation(self):
        io = MemoryCylinderIO()
        io.output = CoilFrame(42, True, False)
        result = CylinderRunner(io, TwoPositionCylinder(1), 0.5).tick()
        self.assertEqual(io.feedback_sequence, 42)
        self.assertEqual(io.feedback.position, 0.5)
        self.assertEqual(result["time_s"], 0.5)

    def test_stale_or_restart_frame_stops_without_advancing(self):
        for sequence in (42, 0):
            io = MemoryCylinderIO()
            io.output = CoilFrame(42, True, False)
            plant = TwoPositionCylinder(1)
            runner = CylinderRunner(io, plant, 0.1)
            runner.tick()
            io.output = CoilFrame(sequence, True, False)
            with self.assertRaises(StaleFrameError):
                runner.tick()
            self.assertEqual(plant.position, 0.1)

    def test_write_failure_does_not_retry_advanced_plant(self):
        class Broken(MemoryCylinderIO):
            def write_inputs(self, sequence, feedback):
                raise OSError("disconnected")

        io = Broken()
        io.output = CoilFrame(0, True, False)
        plant = TwoPositionCylinder(1)
        runner = CylinderRunner(io, plant, 0.1)
        with self.assertRaises(OSError):
            runner.tick()
        with self.assertRaises(RuntimeError):
            runner.tick()
        self.assertEqual(plant.position, 0.1)


if __name__ == "__main__":
    unittest.main()
