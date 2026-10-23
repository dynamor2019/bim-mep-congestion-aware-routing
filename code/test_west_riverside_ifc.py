"""Unit tests for IFC representation-profile summaries."""

import unittest

from audit_west_riverside_ifc import summarize_values


class ProfileSummaryTests(unittest.TestCase):
    """Check profile summary statistics and empty-input behavior."""

    def test_summarizes_values_and_flags_extreme_parameters(self):
        result = summarize_values([[0.1, 0.2], [0.3, 12.0]])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["median_m"], [0.2, 6.1])
        self.assertEqual(result["parameters_over_10m"], 1)

    def test_empty_input_has_no_statistics(self):
        self.assertEqual(summarize_values([]), {
            "count": 0,
            "median_m": [],
            "p90_m": [],
            "maximum_m": [],
        })


if __name__ == "__main__":
    unittest.main()
