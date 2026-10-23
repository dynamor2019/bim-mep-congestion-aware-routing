"""Tests for repeated primary benchmark runtime summaries."""

from __future__ import annotations

import unittest

from summarize_primary_runtime_repeats import exact_mcnemar


class PrimaryRuntimeRepeatTests(unittest.TestCase):
    """Verify the paired exact test used in the runtime audit."""

    def test_exact_mcnemar_for_four_losses_and_one_gain(self) -> None:
        self.assertEqual(exact_mcnemar(4, 1), (0.375, 0.96875))

    def test_exact_mcnemar_for_five_losses_and_two_gains(self) -> None:
        self.assertEqual(exact_mcnemar(5, 2), (0.453125, 0.9375))


if __name__ == "__main__":
    unittest.main()
