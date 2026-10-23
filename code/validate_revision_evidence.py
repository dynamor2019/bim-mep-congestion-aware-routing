"""Check structure and key integrity counts of the archived revision evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def rows(path: Path) -> list[dict[str, str]]:
    """Load a UTF-8 CSV while tolerating a BOM."""
    csv.field_size_limit(10_000_000)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(condition: bool, message: str) -> None:
    """Raise an actionable error for a failed archive invariant."""
    if not condition:
        raise ValueError(message)


def validate_advanced_pilot(data: Path) -> None:
    """Check the exploratory multi-operator pilot archive and route flags."""
    pilot_dir = data / "advanced_validation_5seed"
    manifest = json.loads((pilot_dir / "manifest.json").read_text(encoding="utf-8"))
    pilot = rows(pilot_dir / "advanced_validation_raw.csv")
    require(len(pilot) == 45 and manifest["rows"] == 45,
            "advanced pilot must contain 45 observations")
    require(all(row["validated"] == "1" for row in pilot),
            "all advanced pilot routes must pass independent validation")
    require(all(int(row["success"]) == int(int(row["routed"]) == int(row["total"]))
                for row in pilot), "advanced pilot success flags must match routed counts")
    source_path = data.parent.parent / "code" / "run_advanced_validation.py"
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    require(manifest["source_sha256"] == source_digest,
            "advanced pilot source checksum mismatch")
    for filename, expected in manifest["files"].items():
        path = pilot_dir / filename
        require(path.stat().st_size == expected["bytes"],
                f"advanced pilot file size mismatch: {filename}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"],
                f"advanced pilot checksum mismatch: {filename}")
    groups = Counter((row["size"], row["method"]) for row in pilot)
    require(all(groups[(size, method)] == 5
                for size in ("base", "large", "xlarge")
                for method in ("mspp_random_repair", "adaptive_multi_operator", "conflict_guided")),
            "advanced pilot must contain five paired seeds per size and method")
    expected = manifest["key_outcomes"]
    for size in ("large", "xlarge"):
        for method in ("mspp_random_repair", "adaptive_multi_operator", "conflict_guided"):
            complete = sum(int(row["success"]) for row in pilot
                            if row["size"] == size and row["method"] == method)
            require(complete == expected[size][f"{method}_complete"],
                    f"advanced pilot completion count mismatch: {size}/{method}")


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
        "high_stress_holdout_1000.csv": 1000,
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

    lns2 = rows(data / "spatial_mapf_lns2_holdout_100.csv")
    require(len(lns2) == 100 and all(row["method"] == "spatial_mapf_lns2" and row["validated"] == "1"
                                     for row in lns2),
            "spatial MAPF-LNS2 adaptation must contain 100 validated outputs")
    lns2_manifest = json.loads(
        (data / "spatial_mapf_lns2_holdout_100.manifest.json").read_text(encoding="utf-8-sig")
    )
    lns2_digest = hashlib.sha256(
        (data / "spatial_mapf_lns2_holdout_100.csv").read_bytes()
    ).hexdigest()
    require(lns2_manifest["published_csv_sha256"] == lns2_digest,
            "spatial MAPF-LNS2 CSV checksum mismatch")

    expanded_holdout = tables["high_stress_holdout_900.csv"]
    expanded_groups = defaultdict(set)
    for row in expanded_holdout:
        require(row["validated"] == "1", "all expanded holdout outputs must be validated")
        expanded_groups[row["seed"]].add(row["method"])
    require(len(expanded_groups) == 100 and all(len(methods) == 9 for methods in expanded_groups.values()),
            "expanded holdout must contain nine methods for each of 100 scenes")

    full_holdout = tables["high_stress_holdout_1000.csv"]
    full_groups = defaultdict(set)
    for row in full_holdout:
        require(row["validated"] == "1", "all current holdout outputs must be validated")
        full_groups[row["seed"]].add(row["method"])
    require(len(full_groups) == 100 and all(len(methods) == 10 for methods in full_groups.values()),
            "current holdout must contain ten methods for each of 100 scenes")
    full_keys = {(row["seed"], row["method"]): row for row in full_holdout}
    source_rows = expanded_holdout + lns2
    source_keys = {(row["seed"], row["method"]): row for row in source_rows}
    require(len(full_keys) == len(source_keys) == 1000 and full_keys.keys() == source_keys.keys(),
            "merged holdout keys must equal the nine-method archive plus the LNS2-style extension")
    require(all(full_keys[key]["scene_hash"] == source_keys[key]["scene_hash"]
                for key in full_keys), "merged holdout must preserve source scene hashes")

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
    require(all(row["seed"] in holdout_hashes and row["scene_hash"] == holdout_hashes[row["seed"]]
                for row in lns2), "spatial MAPF-LNS2 rows must match the original holdout scenes")
    require(all(row["validated"] == "1" for row in cbs), "all CBS outputs must pass independent validation")
    require(sum(int(row["success"]) for row in cbs) == 0,
            "archived CBS diagnostic should contain no complete route sets")

    cbs_5s = rows(data / "spatial_cbs_holdout_100_5s.csv")
    cbs_5s_manifest = json.loads(
        (data / "spatial_cbs_holdout_100_5s.manifest.json").read_text(encoding="utf-8-sig")
    )
    cbs_5s_digest = hashlib.sha256(
        (data / "spatial_cbs_holdout_100_5s.csv").read_bytes()
    ).hexdigest()
    require(len(cbs_5s) == 100 and all(row["method"] == "spatial_cbs" for row in cbs_5s),
            "five-second spatial CBS diagnostic must contain 100 outputs")
    require(cbs_5s_manifest["sha256"] == cbs_5s_digest,
            "five-second spatial CBS CSV checksum mismatch")
    require(all(row["validated"] == "1" and float(row["runtime_s"]) <= 5.2 for row in cbs_5s),
            "five-second spatial CBS outputs must be validated and respect the time budget")
    require(all(row["seed"] in holdout_hashes and row["scene_hash"] == holdout_hashes[row["seed"]]
                for row in cbs_5s), "five-second CBS rows must match the original holdout scenes")
    require(sum(int(row["success"]) for row in cbs_5s) == 0
            and cbs_5s_manifest["status_counts"] == {"budget": 94, "individual_infeasible": 6},
            "five-second CBS diagnostic outcome mismatch")

    exact_dir = data / "exact_mcf"
    exact_manifest = json.loads((exact_dir / "manifest.json").read_text(encoding="utf-8"))
    exact_hashes = {row["seed"]: row["scene_hash"] for row in holdout}
    for budget, expected_statuses, expected_complete in ((1, {"optimal": 29, "limit": 71}, 1),
                                                          (30, {"optimal": 84, "limit": 16}, 24)):
        filename = f"holdout_100_{budget}s.csv"
        exact_rows = rows(exact_dir / filename)
        run_manifest = exact_manifest["runs"][filename]
        digest = hashlib.sha256((exact_dir / filename).read_bytes()).hexdigest()
        require(len(exact_rows) == 100 and all(row["validated"] == "1" for row in exact_rows),
                f"exact MCF {budget}s run must contain 100 validated outputs")
        require(all(row["seed"] in exact_hashes and row["scene_hash"] == exact_hashes[row["seed"]]
                    for row in exact_rows), f"exact MCF {budget}s scenes must match the holdout hashes")
        require({row["seed"] for row in exact_rows} == set(exact_hashes),
                f"exact MCF {budget}s must contain each holdout seed exactly once")
        require(all(int(row["routed"]) <= int(row["total"])
                    and int(row["success"]) == int(int(row["routed"]) == int(row["total"]))
                    for row in exact_rows), f"exact MCF {budget}s success flags must match routed counts")
        require(dict(Counter(row["status"] for row in exact_rows)) == expected_statuses,
                f"exact MCF {budget}s solver status counts mismatch")
        require(run_manifest["status_counts"] == expected_statuses
                and run_manifest["time_limit_seconds"] == budget,
                f"exact MCF {budget}s manifest summary mismatch")
        require(sum(int(row["success"]) for row in exact_rows) == expected_complete,
                f"exact MCF {budget}s complete-set count mismatch")
        require(all(float(row["runtime_s"]) <= budget + 3.0 for row in exact_rows),
                f"exact MCF {budget}s run exceeded its recorded wall-clock tolerance")
        require(run_manifest["sha256"] == digest,
                f"exact MCF {budget}s checksum mismatch")
    require(exact_manifest["rows_per_budget"] == 100
            and exact_manifest["paired_scene_hashes_match"] is True,
            "exact MCF manifest pairing metadata mismatch")

    for name in ("factorial_nested_800.csv", "scale_matched_density_180.csv"):
        require(all(row["validated"] == "1" for row in tables[name]), f"all rows in {name} must be validated")

    audit = json.loads((data / "ifc_full_geometry_audit.json").read_text(encoding="utf-8"))
    require(audit["selected_components"] == 4091, "IFC selected-component count mismatch")
    require(audit["geometry_components"] == 4054, "IFC geometry count mismatch")
    require(audit["native_port_count"] == 8460, "IFC port count mismatch")
    require(audit["explicit_port_edges"] == 4050, "IFC explicit port-edge count mismatch")
    topology = json.loads((data / "digital_hub" / "digital_hub_native_topology.json").read_text(encoding="utf-8"))
    pair_counts = {
        name: summary["directed_source_sink_pairs"]
        for name, summary in topology["terminal_pair_readiness"].items()
    }
    require(pair_counts == {"heating": 0, "plumbing": 0, "ventilation": 0},
            "Digital Hub terminal-pair readiness mismatch")

    budget_dir = data / "extended_budget_diagnostics"
    budget_manifest = json.loads((budget_dir / "manifest.json").read_text(encoding="utf-8"))
    budget_rows = {}
    for filename, expected in budget_manifest["files"].items():
        path = budget_dir / filename
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"],
                f"extended budget diagnostic checksum mismatch: {filename}")
        budget_rows[filename] = rows(path)
        require(len(budget_rows[filename]) == expected["rows"],
                f"extended budget diagnostic row count mismatch: {filename}")
        require(all(row["validated"] == "1" for row in budget_rows[filename]),
                f"extended budget diagnostic has unvalidated rows: {filename}")
    pbs = {row["seed"]: row for row in budget_rows["pbs_30s_nodes_10.csv"]}
    random_runs = {row["seed"]: row for row in budget_rows["random_30s_10.csv"]}
    require(set(pbs) == set(random_runs) == {str(seed) for seed in budget_manifest["seeds"]},
            "extended PBS/random seed pairing mismatch")
    require(all(pbs[seed]["scene_hash"] == random_runs[seed]["scene_hash"] for seed in pbs),
            "extended PBS/random scenes are not matched")
    reference_hashes = {
        row["seed"]: row["scene_hash"]
        for row in tables["high_stress_holdout_1000.csv"]
        if row["seed"] in pbs
    }
    require(reference_hashes.keys() == pbs.keys()
            and all(pbs[seed]["scene_hash"] == reference_hashes[seed] for seed in pbs),
            "extended budget scenes do not match the archived 100-scene holdout")
    require(sum(int(row["success"]) for row in pbs.values()) == 3
            and sum(int(row["success"]) for row in random_runs.values()) == 2,
            "extended PBS/random success counts mismatch")
    pair_counts = Counter((int(pbs[seed]["success"]), int(random_runs[seed]["success"]))
                          for seed in pbs)
    require(pair_counts == Counter({(0, 0): 7, (1, 1): 2, (1, 0): 1}),
            "extended PBS/random paired outcomes mismatch")
    require(sum(int(row["success"]) for row in budget_rows["cbs_30s_nodes_10.csv"]) == 0
            and len(budget_rows["cbs_120s_nodes_1.csv"]) == 1
            and budget_rows["cbs_120s_nodes_1.csv"][0]["status"] == "budget",
            "extended CBS budget outcomes mismatch")
    validate_advanced_pilot(data)
    print("PASS: primary archives, IFC audit/readiness, extended-budget diagnostics, and advanced-pilot hashes and route validation")


def main() -> None:
    """Parse the archive directory and run checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    validate(args.data)


if __name__ == "__main__":
    main()
