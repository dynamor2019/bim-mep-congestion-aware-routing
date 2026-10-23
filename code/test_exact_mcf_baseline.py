"""Tests for exact permanent-occupancy multi-commodity flow."""

import unittest

from run_exact_mcf_baseline import solve_exact_mcf
from run_routing_experiments import Commodity, Instance


class ExactMcfBaselineTests(unittest.TestCase):
    """Check path validity and shared-vertex enforcement on small grids."""

    def test_finds_two_disjoint_routes(self):
        instance = Instance(
            (4, 3, 1),
            set(),
            [
                Commodity((0, 0, 0), (3, 0, 0), "water", 0.0, 0.0),
                Commodity((0, 2, 0), (3, 2, 0), "power", 0.0, 0.0),
            ],
        )

        paths, info = solve_exact_mcf(instance, time_limit_s=5.0)

        self.assertEqual(info["status"], "optimal")
        self.assertEqual(len(paths), 2)

    def test_enforces_shared_vertex_capacity(self):
        instance = Instance(
            (3, 3, 1),
            set(),
            [
                Commodity((0, 1, 0), (2, 1, 0), "water", 0.0, 0.0),
                Commodity((1, 0, 0), (1, 2, 0), "power", 0.0, 0.0),
            ],
        )

        paths, info = solve_exact_mcf(instance, time_limit_s=5.0)

        self.assertEqual(info["status"], "optimal")
        self.assertEqual(len(paths), 1)

    def test_rejects_nonpositive_time_limit(self):
        instance = Instance((2, 2, 1), set(), [])

        with self.assertRaises(ValueError):
            solve_exact_mcf(instance, time_limit_s=0.0)


if __name__ == "__main__":
    unittest.main()
