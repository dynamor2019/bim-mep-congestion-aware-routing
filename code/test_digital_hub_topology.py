"""Tests for system-level IFC port graph diagnostics."""

import unittest

from audit_digital_hub_ifc import system_topology_summary
from summarize_digital_hub_topology import directed_terminal_pair_summary


class DigitalHubTopologyTests(unittest.TestCase):
    def test_component_and_branch_counts_use_system_membership(self):
        graph = {
            "systems": [{"id": 7, "name": "system-a"}],
            "vertices": [
                {"id": index, "systems": [7]} for index in range(4)
            ] + [{"id": 4, "systems": [8]}],
            "edges": [
                {"from": 0, "to": 1},
                {"from": 1, "to": 2},
                {"from": 1, "to": 3},
                {"from": 3, "to": 4},
            ],
        }
        result = system_topology_summary(graph)
        record = result["systems"][0]
        self.assertEqual(record["connected_components"], 1)
        self.assertEqual(record["largest_component_ports"], 4)
        self.assertEqual(record["branch_ports_degree_gt_2"], 1)
        self.assertEqual(result["summary"]["isolated_port_memberships"], 0)

    def test_only_source_sink_component_is_counted_as_directed_pair(self):
        graph = {
            "systems": [{"id": 7, "name": "rainwater"}],
            "vertices": [
                {"id": 0, "ifc_id": 10, "owner_type": "IfcWasteTerminal", "systems": [7], "flow_direction": "SOURCE"},
                {"id": 1, "ifc_id": 11, "owner_type": "IfcPipeSegment", "systems": [7]},
                {"id": 2, "ifc_id": 12, "owner_type": "IfcWasteTerminal", "systems": [7], "flow_direction": "SINK"},
            ],
            "edges": [{"from": 0, "to": 1}, {"from": 1, "to": 2}],
        }
        result = directed_terminal_pair_summary(graph)
        self.assertEqual(result["two_terminal_components"], 1)
        self.assertEqual(result["directed_source_sink_pairs"], 1)

        graph["vertices"][2]["flow_direction"] = "SOURCE"
        ambiguous = directed_terminal_pair_summary(graph)
        self.assertEqual(ambiguous["two_terminal_components"], 1)
        self.assertEqual(ambiguous["directed_source_sink_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
