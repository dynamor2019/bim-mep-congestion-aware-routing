"""Check structure and key integrity counts of the archived revision evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    """Load a UTF-8 CSV while tolerating a BOM."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(condition: bool, message: str) -> None:
    """Raise an actionable error for a failed archive invariant."""
    if not condition:
        raise ValueError(message)


def validate(data: Path) -> None:
    """Validate row totals, method balance, and source-audit counts."""
    main = rows(data / "main_150_raw.csv")
    require(len(main) == 750, "main benchmark must contain 750 rows")
    main_groups: dict[str, set[str]] = defaultdict(set)
    for row in main:
        main_groups[f"{row['density']}:{row['seed']}"].add(row["method"])
    require(len(main_groups) == 150, "main benchmark must contain 150 scenes")
    require(all(len(methods) == 5 for methods in main_groups.values()), "main scenes must have five methods each")

    validation = json.loads((data / "main_150_validation.json").read_text(encoding="utf-8"))
    require(validation.get("validated_paths") == 750, "main validation must report 750 validated paths")
    require(validation.get("invalid_paths") == 0, "main validation must report zero invalid paths")

    expected_rows = {
        "sensitivity_990_raw.csv": 990,
        "high_stress_holdout_800.csv": 800,
        "high_stress_holdout_900.csv": 900,
        "factorial_nested_800.csv": 800,
        "scale_matched_density_180.csv": 180,
    }
    tables = {name: rows(data / name) for name in expected_rows}
    for name, expected in expected_rows.items():
        require(len(tables[name]) == expected, f"{name} must contain {expected} rows")

    holdout = tables["high_stress_holdout_800.csv"]
    require(all(row["validated"] == "1" for row in holdout), "all holdout rows must be validated")
    holdout_groups = defaultdict(set)
    for row in holdout:
        holdout_groups[row["seed"]].add(row["method"])
    require(len(holdout_groups) == 100 and all(len(methods) == 8 for methods in holdout_groups.values()),
            "holdout must have 100 scenes and eight methods per scene")

    conflict = rows(data / "conflict_neighborhood_holdout_100.csv")
    require(len(conflict) == 100 and all(row["method"] == "conflict" and row["validated"] == "1"
                                         for row in conflict),
            "conflict-neighborhood holdout must contain 100 validated outputs")
    conflict_manifest = json.loads(
        (data / "conflict_neighborhood_holdout_100.manifest.json").read_text(encoding="utf-8-sig")
    )
    conflict_digest = hashlib.sha256(
        (data / "conflict_neighborhood_holdout_100.csv").read_bytes()
    ).hexdigest()
    require(conflict_manifest["sha256"]["raw_csv"] == conflict_digest,
            "conflict-neighborhood CSV checksum mismatch")

    expanded_holdout = tables["high_stress_holdout_900.csv"]
    expanded_groups = defaultdict(set)
    for row in expanded_holdout:
        require(row["validated"] == "1", "all expanded holdout outputs must be validated")
        expanded_groups[row["seed"]].add(row["method"])
    require(len(expanded_groups) == 100 and all(len(methods) == 9 for methods in expanded_groups.values()),
            "expanded holdout must contain nine methods for each of 100 scenes")

    cbs = rows(data / "spatial_cbs_holdout_100.csv")
    require(len(cbs) == 100 and all(row["method"] == "spatial_cbs" for row in cbs),
            "spatial CBS diagnostic must contain one row per holdout scene")
    holdout_hashes = {row["seed"]: row["scene_hash"] for row in holdout}
    require(all(row["seed"] in holdout_hashes and row["scene_hash"] == holdout_hashes[row["seed"]]
                for row in cbs), "spatial CBS rows must match the original holdout scenes")
    require(all(row["seed"] in holdout_hashes and row["scene_hash"] == holdout_hashes[row["seed"]]
                for row in conflict), "conflict-neighborhood rows must match the original holdout scenes")
    require(all(row["seed"] in holdout_hashes and row["scene_hash"] == holdout_hashes[row["seed"]]
                for row in expanded_holdout), "expanded holdout rows must match the original holdout scenes")
    require(all(row["validated"] == "1" for row in cbs), "all CBS outputs must pass independent validation")
    require(sum(int(row["success"]) for row in cbs) == 0,
            "archived CBS diagnostic should contain no complete route sets")

    for name in ("factorial_nested_800.csv", "scale_matched_density_180.csv"):
        require(all(row["validated"] == "1" for row in tables[name]), f"all rows in {name} must be validated")

    audit = json.loads((data / "ifc_full_geometry_audit.json").read_text(encoding="utf-8"))
    require(audit["selected_components"] == 4091, "IFC selected-component count mismatch")
    require(audit["geometry_components"] == 4054, "IFC geometry count mismatch")
    require(audit["native_port_count"] == 8460, "IFC port count mismatch")
    require(audit["explicit_port_edges"] == 4050, "IFC explicit port-edge count mismatch")
    print("PASS: 150/750 main, 990 sensitivity, 100-scene/9-method holdout + 100 spatial CBS, 800 factorial, 180 scale, IFC audit counts")


def main() -> None:
    """Parse the archive directory and run checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    validate(args.data)


if __name__ == "__main__":
    main()
