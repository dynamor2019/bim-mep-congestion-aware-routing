"""Tests for system-level IFC port graph diagnostics."""

import unittest

from audit_digital_hub_ifc import system_topology_summary


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


if __name__ == "__main__":
    unittest.main()
