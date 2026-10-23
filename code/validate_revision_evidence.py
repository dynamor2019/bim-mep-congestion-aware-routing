"""Check structure and key integrity counts of the archived revision evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

LEGACY_CBS_SOURCE_SHA256 = "bee3be91f0f65e1762fbf0e44785701a16deca39475652a7e2abf8ff39968667"


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


def validate_clinic_ifc_audit(data: Path) -> None:
    """Check the archived medical-dental IFC readiness screen."""
    audit_path = data / "ifc_bench_dental_clinic_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    require(audit["license"] == "CC BY 4.0" and len(audit["models"]) == 2,
            "clinic IFC audit source or model count mismatch")
    by_name = {record["file"]: record for record in audit["models"]}
    expected = {
        "Clinic_HVAC.ifc": (7390, 3695, 440, 1548, 1590, 417),
        "Clinic_Plumbing.ifc": (13058, 6529, 119, 2893, 3318, 87),
    }
    for name, values in expected.items():
        record = by_name[name]
        counts = record["counts"]
        _, _, _, segments, _, largest_terminals = values
        require((counts["distribution_ports"], counts["port_connections"],
                 counts["flow_terminals"], counts["flow_segments"],
                 counts["flow_fittings"]) == values[:5],
                f"clinic IFC count mismatch: {name}")
        require(counts["segments_with_geometry_representation"] == segments
                and counts["segments_with_dimensions_pset"] == segments,
                f"clinic IFC dimension/geometry coverage mismatch: {name}")
        require(counts["systems"] == 0
                and record["owner_graph"]["components_with_exact_source_sink_terminal_pair"] == 0,
                f"clinic IFC topology readiness mismatch: {name}")
        histogram = record["owner_graph"]["components_by_terminal_owner_count"]
        require(max(int(key) for key in histogram) == largest_terminals,
                f"clinic IFC largest terminal component mismatch: {name}")
    require(audit["audit_script_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "audit_ifc_route_readiness.py").read_bytes()
    ).hexdigest(), "clinic IFC audit script checksum mismatch")


def validate_ifc4x3_pcert_audit(data: Path) -> None:
    """Check source hashes and readiness counts for the IFC4X3 PCERT audit."""
    audit = json.loads((data / "ifc4x3_pcert_audit.json").read_text(encoding="utf-8"))
    require(audit["license"] == "CC BY 4.0" and len(audit["models"]) == 2,
            "IFC4X3 audit source or model count mismatch")
    expected = {
        "Building-Hvac.ifc": (1, 1, 2),
        "Infra-Plumbing.ifc": (1, 24, 0),
    }
    for model in audit["models"]:
        counts = model["counts"]
        systems, segments, terminals = expected[model["file"]]
        require(model["schema"] == "IFC4X3"
                and (counts["systems"], counts["flow_segments"],
                     counts["flow_terminals"]) == (systems, segments, terminals),
                f"IFC4X3 model counts mismatch: {model['file']}")
        require(counts["distribution_ports"] == 0
                and counts["port_connections"] == 0
                and counts["flow_fittings"] == 0
                and counts["segments_with_dimensions_pset"] == 0
                and counts["segments_with_geometry_representation"] == segments,
                f"IFC4X3 route-readiness boundary mismatch: {model['file']}")
        require(model["owner_graph"]["components_with_exact_source_sink_terminal_pair"] == 0,
                f"IFC4X3 endpoint graph unexpectedly eligible: {model['file']}")
    require(audit["audit_script_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "audit_ifc_route_readiness.py").read_bytes()
    ).hexdigest(), "IFC4X3 audit script checksum mismatch")


def validate_expanded_adaptive_archive(data: Path) -> None:
    """Check the 270-pair adaptive archive, checksums, pairing, and outcomes."""
    archive = data / "matched_adaptive_scale_270.csv"
    manifest = json.loads(
        (data / "matched_adaptive_scale_270.manifest.json").read_text(encoding="utf-8")
    )
    observations = rows(archive)
    require(len(observations) == 540 and all(row["validated"] == "1" for row in observations),
            "expanded adaptive archive must contain 540 validated outputs")
    require(manifest["paired_scenes"] == 270 and manifest["validated_outputs"] == 540
            and manifest["raw_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest(),
            "expanded adaptive manifest or raw checksum mismatch")
    for source in manifest["input_archives"]:
        source_path = data / source["file"]
        require(hashlib.sha256(source_path.read_bytes()).hexdigest() == source["sha256"],
                f"expanded adaptive source checksum mismatch: {source['file']}")
    summary = data / "matched_adaptive_scale_270_summary.json"
    require(hashlib.sha256(summary.read_bytes()).hexdigest() == manifest["summary_sha256"],
            "expanded adaptive summary checksum mismatch")
    pairs = defaultdict(dict)
    for row in observations:
        pairs[(row["scale"], row["seed"])][row["method"]] = row
    require(len(pairs) == 270 and all(set(pair) == {
        "mspp_random_repair", "adaptive_multi_operator"} for pair in pairs.values()),
        "expanded adaptive archive must contain 270 complete pairs")
    require(all(len({row["scene_hash"] for row in pair.values()}) == 1
                for pair in pairs.values()), "adaptive methods must use identical scenes")
    expected = {"base": (8, 6), "large": (42, 47), "xlarge": (72, 69)}
    for scale, counts in expected.items():
        selected = [pair for (name, _), pair in pairs.items() if name == scale]
        actual = tuple(sum(int(pair[method]["success"]) for pair in selected)
                       for method in ("mspp_random_repair", "adaptive_multi_operator"))
        require(len(selected) == 90 and actual == counts,
                f"expanded adaptive completion counts mismatch: {scale}")


def validate_new_revision_evidence(data: Path) -> None:
    """Check the new paired adaptive, CBS-incumbent, and plant-room audits."""
    adaptive = rows(data / "matched_adaptive_scale_90.csv")
    manifest = json.loads((data / "matched_adaptive_scale_90.csv.manifest.json").read_text(encoding="utf-8"))
    require(len(adaptive) == 180 and all(row["validated"] == "1" for row in adaptive),
            "matched adaptive archive must contain 180 validated outputs")
    require(manifest["outputs"] == 180 and manifest["all_validated"] is True
            and manifest["scene_hash_count"] == 90,
            "matched adaptive manifest counts mismatch")
    require(manifest["source_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "run_matched_adaptive_scale.py").read_bytes()
    ).hexdigest(), "matched adaptive source checksum mismatch")
    pairs = defaultdict(dict)
    for row in adaptive:
        pairs[(row["scale"], row["seed"])][row["method"]] = row
    require(len(pairs) == 90 and all(set(pair) == {
        "mspp_random_repair", "adaptive_multi_operator"} for pair in pairs.values()),
        "matched adaptive archive must contain 90 complete pairs")
    require(all(len({row["scene_hash"] for row in pair.values()}) == 1
                for pair in pairs.values()), "adaptive methods must use identical scenes")
    expected = {"base": (3, 3), "large": (13, 15), "xlarge": (25, 26)}
    for scale, counts in expected.items():
        selected = [pair for (name, _), pair in pairs.items() if name == scale]
        actual = tuple(sum(int(pair[method]["success"]) for pair in selected)
                       for method in ("mspp_random_repair", "adaptive_multi_operator"))
        require(len(selected) == 30 and actual == counts,
                f"matched adaptive completion counts mismatch: {scale}")
    validate_expanded_adaptive_archive(data)
    cbs = rows(data / "cbs_incumbent_5s_holdout_10.csv")
    require(len(cbs) == 20 and all(row["validated"] == "1" for row in cbs),
            "CBS incumbent diagnostic must contain 20 validated method outputs")
    cbs_groups = defaultdict(dict)
    for row in cbs:
        cbs_groups[row["seed"]][row["method"]] = row
    require(len(cbs_groups) == 10 and all(set(group) == {"random", "spatial_cbs"}
                                          for group in cbs_groups.values()),
            "CBS incumbent diagnostic must have ten paired scenes")
    require(sum(int(row["success"]) for row in cbs
                if row["method"] == "spatial_cbs") == 0
            and round(sum(int(row["routed"]) for row in cbs
                          if row["method"] == "spatial_cbs") / 10, 1) == 4.3,
            "CBS incumbent completion or routed-demand summary mismatch")
    plantroom = json.loads((data / "public_plantroom_dataset_audit.json").read_text(encoding="utf-8"))
    require((plantroom["case_count"], plantroom["pipe_network_count"],
             plantroom["terminal_point_count"], plantroom["multi_terminal_network_count"])
            == (7, 48, 216, 48), "plant-room dataset audit counts mismatch")
    require(plantroom["direct_point_to_point_benchmark_eligible"] is False,
            "plant-room compatibility boundary must remain explicit")


def validate_matched_cbs_diagnostic(data: Path) -> None:
    """Verify the same-scene, equal-wall-clock spatial CBS diagnostic."""
    archive = data / "spatial_cbs_matched_5s_10.csv"
    manifest = json.loads((data / "spatial_cbs_matched_5s_10.manifest.json").read_text(encoding="utf-8"))
    observations = rows(archive)
    require(len(observations) == 20 and all(row["validated"] == "1" for row in observations),
            "matched CBS archive must have 20 validated route outputs")
    require(manifest["budget"]["seconds"] == 5.0
            and manifest["arguments"]["iterations"] == 10000,
            "matched CBS runtime budget metadata mismatch")
    require(manifest["source_sha256"] == LEGACY_CBS_SOURCE_SHA256,
            "matched CBS archive is not tied to the v2.11.0 solver source")
    require(manifest["raw_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest(),
            "matched CBS archive checksum mismatch")
    pairs = defaultdict(dict)
    for row in observations:
        pairs[row["seed"]][row["method"]] = row
    require(len(pairs) == 10 and all(set(pair) == {"random", "spatial_cbs"}
                                     for pair in pairs.values()),
            "matched CBS archive must contain ten complete pairs")
    require(all(pair["random"]["scene_hash"] == pair["spatial_cbs"]["scene_hash"]
                for pair in pairs.values()), "CBS and random must use identical scenes")
    require(sum(int(row["success"]) for row in observations if row["method"] == "random") == 2
            and sum(int(row["success"]) for row in observations if row["method"] == "spatial_cbs") == 0,
            "matched CBS completion counts mismatch")


def validate_extended_cbs_diagnostic(data: Path) -> None:
    """Check the 60-scene, paired wall-clock spatial CBS extension."""
    archive = data / "spatial_cbs_total_matched_60.csv"
    manifest = json.loads((data / "spatial_cbs_total_matched_60.manifest.json").read_text(encoding="utf-8"))
    observations = rows(archive)
    require(len(observations) == 120 and all(row["validated"] == "1" for row in observations),
            "extended CBS archive must contain 120 validated method outputs")
    require(manifest["scene_count"] == 60 and manifest["method_output_count"] == 120
            and manifest["method_budget_seconds"] == 4.8
            and manifest["shared_initialization_computed"] is True
            and manifest["common_incumbent_passed_to_cbs"] is False,
            "extended CBS manifest metadata mismatch")
    require(manifest["source_sha256"] == LEGACY_CBS_SOURCE_SHA256,
            "extended CBS archive is not tied to the v2.11.0 solver source")
    require(manifest["raw_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest(),
            "extended CBS raw checksum mismatch")
    pairs = defaultdict(dict)
    for row in observations:
        pairs[row["seed"]][row["method"]] = row
    require(len(pairs) == 60 and all(set(pair) == {"random", "spatial_cbs"}
                                     for pair in pairs.values()),
            "extended CBS archive must contain 60 complete pairs")
    require(all(pair["random"]["scene_hash"] == pair["spatial_cbs"]["scene_hash"]
                for pair in pairs.values()), "extended CBS methods must use identical scenes")
    require(sum(int(row["success"]) for row in observations if row["method"] == "random") == 9
            and sum(int(row["success"]) for row in observations if row["method"] == "spatial_cbs") == 0,
            "extended CBS completion counts mismatch")


def validate_current_cbs_incumbent_diagnostic(data: Path) -> None:
    """Verify the corrected same-cohort CBS comparison and provenance hashes."""
    archive = data / "spatial_cbs_incumbent_matched_100_5s" / "raw.csv"
    manifest_path = archive.with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = rows(archive)
    require(len(observations) == 200 and manifest["scene_count"] == 100,
            "corrected CBS archive must contain 100 paired scenes")
    require(all(row["validated"] == "1" for row in observations),
            "all corrected CBS route outputs must be independently validated")
    require(manifest["raw_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest(),
            "corrected CBS archive checksum mismatch")
    require(manifest["provenance"]["cbs_solver_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "routing_revision_solvers.py").read_bytes()
    ).hexdigest(), "corrected CBS solver checksum mismatch")
    pairs = defaultdict(dict)
    for row in observations:
        pairs[row["seed"]][row["method"]] = row
    require(len(pairs) == 100 and all(set(pair) == {"random", "spatial_cbs"}
                                     for pair in pairs.values()),
            "corrected CBS archive must contain complete method pairs")
    require(all(pair["random"]["scene_hash"] == pair["spatial_cbs"]["scene_hash"]
                and pair["random"]["initial_objective"]
                == pair["spatial_cbs"]["initial_objective"]
                for pair in pairs.values()),
            "corrected CBS pairs must match scene and logged incumbent")
    require(sum(int(pair["random"]["success"]) for pair in pairs.values()) == 19
            and sum(int(pair["spatial_cbs"]["success"]) for pair in pairs.values()) == 9,
            "corrected CBS paired success counts mismatch")
    require(sum(int(pair["random"]["success"]) == 1
                and int(pair["spatial_cbs"]["success"]) == 0
                for pair in pairs.values()) == 10
            and sum(int(pair["random"]["success"]) == 0
                    and int(pair["spatial_cbs"]["success"]) == 1
                    for pair in pairs.values()) == 0,
            "corrected CBS discordant outcomes mismatch")


def validate_matched_pbs_diagnostic(data: Path) -> None:
    """Check the paired 100-scene, five-second PBS-adaptation archive."""
    archive = data / "pbs_matched_5s_100" / "raw.csv"
    manifest = json.loads(archive.with_name("manifest.json").read_text(encoding="utf-8"))
    observations = rows(archive)
    require(len(observations) == 200 and manifest["scene_count"] == 100,
            "matched PBS archive must contain 100 paired scenes")
    require(all(row["validated"] == "1" for row in observations),
            "all matched PBS route outputs must be independently validated")
    require(manifest["raw_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest(),
            "matched PBS raw archive checksum mismatch")
    require(manifest["solver_source_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "routing_revision_solvers.py").read_bytes()
    ).hexdigest(), "matched PBS solver source checksum mismatch")
    pairs = defaultdict(dict)
    for row in observations:
        pairs[row["seed"]][row["method"]] = row
    require(len(pairs) == 100 and all(set(pair) == {"random", "pbs_static"}
                                      for pair in pairs.values()),
            "matched PBS archive must have 100 complete pairs")
    require(all(pair["random"]["scene_hash"] == pair["pbs_static"]["scene_hash"]
                for pair in pairs.values()), "PBS and random must use identical scenes")
    require(sum(int(row["success"]) for row in observations if row["method"] == "random") == 19
            and sum(int(row["success"]) for row in observations if row["method"] == "pbs_static") == 20,
            "matched PBS completion counts mismatch")


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

    factorial = tables["factorial_nested_800.csv"]
    factorial_groups: dict[tuple[int, float], dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in factorial:
        key = (int(row["n_systems"]), float(row["obstacle_rate"]))
        factorial_groups[key][row["method"]].append(row)
        require(int(row["n_generated"]) == key[0],
                "factorial generated-system count must match its assigned factor")
        require(int(row["success"]) == int(int(row["routed"]) == key[0]),
                "factorial success flag must match routed and generated counts")
    expected_cells = {(5, 0.045), (5, 0.085), (9, 0.045), (9, 0.085)}
    require(set(factorial_groups) == expected_cells,
            "factorial archive must contain all four system-count/obstacle cells")
    for key, methods in factorial_groups.items():
        require(set(methods) == {"random", "guided"}
                and all(len(methods[name]) == 100 for name in methods),
                f"factorial cell must have 100 paired scenes per method: {key}")
        paired = {name: {row["seed"]: row for row in rows}
                  for name, rows in methods.items()}
        require(set(paired["random"]) == set(paired["guided"]),
                f"factorial methods must use matched seeds: {key}")
        require(all(paired["random"][seed]["scene_hash"]
                    == paired["guided"][seed]["scene_hash"]
                    and paired["random"][seed]["terminal_hash"]
                    == paired["guided"][seed]["terminal_hash"]
                    for seed in paired["random"]),
                f"factorial methods must use identical scenes and terminals: {key}")
    factorial_manifest_path = data / "factorial_nested_800.manifest.json"
    factorial_manifest = json.loads(
        factorial_manifest_path.read_text(encoding="utf-8")
    )
    factorial_path = data / "factorial_nested_800.csv"
    require(factorial_manifest["rows"] == 800
            and factorial_manifest["scenes"] == 400
            and factorial_manifest["all_routes_independently_validated"] is True,
            "factorial manifest scope or validation status mismatch")
    require(factorial_manifest["output_bytes"] == factorial_path.stat().st_size
            and factorial_manifest["output_sha256"] == hashlib.sha256(
                factorial_path.read_bytes()
            ).hexdigest(), "factorial output checksum mismatch")
    require(factorial_manifest["source_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "run_factorial_density.py").read_bytes()
    ).hexdigest(), "factorial generator checksum mismatch")
    require(factorial_manifest["router_sha256"] == hashlib.sha256(
        (data.parent.parent / "code" / "run_routing_experiments.py").read_bytes()
    ).hexdigest(), "factorial router checksum mismatch")
    expected_successes = {
        "5_0.045": {"random": 97, "guided": 96},
        "5_0.085": {"random": 93, "guided": 91},
        "9_0.045": {"random": 34, "guided": 31},
        "9_0.085": {"random": 9, "guided": 12},
    }
    require(factorial_manifest["cell_successes"] == expected_successes,
            "factorial completion counts differ from the verified rerun")

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
    validate_clinic_ifc_audit(data)
    validate_ifc4x3_pcert_audit(data)
    validate_new_revision_evidence(data)
    validate_matched_cbs_diagnostic(data)
    validate_extended_cbs_diagnostic(data)
    validate_current_cbs_incumbent_diagnostic(data)
    validate_matched_pbs_diagnostic(data)
    print("PASS: primary archives, IFC readiness screens, budget diagnostics, paired studies, and route validation")


def main() -> None:
    """Parse the archive directory and run checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    validate(args.data)


if __name__ == "__main__":
    main()
