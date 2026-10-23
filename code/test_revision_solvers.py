"""Independent regression checks for the revised search methods."""

import unittest

from routing_revision_solvers import (
    RoutingContext, SearchBudget, blocker_graph, closure, first_conflict,
    lns, pbs, spatial_cbs, validate_paths,
)
from run_routing_experiments import Commodity, Instance, estimate_demand


class RevisedSolverTests(unittest.TestCase):
    """Exercise conflict branching, transitive priorities and terminal safety."""

    def setUp(self):
        self.instance = Instance((3, 3, 2), set(), [
            Commodity((0, 1, 0), (2, 1, 0), "pressure", 0, 0),
            Commodity((1, 0, 0), (1, 2, 0), "pressure", 0, 0),
        ])
        self.context = RoutingContext(self.instance, estimate_demand(self.instance))

    def test_pbs_resolves_independent_path_conflict(self):
        roots = {i: self.context.plan(i) for i in range(2)}
        self.assertIsNotNone(first_conflict(roots))
        paths, _, info = pbs(self.context, {}, SearchBudget(seconds=5))
        self.assertEqual(info["status"], "solved")
        self.assertGreater(info["nodes"], 1)
        self.assertEqual(len(paths), 2)
        self.assertTrue(validate_paths(self.instance, paths))

    def test_spatial_cbs_resolves_permanent_vertex_conflict(self):
        paths, _, info = spatial_cbs(
            self.context, SearchBudget(seconds=1, nodes=100)
        )
        self.assertEqual(info["status"], "solved")
        self.assertEqual(len(paths), 2)
        self.assertTrue(validate_paths(self.instance, paths))

    def test_priority_closure_and_cycle_rejection(self):
        ancestors, order = closure({(0, 1), (1, 2)}, 3)
        self.assertEqual(ancestors[2], {0, 1})
        self.assertEqual(order, [0, 1, 2])
        self.assertIsNone(closure({(0, 1), (1, 0)}, 2))

    def test_blocker_score_uses_failed_path_intersections(self):
        probes = {i: self.context.plan(i) for i in range(2)}
        scores, neighbors = blocker_graph(self.context, {0: probes[0]}, probes)
        self.assertEqual(scores[0], 1)
        self.assertEqual(neighbors[1], {0})

    def test_all_selectors_return_valid_accepted_paths(self):
        initial = self.context.sequential([0, 1])
        for method in ("random", "length", "guided", "blocker", "conflict", "adaptive"):
            paths, trace, _ = lns(self.context, initial, method, 1, SearchBudget(seconds=5, iterations=3))
            self.assertTrue(validate_paths(self.instance, paths))
            costs = [row["objective"] for row in trace]
            self.assertEqual(costs, sorted(costs, reverse=True))


if __name__ == "__main__":
    unittest.main()
