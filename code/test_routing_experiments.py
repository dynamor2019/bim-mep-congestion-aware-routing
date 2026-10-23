"""Invariant tests for the synthetic BIM-MEP routing experiment."""

from __future__ import annotations

import unittest

from run_routing_experiments import generate_instance, manhattan, solve


class RoutingExperimentTests(unittest.TestCase):
    """Check generator and returned-route invariants."""

    def test_generation_is_deterministic(self) -> None:
        """The same density and seed must yield the same instance."""
        first = generate_instance("medium", 17)
        second = generate_instance("medium", 17)
        self.assertEqual(first.blocked, second.blocked)
        self.assertEqual(first.commodities, second.commodities)

    def test_returned_routes_are_valid(self) -> None:
        """Returned routes must be connected, collision-free, and compliant."""
        instance = generate_instance("high", 4)
        paths, _, _ = solve(instance, "stage3_only", 4)
        interiors: set[tuple[int, int, int]] = set()
        for index, path in paths.items():
            item = instance.commodities[index]
            self.assertEqual(path[0], item.start)
            self.assertEqual(path[-1], item.goal)
            self.assertTrue(all(manhattan(a, b) == 1 for a, b in zip(path, path[1:])))
            self.assertTrue(all(node not in instance.blocked for node in path))
            self.assertTrue(interiors.isdisjoint(path[1:-1]))
            interiors.update(path[1:-1])
            if item.discipline == "drainage":
                self.assertTrue(all(b[2] <= a[2] for a, b in zip(path, path[1:])))


if __name__ == "__main__":
    unittest.main()
