"""Software tests for faithful PBS and ECBS (not paper data)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faithful_spatial_pbs import closure, find_conflict, pbs  # noqa
from faithful_spatial_ecbs import bcbs as ecbs  # noqa
from run_routing_experiments import Commodity, Instance, path_cost  # noqa
from routing_revision_solvers import validate_paths  # noqa


def crossing_instance():
    return Instance((3, 3, 2), set(), [
        Commodity((0, 1, 0), (2, 1, 0), "HVAC", 0.0, 0.0),
        Commodity((1, 0, 0), (1, 2, 0), "pressure", 0.0, 0.0),
    ])


class PBSTests(unittest.TestCase):
    def test_conflict_detected(self):
        paths = {0: [(0,1,0),(1,1,0),(2,1,0)], 1: [(1,0,0),(1,1,0),(1,2,0)]}
        self.assertEqual(find_conflict(paths), (0, 1))

    def test_closure_detects_cycle(self):
        edges = frozenset({(0, 1), (1, 0)})
        self.assertIsNone(closure(edges, 2))

    def test_closure_linear(self):
        edges = frozenset({(0, 1), (1, 2)})
        anc, order = closure(edges, 3)
        self.assertEqual(order, [0, 1, 2])
        self.assertIn(0, anc[2])

    def test_crossing_resolved(self):
        inst = crossing_instance()
        paths, status, _, _ = pbs(inst, time.perf_counter() + 10)
        self.assertEqual(status, "solved")
        self.assertTrue(validate_paths(inst, paths))
        cost = sum(path_cost(p, inst.commodities[i]) for i, p in paths.items())
        self.assertEqual(cost, 6)

    def test_timeout_reported(self):
        inst = crossing_instance()
        _, status, _, _ = pbs(inst, time.perf_counter() - 1)
        self.assertEqual(status, "timeout")


class ECBSTests(unittest.TestCase):
    def test_crossing_resolved(self):
        inst = crossing_instance()
        paths, status, _, _ = ecbs(inst, time.perf_counter() + 10)
        self.assertEqual(status, "solved")
        self.assertTrue(validate_paths(inst, paths))
        cost = sum(path_cost(p, inst.commodities[i]) for i, p in paths.items())
        # ECBS with w=1.5 may accept cost up to 1.5 * optimal(6) = 9
        self.assertLessEqual(cost, 9)

    def test_timeout_reported(self):
        inst = crossing_instance()
        _, status, _, _ = ecbs(inst, time.perf_counter() - 1)
        self.assertEqual(status, "timeout")

    def test_expanded_nodes_not_reexpanded(self):
        # Regression: the first version never removed expanded nodes from OPEN and
        # dropped inherited constraints, so it re-expanded the same node endlessly.
        inst = crossing_instance()
        _, status, expanded, generated = ecbs(inst, time.perf_counter() + 10)
        self.assertEqual(status, "solved")
        self.assertLessEqual(expanded, generated)

    def test_three_way_constraints_accumulate(self):
        # Three services forced through one 1-wide corridor plus a detour layer;
        # solving requires constraints to be inherited across levels.
        inst = Instance((5, 3, 2), set(), [
            Commodity((0, 1, 0), (4, 1, 0), "HVAC", 0.0, 0.0),
            Commodity((2, 0, 0), (2, 2, 0), "pressure", 0.0, 0.0),
            Commodity((1, 0, 0), (1, 2, 0), "electrical", 0.0, 0.0),
        ])
        paths, status, expanded, generated = ecbs(inst, time.perf_counter() + 10)
        self.assertEqual(status, "solved")
        self.assertTrue(validate_paths(inst, paths))
        self.assertLessEqual(expanded, generated)


if __name__ == "__main__":
    unittest.main()
