"""Combine compatible permanent-space baseline runs into one paired archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


METHODS = {
    "cbs": {"random", "spatial_cbs"},
    "pbs": {"random", "pbs_static"},
    "lns": {"spatial_mapf_lns2"},
}


def sha256(path: Path) -> str:
    """Return the file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def budget_signature(manifest: dict) -> dict:
    """Normalize omitted historical defaults while retaining all budget fields."""
    budget = dict(manifest["budget"])
    budget.setdefault("fraction", 0.25)
    return budget


def load_archive(folder: Path, expected: set[str]) -> tuple[dict, dict[str, dict[str, dict]]]:
    """Load and validate one archive's methods, seeds, and route checks."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    grouped: dict[str, dict[str, dict]] = {}
    with (folder / "raw.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["method"] not in expected or row["validated"] != "1":
                raise ValueError(f"Unexpected method or invalid route in {folder}")
            seed_rows = grouped.setdefault(row["method"], {})
            if row["seed"] in seed_rows:
                raise ValueError(f"Duplicate seed {row['seed']} in {folder}")
            seed_rows[row["seed"]] = row
    if set(grouped) != expected:
        raise ValueError(f"Expected methods {sorted(expected)} in {folder}")
    return manifest, grouped


def merge_archives(cbs_dir: Path, pbs_dir: Path, lns_dir: Path) -> tuple[list[dict], dict]:
    """Merge shared-seed CBS, PBS, and LNS archives after strict checks."""
    folders = {"cbs": cbs_dir, "pbs": pbs_dir, "lns": lns_dir}
    loaded = {key: load_archive(folder, METHODS[key]) for key, folder in folders.items()}
    manifests = {key: item[0] for key, item in loaded.items()}
    groups = {key: item[1] for key, item in loaded.items()}
    budgets = {key: budget_signature(manifest) for key, manifest in manifests.items()}
    if len({json.dumps(value, sort_keys=True) for value in budgets.values()}) != 1:
        raise ValueError("Baseline budgets differ")
    reference = groups["cbs"]["random"]
    seeds = set(reference)
    if any(set(method_rows) != seeds for cohort in groups.values() for method_rows in cohort.values()):
        raise ValueError("Baseline seed sets differ")
    for cohort, method_rows in groups.items():
        for method, rows in method_rows.items():
            for seed in seeds:
                expected = reference[seed]
                actual = rows[seed]
                if (actual["scene_hash"] != expected["scene_hash"]
                        or actual["initial_objective"] != expected["initial_objective"]):
                    raise ValueError(f"Scene/incumbent mismatch: {cohort}/{method}/{seed}")
    for seed in seeds:
        pbs_random = groups["pbs"]["random"][seed]
        for field in ("success", "routed", "objective"):
            if pbs_random[field] != reference[seed][field]:
                raise ValueError(f"Random baseline changed between runs at seed {seed}")
    merged = [reference[seed] for seed in sorted(seeds, key=int)]
    merged.extend(groups["cbs"]["spatial_cbs"][seed] for seed in sorted(seeds, key=int))
    merged.extend(groups["pbs"]["pbs_static"][seed] for seed in sorted(seeds, key=int))
    merged.extend(groups["lns"]["spatial_mapf_lns2"][seed] for seed in sorted(seeds, key=int))
    provenance = {
        "scene_count": len(seeds),
        "methods": ["random", "spatial_cbs", "pbs_static", "spatial_mapf_lns2"],
        "outputs": len(merged),
        "common_budget": next(iter(budgets.values())),
        "same_scenes_and_initial_objectives": True,
        "sources": {
            key: {
                "path": folder.as_posix(),
                "raw_sha256": sha256(folder / "raw.csv"),
                "manifest_sha256": sha256(folder / "manifest.json"),
            }
            for key, folder in folders.items()
        },
        "scope": "Permanent-occupancy adaptations; not faithful temporal MAPF baselines.",
    }
    return merged, provenance


def write_archive(output: Path, rows: list[dict], provenance: dict) -> None:
    """Write paired observations and their integrity manifest."""
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    provenance["raw_sha256"] = sha256(raw_path)
    (output / "manifest.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Validate and merge the matched permanent-space baseline archives."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cbs", type=Path, required=True)
    parser.add_argument("--pbs", type=Path, required=True)
    parser.add_argument("--lns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, provenance = merge_archives(args.cbs, args.pbs, args.lns)
    write_archive(args.output, rows, provenance)
    print(json.dumps({"scene_count": provenance["scene_count"],
                      "methods": provenance["methods"], "outputs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
