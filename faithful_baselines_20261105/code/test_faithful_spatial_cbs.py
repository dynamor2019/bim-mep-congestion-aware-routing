"""Software checks for the spatial CBS baseline (not paper data)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faithful_spatial_cbs import find_conflict, spatial_cbs  # noqa: E402
from run_routing_experiments import Commodity, Instance, path_cost  # noqa: E402
from routing_revision_solvers import validate_paths  # noqa: E402


class SpatialCBSTests(unittest.TestCase):
    def test_conflict_detected(self):
        paths = {0: [(0, 1, 0), (1, 1, 0), (2, 1, 0)], 1: [(1, 0, 0), (1, 1, 0), (1, 2, 0)]}
        self.assertEqual(find_conflict(paths), ((1, 1, 0), [0, 1]))

    def test_crossing_resolved_and_optimal(self):
        # Two crossing routes on a 3x3x2 grid: one must detour via z=1.
        inst = Instance((3, 3, 2), set(), [
            Commodity((0, 1, 0), (2, 1, 0), "HVAC", 0.0, 0.0),
            Commodity((1, 0, 0), (1, 2, 0), "pressure", 0.0, 0.0),
        ])
        paths, status, _, _ = spatial_cbs(inst, time.perf_counter() + 10)
        self.assertEqual(status, "solved")
        self.assertTrue(validate_paths(inst, paths))
        total = sum(path_cost(p, inst.commodities[i]) for i, p in paths.items())
        self.assertEqual(total, 2 + 4)  # one straight (2), one detour (4)

    def test_timeout_reported(self):
        inst = Instance((3, 3, 1), set(), [Commodity((0, 0, 0), (2, 2, 0), "HVAC", 0.0, 0.0)])
        _, status, _, _ = spatial_cbs(inst, time.perf_counter() - 1)
        self.assertEqual(status, "timeout")


if __name__ == "__main__":
    unittest.main()
