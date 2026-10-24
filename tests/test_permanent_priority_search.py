import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from permanent_priority_search import (
    _topological_order,
    permanent_priority_search,
)
from run_priority_graph_pilot import exact_mcnemar_p
from run_routing_experiments import Commodity, Instance, foreign_terminal_cells


class PermanentPrioritySearchTests(unittest.TestCase):
    def test_topological_order_respects_precedence(self):
        order = _topological_order(3, frozenset({(2, 0), (0, 1)}), [0, 1, 2])
        self.assertEqual(order, [2, 0, 1])

    def test_topological_order_rejects_cycle(self):
        order = _topological_order(2, frozenset({(0, 1), (1, 0)}), [0, 1])
        self.assertIsNone(order)

    def test_exact_mcnemar_uses_binary_discordances(self):
        self.assertEqual(exact_mcnemar_p(1, 1), 1.0)
        self.assertEqual(exact_mcnemar_p(3, 1), 0.625)

    def test_routes_disjoint_commodities(self):
        instance = Instance(
            shape=(4, 3, 1),
            blocked=set(),
            commodities=[
                Commodity((0, 0, 0), (3, 0, 0), "HVAC", 1.0, 1.0),
                Commodity((0, 2, 0), (3, 2, 0), "electrical", 1.0, 1.0),
            ],
        )
        paths, expanded, complete = permanent_priority_search(instance, seed=4)
        self.assertTrue(complete)
        self.assertGreaterEqual(expanded, 1)
        self.assertEqual(set(paths), {0, 1})
        self.assertFalse(set(paths[0][1:-1]) & set(paths[1][1:-1]))

    def test_rejects_nonpositive_node_budget(self):
        instance = Instance(shape=(2, 2, 1), blocked=set(), commodities=[])
        with self.assertRaises(ValueError):
            permanent_priority_search(instance, seed=1, max_nodes=0)

    def test_repair_forbids_other_system_terminals(self):
        instance = Instance(
            shape=(4, 2, 1),
            blocked=set(),
            commodities=[
                Commodity((0, 0, 0), (3, 0, 0), "HVAC", 1.0, 1.0),
                Commodity((1, 1, 0), (2, 1, 0), "electrical", 1.0, 1.0),
            ],
        )
        self.assertEqual(
            foreign_terminal_cells(instance, 0),
            {(1, 1, 0), (2, 1, 0)},
        )


if __name__ == "__main__":
    unittest.main()
