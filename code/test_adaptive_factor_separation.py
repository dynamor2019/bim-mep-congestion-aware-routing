"""Tests for the adaptive factor-separation experiment summaries."""

from __future__ import annotations

import unittest

from run_adaptive_factor_separation import (
    DESIGN,
    METHODS,
    holm_adjust,
    make_instance,
    summarize,
)


class AdaptiveFactorSeparationTests(unittest.TestCase):
    """Check pairing, design-cell aggregation, and multiplicity correction."""

    def test_holm_adjustment_is_monotone_in_rank_order(self) -> None:
        adjusted = holm_adjust([0.04, 0.01, 0.03, 0.20, 0.02])
        self.assertEqual(adjusted, [0.09, 0.05, 0.09, 0.20, 0.08])

    def test_summary_keeps_five_cells_and_paired_discordance(self) -> None:
        rows = []
        for cell_index, (label, _, _) in enumerate(DESIGN):
            for seed in (10, 11):
                random_success = int(seed == 10)
                adaptive_success = int(seed == 11 and cell_index == 0)
                for method, success in zip(METHODS,
                                           (random_success, adaptive_success)):
                    rows.append({
                        "design_cell": label,
                        "seed": seed,
                        "method": method,
                        "success": success,
                        "runtime_s": 1.0,
                    })
        result = summarize(rows)
        self.assertEqual(result["paired_scenes"], 10)
        self.assertEqual(result["validated_outputs"], 20)
        self.assertEqual(len(result["design_results"]), 5)
        self.assertEqual(result["design_results"][0]["random_only"], 1)
        self.assertEqual(result["design_results"][0]["adaptive_only"], 1)
        self.assertEqual(result["design_results"][1]["exact_two_sided_mcnemar_p"], 1.0)

    def test_count_factor_uses_nested_tasks_in_identical_geometry(self) -> None:
        nine = make_instance("xlarge", 9, 130001)
        twelve = make_instance("xlarge", 12, 130001)
        fifteen = make_instance("xlarge", 15, 130001)
        self.assertEqual(nine.shape, twelve.shape)
        self.assertEqual(twelve.shape, fifteen.shape)
        self.assertEqual(nine.blocked, twelve.blocked)
        self.assertEqual(twelve.blocked, fifteen.blocked)
        self.assertEqual(nine.commodities, twelve.commodities[:9])
        self.assertEqual(twelve.commodities, fifteen.commodities[:12])


if __name__ == "__main__":
    unittest.main()
