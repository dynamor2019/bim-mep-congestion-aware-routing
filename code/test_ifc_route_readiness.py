"""Tests for IFC readiness component summaries."""

import unittest

from audit_ifc_route_readiness import connected_component_summary


class IfcRouteReadinessTests(unittest.TestCase):
    def test_counts_only_strict_two_terminal_source_sink_components(self):
        summary = connected_component_summary(
            {1, 2, 3, 4, 5},
            [(1, 2), (2, 3), (4, 5)],
            {1: {"SOURCE"}, 3: {"SINK"}, 4: {"SOURCE", "SINK"}},
        )
        self.assertEqual(summary["owner_component_count"], 2)
        self.assertEqual(summary["components_with_exact_source_sink_terminal_pair"], 1)
        self.assertEqual(summary["components_by_terminal_owner_count"], {"1": 1, "2": 1})

    def test_branching_multi_terminal_component_is_not_a_point_pair(self):
        summary = connected_component_summary(
            {1, 2, 3, 4},
            [(1, 2), (2, 3), (2, 4)],
            {1: {"SOURCE"}, 3: {"SINK"}, 4: {"SINK"}},
        )
        self.assertEqual(summary["owner_component_count"], 1)
        self.assertEqual(summary["components_with_exact_source_sink_terminal_pair"], 0)
        self.assertEqual(summary["components_by_terminal_owner_count"], {"3": 1})


if __name__ == "__main__":
    unittest.main()
