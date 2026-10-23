"""Regression tests for wall-clock repair summary statistics."""

from __future__ import annotations

import unittest

from summarize_adaptive_wallclock import exact_mcnemar, holm_adjust, summarize


class WallclockSummaryTests(unittest.TestCase):
    """Check exact paired tests and family-wise p-value adjustment."""

    def test_exact_mcnemar_for_seven_one_sided_discordances(self) -> None:
        self.assertEqual(exact_mcnemar(7, 0), 0.015625)

    def test_holm_adjust_preserves_original_order(self) -> None:
        self.assertEqual(holm_adjust([1.0, 0.015625, 0.125]),
                         [1.0, 0.046875, 0.25])

    def test_summary_holm_adjusts_three_independent_scale_tests(self) -> None:
        rows = []
        outcomes = {
            "base": (11, 2),
            "large": (17, 3),
            "xlarge": (10, 0),
        }
        for scale, (random_only, adaptive_only) in outcomes.items():
            for seed in range(100):
                random_success = int(seed < 20)
                adaptive_success = random_success
                if seed < random_only:
                    random_success, adaptive_success = 1, 0
                elif seed < random_only + adaptive_only:
                    random_success, adaptive_success = 0, 1
                for method, success in (
                    ("mspp_random_repair", random_success),
                    ("adaptive_multi_operator", adaptive_success),
                ):
                    rows.append({
                        "scale": scale,
                        "seed": str(seed),
                        "method": method,
                        "validated": "1",
                        "success": str(success),
                        "runtime_s": "1.0",
                        "iterations_used": "1",
                        "budget_s": "1.0",
                        "scene_hash": f"{scale}-{seed}",
                    })

        result = summarize(rows)
        self.assertEqual(result["paired_scenes"], 300)
        self.assertEqual(result["scale_results"][0]["random_only_successes"], 11)
        adjusted = [item["holm_adjusted_p_across_three_scales"]
                    for item in result["scale_results"]]
        self.assertEqual(adjusted, [0.0224609375, 0.005859375, 0.005859375])


if __name__ == "__main__":
    unittest.main()
