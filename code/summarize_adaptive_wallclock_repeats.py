"""Summarize repeated wall-clock-capped adaptive repair runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import statistics
from collections import defaultdict
from pathlib import Path

from summarize_adaptive_wallclock import exact_mcnemar, holm_adjust


METHODS = ("mspp_random_repair", "adaptive_multi_operator")
SCALES = ("base", "large", "xlarge")


def read_run(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    """Load one complete, independently validated paired run."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    keyed = {}
    for row in rows:
        if row["validated"] != "1":
            raise ValueError(f"Unvalidated output in {path}")
        key = (row["scale"], row["seed"], row["method"])
        if key in keyed:
            raise ValueError(f"Duplicate method/scene output in {path}: {key}")
        keyed[key] = row
    scenes = {(scale, seed) for scale, seed, _ in keyed}
    expected = {(scale, seed, method) for scale, seed in scenes for method in METHODS}
    if not scenes or set(keyed) != expected:
        raise ValueError(f"Incomplete paired run: {path}")
    return keyed


def percentile(values: list[float], fraction: float) -> float:
    """Return a deterministic nearest-rank percentile."""
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def summarize_repeats(paths: list[Path]) -> dict:
    """Summarize repeated outcomes without treating repeats as new scenes."""
    if len(paths) < 2:
        raise ValueError("At least two repeated runs are required")
    runs = [read_run(path) for path in paths]
    keys = set(runs[0])
    if any(set(run) != keys for run in runs[1:]):
        raise ValueError("Repeated runs must use identical scale/seed/method keys")
    for key in keys:
        scene_hashes = {run[key]["scene_hash"] for run in runs}
        if len(scene_hashes) != 1:
            raise ValueError(f"Scene hash changed across repeats: {key[:2]}")

    scale_results = []
    present_scales = [scale for scale in SCALES if any(key[0] == scale for key in keys)]
    for scale in present_scales:
        per_run = []
        for run_index, run in enumerate(runs, start=1):
            pairs = defaultdict(dict)
            for (name, seed, method), row in run.items():
                if name == scale:
                    pairs[seed][method] = row
            random_only = sum(int(pair[METHODS[0]]["success"]) == 1
                              and int(pair[METHODS[1]]["success"]) == 0
                              for pair in pairs.values())
            adaptive_only = sum(int(pair[METHODS[0]]["success"]) == 0
                                and int(pair[METHODS[1]]["success"]) == 1
                                for pair in pairs.values())
            per_run.append({
                "run": run_index,
                "paired_scenes": len(pairs),
                "random_complete": sum(int(p[METHODS[0]]["success"]) for p in pairs.values()),
                "adaptive_complete": sum(int(p[METHODS[1]]["success"]) for p in pairs.values()),
                "random_only": random_only,
                "adaptive_only": adaptive_only,
                "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
            })

        timing = {}
        for method in METHODS:
            values = [float(run[key]["runtime_s"]) for run in runs for key in keys
                      if key[0] == scale and key[2] == method]
            timing[method] = {
                "median_s": statistics.median(values),
                "p10_s": percentile(values, 0.10),
                "p90_s": percentile(values, 0.90),
                "min_s": min(values),
                "max_s": max(values),
            }
        scale_results.append({"scale": scale, "per_run": per_run, "runtime_across_repeats": timing})

    outcome_switches = {}
    for method in METHODS:
        outcome_switches[method] = sum(
            len({int(run[key]["success"]) for run in runs}) > 1
            for key in keys if key[2] == method
        )
    return {
        "protocol": "three executions of the same seeded 90-scene wall-clock-capped cohort",
        "repeat_runs": [str(path) for path in paths],
        "repeat_count": len(runs),
        "unique_paired_scenes": len({(scale, seed) for scale, seed, _ in keys}),
        "validated_outputs_per_run": len(keys),
        "outcome_switches_across_repeats": outcome_switches,
        "scale_results": scale_results,
        "inference_note": "Repeated executions are timing/reproducibility checks, not independent scenes; do not pool them for inferential tests.",
        "timing_note": "The nominal 1-s cap is checked between complete iterations and can be exceeded by a final iteration.",
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def main() -> None:
    """Write a repeated-run summary and source-data hashes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path, nargs="+", help="Repeated raw CSV runs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize_repeats(args.inputs)
    result["input_sha256"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in args.inputs
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "repeats": len(args.inputs),
                      "unique_scenes": result["unique_paired_scenes"]}, indent=2))


if __name__ == "__main__":
    main()
