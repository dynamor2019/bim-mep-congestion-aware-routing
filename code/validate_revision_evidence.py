"""Check structure and key integrity counts of the archived revision evidence."""

from __future__ import annotations

import argparse
import csv
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

    for name in ("factorial_nested_800.csv", "scale_matched_density_180.csv"):
        require(all(row["validated"] == "1" for row in tables[name]), f"all rows in {name} must be validated")

    audit = json.loads((data / "ifc_full_geometry_audit.json").read_text(encoding="utf-8"))
    require(audit["selected_components"] == 4091, "IFC selected-component count mismatch")
    require(audit["geometry_components"] == 4054, "IFC geometry count mismatch")
    require(audit["native_port_count"] == 8460, "IFC port count mismatch")
    require(audit["explicit_port_edges"] == 4050, "IFC explicit port-edge count mismatch")

    digital_hub = json.loads((data / "digital_hub" / "digital_hub_ifc_audit.json").read_text(encoding="utf-8"))
    inputs = digital_hub["inputs"]
    mep_names = ("heating.ifc", "plumbing.ifc", "ventilation.ifc")
    require(sum(inputs[name]["systems"] for name in mep_names) == 65,
            "Digital Hub IFC system count mismatch")
    require(sum(inputs[name]["ports_with_placement"] for name in mep_names) == 8497,
            "Digital Hub placed-port count mismatch")
    require(sum(inputs[name]["ports_with_system"] for name in mep_names) == 8497,
            "Digital Hub port-system membership count mismatch")
    require(sum(inputs[name]["explicit_port_relations"] for name in mep_names) == 4208,
            "Digital Hub explicit port-relation count mismatch")
    identities = {json.dumps(inputs[name]["identity"], sort_keys=True) for name in ("arc.ifc", *mep_names)}
    require(len(identities) == 1, "Digital Hub IFC identities are not co-registered")
    require(all(inputs[name]["crs"] == "EPSG:3857" for name in ("arc.ifc", *mep_names)),
            "Digital Hub CRS mismatch")
    pair_counts = [item["count"] for item in digital_hub["geometry_sample"]["aabb_pair_candidates"]]
    require(pair_counts == [179, 300, 433, 676], "Digital Hub geometry-sample counts mismatch")
    require(digital_hub["geometry_sample"]["not_full_model_geometry"],
            "Digital Hub geometry scope must remain explicitly sampled")
    print("PASS: main/sensitivity/holdout/factor/scale; prior IFC; Digital Hub identity, semantics, and sampled geometry")


def main() -> None:
    """Parse the archive directory and run checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    validate(args.data)


if __name__ == "__main__":
    main()
