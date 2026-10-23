"""Regression tests for wall-clock repair summary statistics."""

from __future__ import annotations

import unittest

from summarize_adaptive_wallclock import exact_mcnemar, holm_adjust


class WallclockSummaryTests(unittest.TestCase):
    """Check exact paired tests and family-wise p-value adjustment."""

    def test_exact_mcnemar_for_seven_one_sided_discordances(self) -> None:
        self.assertEqual(exact_mcnemar(7, 0), 0.015625)

    def test_holm_adjust_preserves_original_order(self) -> None:
        self.assertEqual(holm_adjust([1.0, 0.015625, 0.125]),
                         [1.0, 0.046875, 0.25])


if __name__ == "__main__":
    unittest.main()
