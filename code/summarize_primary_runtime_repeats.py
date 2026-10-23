"""Check repeated timing on the identical 150-scene primary benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
from collections import defaultdict
from pathlib import Path


METHODS = ("fix_order", "pbs_random", "stage1_only", "stage3_only", "proposed")
DENSITIES = ("low", "medium", "high")


def read_run(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    """Load unique method observations and reject malformed inputs."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    keyed = {}
    for row in rows:
        key = (row["density"], row["seed"], row["method"])
        if key in keyed:
            raise ValueError(f"Duplicate observation: {key}")
        if row["method"] not in METHODS or row["density"] not in DENSITIES:
            raise ValueError(f"Unexpected method or density: {key}")
        keyed[key] = row
    if not keyed or len(keyed) != 750:
        raise ValueError(f"Expected 750 observations, found {len(keyed)}")
    return keyed


def exact_mcnemar(random_only: int, other_only: int) -> tuple[float, float]:
    """Return two-sided and other-method-favoring exact McNemar p-values."""
    discordant = random_only + other_only
    if discordant == 0:
        return 1.0, 1.0
    two_sided = min(1.0, 2 * sum(
        math.comb(discordant, k)
        for k in range(min(random_only, other_only) + 1)
    ) / (2 ** discordant))
    other_favoring = sum(
        math.comb(discordant, k)
        for k in range(other_only, discordant + 1)
    ) / (2 ** discordant)
    return two_sided, other_favoring


def bootstrap_mean_ci(values: list[float], seed: int) -> tuple[float, float]:
    """Return percentile 95% CI for a scene-level mean using fixed resampling."""
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    return means[124], means[4874]


def summarize_runs(first: dict, second: dict) -> dict:
    """Verify matched outputs and summarize paired runtime measurements."""
    if set(first) != set(second):
        raise ValueError("Repeated runs do not contain identical method/scene keys")
    for key in first:
        a = {name: value for name, value in first[key].items() if name != "runtime_s"}
        b = {name: value for name, value in second[key].items() if name != "runtime_s"}
        if a != b:
            raise ValueError(f"Non-runtime result changed across runs: {key}")

    results = []
    for density in DENSITIES:
        scene_seeds = sorted({seed for name, seed, _ in first if name == density})
        row = {"density": density, "scenes": len(scene_seeds), "methods": {}, "paired_tests": {}}
        for method in METHODS:
            times = [float(run[(density, seed, method)]["runtime_s"])
                     for run in (first, second) for seed in scene_seeds]
            row["methods"][method] = {
                "successes_per_50": sum(int(first[(density, seed, method)]["success"])
                                         for seed in scene_seeds),
                "mean_runtime_by_run_s": [
                    statistics.mean(float(run[(density, seed, method)]["runtime_s"])
                                    for seed in scene_seeds)
                    for run in (first, second)
                ],
                "median_runtime_across_repeats_s": statistics.median(times),
                "p10_runtime_across_repeats_s": sorted(times)[9],
                "p90_runtime_across_repeats_s": sorted(times)[89],
            }
        for method in ("stage3_only", "proposed"):
            random_only = sum(
                int(first[(density, seed, "pbs_random")]["success"]) == 1
                and int(first[(density, seed, method)]["success"]) == 0
                for seed in scene_seeds
            )
            method_only = sum(
                int(first[(density, seed, "pbs_random")]["success"]) == 0
                and int(first[(density, seed, method)]["success"]) == 1
                for seed in scene_seeds
            )
            p_two, p_method_better = exact_mcnemar(random_only, method_only)
            row["paired_tests"][method] = {
                "random_only": random_only, "method_only": method_only,
                "exact_two_sided_p": p_two, "exact_method_better_one_sided_p": p_method_better,
            }
        baseline, guided = [], []
        for seed in scene_seeds:
            base_time = statistics.mean(float(run[(density, seed, "pbs_random")]["runtime_s"])
                                        for run in (first, second))
            guided_time = statistics.mean(float(run[(density, seed, "stage3_only")]["runtime_s"])
                                          for run in (first, second))
            baseline.append(base_time)
            guided.append((guided_time / base_time) - 1.0)
        low, high = bootstrap_mean_ci(guided, seed=20261024 + len(results))
        row["stage3_runtime_overhead"] = {
            "mean_paired_relative_overhead_pct": 100 * statistics.mean(guided),
            "bootstrap_95_ci_pct": [100 * low, 100 * high],
            "ratio_of_mean_runtimes_pct": 100 * (statistics.mean([
                float(run[(density, seed, "stage3_only")]["runtime_s"])
                for run in (first, second) for seed in scene_seeds
            ]) / statistics.mean([
                float(run[(density, seed, "pbs_random")]["runtime_s"])
                for run in (first, second) for seed in scene_seeds
            ]) - 1.0),
        }
        results.append(row)
    return {
        "protocol": "two executions of identical seeded main-study scenes using the public current solver",
        "observations_per_run": len(first),
        "scene_level_outcomes_identical": True,
        "runtime_note": "Only runtime_s may vary; repeated timings are not additional experimental scenes.",
        "machine": {
            "processor": "Intel Core i7-11700, 8 cores / 16 threads",
            "memory_gb": 64,
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "scale_results": results,
    }


def main() -> None:
    """Write a checksum-bearing timing-repeat summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize_runs(read_run(args.first), read_run(args.second))
    summary["input_sha256"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (args.first, args.second)
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "scenes": 150,
                      "observations_per_run": 750}, indent=2))


if __name__ == "__main__":
    main()
