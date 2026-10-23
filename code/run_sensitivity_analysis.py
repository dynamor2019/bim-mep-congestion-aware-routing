"""Sensitivity and robust-statistics extension for the routing study."""

from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import binomtest

from run_routing_experiments import (
    estimate_demand,
    generate_instance,
    improve,
    manhattan,
    objective,
    route_order,
)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Return Wilson score interval for a binomial proportion."""
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    return center - margin, center + margin


def initial_routes(instance, seed: int, weight: float):
    """Return best of two priority orders under one congestion weight."""
    rng = random.Random(seed)
    demand = estimate_demand(instance)
    indices = list(range(len(instance.commodities)))
    candidates = []
    for _ in range(2):
        rng.shuffle(indices)
        candidates.append(route_order(instance, list(indices), demand, weight))
    return min(candidates, key=lambda paths: objective(instance, paths)), demand


def run(output_dir: Path, seeds: int = 15) -> None:
    """Execute parameter sweeps and exact paired success tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    weights = (0.0, 0.5, 1.0, 2.0, 4.0)
    fractions = (0.15, 0.25, 0.40)
    iterations = (2, 5, 10)
    densities = ("low", "medium", "high")
    for density_index, density in enumerate(densities):
        for seed in range(seeds):
            instance = generate_instance(density, 10000 * density_index + seed)
            lower_bound = sum(manhattan(item.start, item.goal) for item in instance.commodities)
            for weight in weights:
                paths, _ = initial_routes(instance, seed, weight)
                rows.append({"analysis": "weight", "density": density, "seed": seed, "parameter": weight,
                             "success": int(len(paths) == len(instance.commodities)),
                             "normalized_cost": objective(instance, paths) / lower_bound})
            baseline, demand = initial_routes(instance, seed, 0.0)
            for fraction in fractions:
                paths, _ = improve(instance, baseline, demand, True, random.Random(seed),
                                   iterations=5, destroy_fraction=fraction, congestion_weight=2.0)
                rows.append({"analysis": "fraction", "density": density, "seed": seed, "parameter": fraction,
                             "success": int(len(paths) == len(instance.commodities)),
                             "normalized_cost": objective(instance, paths) / lower_bound})
            for budget in iterations:
                paths, _ = improve(instance, baseline, demand, True, random.Random(seed),
                                   iterations=budget, destroy_fraction=0.25, congestion_weight=2.0)
                rows.append({"analysis": "iterations", "density": density, "seed": seed, "parameter": budget,
                             "success": int(len(paths) == len(instance.commodities)),
                             "normalized_cost": objective(instance, paths) / lower_bound})

    with (output_dir / "sensitivity_raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for analysis in ("weight", "fraction", "iterations"):
        parameters = sorted({float(row["parameter"]) for row in rows if row["analysis"] == analysis})
        for density in densities:
            for parameter in parameters:
                subset = [row for row in rows if row["analysis"] == analysis and row["density"] == density
                          and float(row["parameter"]) == parameter]
                successes = sum(int(row["success"]) for row in subset)
                low, high = wilson_interval(successes, len(subset))
                summary.append({"analysis": analysis, "density": density, "parameter": parameter,
                                "success_rate": successes / len(subset), "wilson_low": low, "wilson_high": high,
                                "normalized_cost_mean": float(np.mean([row["normalized_cost"] for row in subset]))})

    with (output_dir / "sensitivity_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    main_rows = list(csv.DictReader((output_dir / "raw_results.csv").open(encoding="utf-8")))
    exact_tests = {}
    for density in densities:
        base = {int(row["seed"]): int(row["success"]) for row in main_rows
                if row["density"] == density and row["method"] == "pbs_random"}
        guided = {int(row["seed"]): int(row["success"]) for row in main_rows
                  if row["density"] == density and row["method"] == "stage3_only"}
        better = sum(guided[seed] > base[seed] for seed in base)
        worse = sum(guided[seed] < base[seed] for seed in base)
        discordant = better + worse
        p_value = binomtest(better, discordant, 0.5, alternative="greater").pvalue if discordant else 1.0
        exact_tests[density] = {"guided_better": better, "guided_worse": worse,
                                "discordant_pairs": discordant, "exact_mcnemar_one_sided_p": p_value}
    (output_dir / "robust_statistics.json").write_text(json.dumps(exact_tests, indent=2), encoding="utf-8")

    figure, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    for axis, analysis in zip(axes, ("weight", "fraction", "iterations")):
        for density in densities:
            subset = [row for row in summary if row["analysis"] == analysis and row["density"] == density]
            axis.plot([row["parameter"] for row in subset], [row["normalized_cost_mean"] for row in subset],
                      marker="o", label=density)
        axis.set_title(analysis.capitalize())
        axis.set_xlabel("Parameter value")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Mean normalized penalized cost")
    axes[-1].legend(frameon=False)
    figure.tight_layout()
    figure.savefig(output_dir / "figure4_sensitivity.png", dpi=220)
    plt.close(figure)


if __name__ == "__main__":
    run(Path("results"))
