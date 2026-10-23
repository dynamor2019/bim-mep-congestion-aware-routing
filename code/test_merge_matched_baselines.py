"""Tests for strict merging of matched permanent-space baselines."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from merge_matched_baselines import merge_archives


class MatchedBaselineMergeTests(unittest.TestCase):
    """Ensure only scene-, incumbent-, and budget-matched archives merge."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folders = {name: self.root / name for name in ("cbs", "pbs", "lns")}
        methods = {
            "cbs": ["random", "spatial_cbs"],
            "pbs": ["random", "pbs_static"],
            "lns": ["spatial_mapf_lns2"],
        }
        for folder_name, folder in self.folders.items():
            folder.mkdir()
            (folder / "manifest.json").write_text(json.dumps({
                "budget": {"seconds": 5, "iterations": 100, "nodes": 256}
            }), encoding="utf-8")
            with (folder / "raw.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "method", "seed", "validated", "scene_hash", "initial_objective",
                    "success", "routed", "objective",
                ])
                writer.writeheader()
                for method in methods[folder_name]:
                    writer.writerow({
                        "method": method, "seed": 1, "validated": 1,
                        "scene_hash": "same", "initial_objective": 10,
                        "success": int(method in {"random", "pbs_static"}),
                        "routed": 2, "objective": 10,
                    })

    def tearDown(self):
        self.temp.cleanup()

    def test_merges_four_methods_with_common_budget(self):
        rows, manifest = merge_archives(
            self.folders["cbs"], self.folders["pbs"], self.folders["lns"]
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(manifest["scene_count"], 1)
        self.assertTrue(manifest["same_scenes_and_initial_objectives"])

    def test_rejects_scene_mismatch(self):
        path = self.folders["lns"] / "raw.csv"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(",same,", ",different,"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Scene/incumbent mismatch"):
            merge_archives(self.folders["cbs"], self.folders["pbs"], self.folders["lns"])

    def test_rejects_different_budgets(self):
        path = self.folders["lns"] / "manifest.json"
        path.write_text(json.dumps({"budget": {"seconds": 1, "iterations": 20, "nodes": 256}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "budgets differ"):
            merge_archives(self.folders["cbs"], self.folders["pbs"], self.folders["lns"])


if __name__ == "__main__":
    unittest.main()
