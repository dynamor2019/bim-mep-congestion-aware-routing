"""Tests for repeated adaptive wall-clock summaries."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from summarize_adaptive_wallclock_repeats import summarize_repeats


class AdaptiveWallclockRepeatTests(unittest.TestCase):
    """Verify paired repeat integrity and non-pooled summaries."""

    def test_reports_repeat_runs_without_pooling_scenes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"run_{index}.csv" for index in range(2)]
            for index, path in enumerate(paths):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=[
                        "scale", "seed", "method", "scene_hash", "success", "runtime_s", "validated"
                    ])
                    writer.writeheader()
                    for method, success in (("mspp_random_repair", 1),
                                            ("adaptive_multi_operator", 0)):
                        writer.writerow({"scale": "base", "seed": 1, "method": method,
                                         "scene_hash": "same", "success": success,
                                         "runtime_s": 1.0 + index * 0.1, "validated": 1})
            summary = summarize_repeats(paths)
        self.assertEqual(summary["unique_paired_scenes"], 1)
        self.assertEqual(summary["repeat_count"], 2)
        self.assertEqual(summary["outcome_switches_across_repeats"]["mspp_random_repair"], 0)
        self.assertIn("do not pool", summary["inference_note"])

    def test_rejects_changed_scene_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"run_{index}.csv" for index in range(2)]
            for index, path in enumerate(paths):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=[
                        "scale", "seed", "method", "scene_hash", "success", "runtime_s", "validated"
                    ])
                    writer.writeheader()
                    for method in ("mspp_random_repair", "adaptive_multi_operator"):
                        writer.writerow({"scale": "base", "seed": 1, "method": method,
                                         "scene_hash": f"hash-{index}", "success": 0,
                                         "runtime_s": 1.0, "validated": 1})
            with self.assertRaisesRegex(ValueError, "Scene hash changed"):
                summarize_repeats(paths)


if __name__ == "__main__":
    unittest.main()
