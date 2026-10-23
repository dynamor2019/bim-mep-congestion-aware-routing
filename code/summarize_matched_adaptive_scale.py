"""Summarize paired adaptive-repair scale outcomes with exact McNemar tests."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def exact_mcnemar(random_only: int, adaptive_only: int) -> float:
    """Return the exact two-sided binomial McNemar p-value."""
    discordant = random_only + adaptive_only
    if discordant == 0:
        return 1.0
    lower_tail = sum(math.comb(discordant, value)
                     for value in range(min(random_only, adaptive_only) + 1))
    return min(1.0, 2.0 * lower_tail / (2 ** discordant))


def summarize_scale(scale: str, pairs: dict, methods: set[str]) -> dict:
    """Summarize completion, runtime, and discordances for one scale."""
    selected = [pair for (name, _), pair in pairs.items() if name == scale]
    random_only = sum(int(pair["mspp_random_repair"]["success"]) == 1
                      and int(pair["adaptive_multi_operator"]["success"]) == 0
                      for pair in selected)
    adaptive_only = sum(int(pair["mspp_random_repair"]["success"]) == 0
                        and int(pair["adaptive_multi_operator"]["success"]) == 1
                        for pair in selected)
    method_stats = {}
    for method in sorted(methods):
        method_rows = [pair[method] for pair in selected]
        method_stats[method] = {
            "complete_scenes": sum(int(row["success"]) for row in method_rows),
            "scenes": len(method_rows),
            "mean_routed_systems": statistics.mean(
                int(row["routed"]) for row in method_rows),
            "median_runtime_s": statistics.median(
                float(row["runtime_s"]) for row in method_rows),
        }
    return {
        "scale": scale,
        "systems": int(selected[0]["adaptive_multi_operator"]["systems"]),
        "paired_scenes": len(selected),
        "random_only_successes": random_only,
        "adaptive_only_successes": adaptive_only,
        "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
        "methods": method_stats,
    }


def summarize(input_path: Path) -> dict:
    """Summarize validated paired outcomes by scale and method."""
    rows = list(csv.DictReader(input_path.open(encoding="utf-8", newline="")))
    pairs = defaultdict(dict)
    for row in rows:
        pairs[(row["scale"], row["seed"])][row["method"]] = row
    expected_methods = {"mspp_random_repair", "adaptive_multi_operator"}
    if not pairs or any(set(pair) != expected_methods for pair in pairs.values()):
        raise ValueError("Input must contain one complete pair per scene")
    if any(row["validated"] != "1" for row in rows):
        raise ValueError("Input contains an unvalidated route output")
    if any(len({row["scene_hash"] for row in pair.values()}) != 1
           for pair in pairs.values()):
        raise ValueError("Paired methods do not share scene hashes")
    scales = sorted({scale for scale, _ in pairs})
    results = [summarize_scale(scale, pairs, expected_methods) for scale in scales]
    return {
        "protocol": "equal 8 iterations, same generated scene and shared initial route",
        "total_pairs": len(pairs),
        "validated_outputs": len(rows),
        "scale_results": results,
        "interpretation_boundary": (
            "Equal iterations are not equal wall-clock time. All scenes are synthetic; "
            "grid dimensions increase with system count, so scale effects are not isolated."
        ),
    }


def main() -> None:
    """Write a machine-readable paired summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
