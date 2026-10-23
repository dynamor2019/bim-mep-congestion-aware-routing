"""Summarize paired wall-clock adaptive repair results with Holm adjustment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


METHODS = ("mspp_random_repair", "adaptive_multi_operator")
SCALES = ("base", "large", "xlarge")


def exact_mcnemar(random_only: int, adaptive_only: int) -> float:
    """Return the exact two-sided McNemar p-value."""
    discordant = random_only + adaptive_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value)
               for value in range(min(random_only, adaptive_only) + 1))
    return min(1.0, 2.0 * tail / (2 ** discordant))


def holm_adjust(p_values: list[float]) -> list[float]:
    """Return Holm-adjusted p-values in their original order."""
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [1.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def summarize(rows: list[dict[str, str]]) -> dict:
    """Summarize paired successes, time, iterations, and paired tests."""
    pairs = defaultdict(dict)
    for row in rows:
        if row["validated"] != "1":
            raise ValueError("All routes must pass independent validation")
        pairs[(row["scale"], row["seed"])][row["method"]] = row
    if not pairs or any(set(pair) != set(METHODS) for pair in pairs.values()):
        raise ValueError("Each scene must have one output from both repair methods")
    results = []
    for scale in SCALES:
        selected = [pair for (name, _), pair in pairs.items() if name == scale]
        if not selected:
            continue
        random_only = sum(int(pair[METHODS[0]]["success"]) == 1
                          and int(pair[METHODS[1]]["success"]) == 0 for pair in selected)
        adaptive_only = sum(int(pair[METHODS[0]]["success"]) == 0
                            and int(pair[METHODS[1]]["success"]) == 1 for pair in selected)
        methods = {}
        for method in METHODS:
            method_rows = [pair[method] for pair in selected]
            methods[method] = {
                "complete_scenes": sum(int(row["success"]) for row in method_rows),
                "scenes": len(method_rows),
                "median_runtime_s": statistics.median(float(row["runtime_s"])
                                                       for row in method_rows),
                "median_iterations": statistics.median(int(row["iterations_used"])
                                                        for row in method_rows),
            }
        results.append({
            "scale": scale,
            "paired_scenes": len(selected),
            "random_only_successes": random_only,
            "adaptive_only_successes": adaptive_only,
            "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
            "methods": methods,
        })
    adjusted = holm_adjust([row["exact_two_sided_mcnemar_p"] for row in results])
    for result, value in zip(results, adjusted):
        result["holm_adjusted_p_across_three_scales"] = value
    return {
        "protocol": "same scene and initial routes; 1-s repair budget cap per method",
        "paired_scenes": len(pairs),
        "validated_outputs": len(rows),
        "budget_seconds_per_method": float(rows[0]["budget_s"]),
        "scale_results": results,
        "wallclock_note": (
            "The cap is checked between full repair iterations; observed runtime can overshoot "
            "by one iteration, so this is not exact equal-CPU-time matching."
        ),
        "scope_note": "Exploratory synthetic evidence; scale and systems count co-vary.",
    }


def main() -> None:
    """Write summary and checksum manifest for an existing raw archive."""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-source", type=Path, required=True)
    parser.add_argument("--implementation-source", type=Path, nargs=2, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = summarize(rows)
    seeds_by_scale = {
        scale: sorted({int(row["seed"]) for row in rows if row["scale"] == scale})
        for scale in SCALES
    }
    nonempty = [seeds for seeds in seeds_by_scale.values() if seeds]
    if not nonempty or any(len(seeds) != len(nonempty[0]) for seeds in nonempty):
        raise ValueError("Each represented scale must contain the same number of paired seeds")
    summary["seeds_per_scale"] = len(nonempty[0])
    summary["start_seed"] = min(seed for seeds in nonempty for seed in seeds)
    summary["source_sha256"] = hashlib.sha256(args.run_source.read_bytes()).hexdigest()
    summary["implementation_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in args.implementation_source
    }
    summary["summary_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary["raw_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "raw_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "outputs": len(rows),
        "all_validated": all(row["validated"] == "1" for row in rows),
        "run_source_sha256": summary["source_sha256"],
        "implementation_sha256": summary["implementation_sha256"],
        "summary_script_sha256": summary["summary_script_sha256"],
    }
    args.input.with_suffix(args.input.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps({"summary": str(args.output), "outputs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
