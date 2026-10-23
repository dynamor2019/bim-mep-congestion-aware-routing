"""Tests for the isolated hard-deadline experiment runner."""

from __future__ import annotations

import random
import time
import unittest

from run_advanced_validation import scaled_instance
from run_matched_adaptive_hard_deadline import (
    SearchDeadlineExceeded,
    bounded_astar,
    repair,
)
from run_routing_experiments import astar, estimate_demand, route_order


class HardDeadlineRunnerTests(unittest.TestCase):
    """Check interruption and preservation of the common incumbent."""

    def test_low_level_search_stops_at_expired_deadline(self) -> None:
        instance = scaled_instance("base", 17)
        with self.assertRaises(SearchDeadlineExceeded):
            bounded_astar(instance, instance.commodities[0], set(), {}, 0.0, 0.0)

    def test_uninterrupted_search_matches_canonical_astar(self) -> None:
        instance = scaled_instance("base", 19)
        item = instance.commodities[0]
        predicted = estimate_demand(instance)
        expected = astar(instance, item, set(), predicted, 2.0)
        actual = bounded_astar(instance, item, set(), predicted, 2.0,
                               time.perf_counter() + 5.0)
        self.assertEqual(actual, expected)

    def test_timeout_returns_the_valid_initial_solution(self) -> None:
        instance = scaled_instance("base", 18)
        predicted = estimate_demand(instance)
        order = list(range(len(instance.commodities)))
        random.Random(18).shuffle(order)
        initial = route_order(instance, order, predicted, 0.0)
        result, iterations = repair(instance, initial, predicted, 18, 1e-9, True)
        self.assertEqual(result, initial)
        self.assertEqual(iterations, 0)


if __name__ == "__main__":
    unittest.main()
