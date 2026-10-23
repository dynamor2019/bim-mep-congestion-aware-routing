"""Separate grid-size and system-count effects in paired adaptive repair."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run_advanced_validation import scaled_instance  # noqa: E402
from run_matched_adaptive_wallclock import (  # noqa: E402
    METHODS,
    adaptive_repair_wallclock,
    exact_mcnemar,
    random_repair_wallclock,
)
from run_routing_experiments import (  # noqa: E402
    Instance,
    estimate_demand,
    objective,
    route_order,
    solution_cost,
)
from routing_revision_solvers import validate_paths  # noqa: E402
from run_revision_benchmark import fingerprint  # noqa: E402

DESIGN = (
    ("grid_base_9", "base", 9),
    ("grid_large_9", "large", 9),
    ("grid_xlarge_9", "xlarge", 9),
    ("count_12_xlarge", "xlarge", 12),
    ("count_15_xlarge", "xlarge", 15),
)


def make_instance(scale: str, systems: int, seed: int) -> Instance:
    """Hold either demand count or grid geometry fixed as specified."""
    generated = scaled_instance(scale, seed)
    if systems > len(generated.commodities):
        raise ValueError(f"{scale} generator supplies fewer than {systems} systems")
    return Instance(generated.shape, generated.blocked,
                    generated.commodities[:systems])


def run_pair(label: str, scale: str, systems: int, seed: int,
             budget_s: float) -> list[dict]:
    """Run both methods on one common scene and initial incumbent."""
    instance = make_instance(scale, systems, seed)
    predicted = estimate_demand(instance)
    order = list(range(systems))
    random.Random(seed).shuffle(order)
    initial = route_order(instance, order, predicted, 0.0)
    validate_paths(instance, initial)
    scene_hash = fingerprint(instance)
    environment_hash = fingerprint(Instance(instance.shape, instance.blocked, []))
    terminal_hash = fingerprint(Instance(instance.shape, set(), instance.commodities))
    terminal_prefix_9 = fingerprint(
        Instance(instance.shape, set(), instance.commodities[:9]))
    terminal_prefix_12 = (fingerprint(
        Instance(instance.shape, set(), instance.commodities[:12]))
        if systems >= 12 else "")
    outcomes = []
    for method in METHODS:
        started = time.perf_counter()
        repair = (random_repair_wallclock if method == METHODS[0]
                  else adaptive_repair_wallclock)
        paths, trace = repair(instance, initial, predicted, seed, budget_s)
        runtime = time.perf_counter() - started
        validate_paths(instance, paths)
        outcomes.append({
            "design_cell": label,
            "seed": seed,
            "scene_hash": scene_hash,
            "environment_hash": environment_hash,
            "terminal_hash": terminal_hash,
            "terminal_prefix_9_hash": terminal_prefix_9,
            "terminal_prefix_12_hash": terminal_prefix_12,
            "method": method,
            "grid": "x".join(map(str, instance.shape)),
            "systems": systems,
            "success": int(len(paths) == systems),
            "routed": len(paths),
            "objective": objective(instance, paths),
            "physical_cost": solution_cost(instance, paths),
            "runtime_s": runtime,
            "budget_s": budget_s,
            "iterations_used": len(trace) - 1,
            "validated": 1,
        })
    return outcomes


def holm_adjust(p_values: list[float]) -> list[float]:
    """Return monotone Holm-adjusted p-values in the input order."""
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [1.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (len(p_values) - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def summarize(rows: list[dict]) -> dict:
    """Summarize paired completions and correct five comparisons."""
    paired = defaultdict(dict)
    for row in rows:
        paired[(row["design_cell"], row["seed"])][row["method"]] = row
    results = []
    for label, _, _ in DESIGN:
        pairs = [pair for (name, _), pair in paired.items() if name == label]
        random_only = sum(pair[METHODS[0]]["success"] > pair[METHODS[1]]["success"]
                          for pair in pairs)
        adaptive_only = sum(pair[METHODS[1]]["success"] > pair[METHODS[0]]["success"]
                            for pair in pairs)
        results.append({
            "design_cell": label,
            "paired_scenes": len(pairs),
            "random_complete": sum(pair[METHODS[0]]["success"] for pair in pairs),
            "adaptive_complete": sum(pair[METHODS[1]]["success"] for pair in pairs),
            "random_only": random_only,
            "adaptive_only": adaptive_only,
            "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
            "random_median_runtime_s": statistics.median(
                pair[METHODS[0]]["runtime_s"] for pair in pairs),
            "adaptive_median_runtime_s": statistics.median(
                pair[METHODS[1]]["runtime_s"] for pair in pairs),
        })
    adjusted = holm_adjust([row["exact_two_sided_mcnemar_p"] for row in results])
    for row, p_value in zip(results, adjusted):
        row["holm_adjusted_p"] = p_value
    return {"design_results": results, "paired_scenes": len(paired),
            "validated_outputs": len(rows)}


def write_archive(output: Path, rows: list[dict], summary: dict,
                  seeds: int, start_seed: int, budget_s: float) -> None:
    """Write raw outcomes, summary, and integrity manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary.update({
        "protocol": "paired repair with grid size and system count varied separately",
        "design": [{"cell": name, "generator_scale": scale, "systems": count}
                   for name, scale, count in DESIGN],
        "seeds_per_cell": seeds,
        "start_seed": start_seed,
        "budget_seconds_per_method": budget_s,
        "methods": list(METHODS),
        "timer_note": "Budget checked between complete iterations; runtime may overrun.",
        "scope_note": "Synthetic factor-separation experiment; no BIM or scaling-law claim.",
        "python": sys.version,
        "platform": platform.platform(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("run_matched_adaptive_wallclock.py", "run_advanced_validation.py",
                         "run_routing_experiments.py", "routing_revision_solvers.py",
                         "run_revision_benchmark.py")
        },
    })
    summary_path = output.with_name(output.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "raw_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "runner_sha256": summary["runner_sha256"],
        "implementation_sha256": summary["implementation_sha256"],
        "outputs": len(rows),
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    """Run and archive the pre-specified five-cell paired design."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=130000)
    parser.add_argument("--budget-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1 or args.budget_seconds <= 0:
        parser.error("--seeds and --budget-seconds must be positive")
    rows = []
    for label, scale, systems in DESIGN:
        for offset in range(args.seeds):
            rows.extend(run_pair(label, scale, systems, args.start_seed + offset,
                                 args.budget_seconds))
            print(f"{label}: {offset + 1}/{args.seeds}", flush=True)
    expected = len(DESIGN) * args.seeds * len(METHODS)
    if len(rows) != expected or not all(row["validated"] for row in rows):
        raise RuntimeError("Incomplete design or failed independent route validation")
    write_archive(args.output, rows, summarize(rows), args.seeds,
                  args.start_seed, args.budget_seconds)
    print(json.dumps({"outputs": len(rows), "path": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
