"""Tests for deterministic matched-density instance generation."""

import unittest

from run_routing_experiments import astar, manhattan
from run_scaling_matched_density import SCALES, generate_instance


class ScalingGeneratorTests(unittest.TestCase):
    def test_seed_reproduces_geometry_and_terminals(self):
        count, shape = SCALES[1]
        first = generate_instance(shape, count, 210_017)
        second = generate_instance(shape, count, 210_017)
        self.assertEqual(first, second)

    def test_all_scale_families_create_requested_long_pairs(self):
        for index, (count, shape) in enumerate(SCALES):
            instance = generate_instance(shape, count, 200_000 + index)
            self.assertEqual(len(instance.commodities), count)
            self.assertTrue(all(manhattan(c.start, c.goal) >= shape[0] - 3
                                for c in instance.commodities))
            self.assertTrue(all(astar(instance, c, set(), {}, 0.0) is not None
                                for c in instance.commodities))


if __name__ == "__main__":
    unittest.main()
