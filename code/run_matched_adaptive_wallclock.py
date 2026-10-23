"""Compare adaptive and random repair under paired wall-clock budgets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run_advanced_validation import conflict_scores, scaled_instance  # noqa: E402
from run_routing_experiments import (  # noqa: E402
    astar,
    estimate_demand,
    objective,
    route_order,
    solution_cost,
)
from routing_revision_solvers import validate_paths  # noqa: E402
from run_revision_benchmark import fingerprint  # noqa: E402


SCALES = ("base", "large", "xlarge")
METHODS = ("mspp_random_repair", "adaptive_multi_operator")
ITERATION_CAP = 100_000


def random_repair_wallclock(instance, initial, predicted, seed, budget_s):
    """Apply random neighborhoods until the wall-clock budget is reached."""
    paths = dict(initial)
    trace = [objective(instance, paths)]
    rng = random.Random(seed)
    started = time.perf_counter()
    for _ in range(ITERATION_CAP):
        if time.perf_counter() - started >= budget_s:
            break
        route_demand = defaultdict(int)
        for path in paths.values():
            for node in path:
                route_demand[node] += 1
        scores = {}
        for index, item in enumerate(instance.commodities):
            path = paths.get(index, [])
            scores[index] = sum(predicted.get(node, 0.0) + route_demand[node]
                                for node in path) + (1000.0 if index not in paths else 0.0)
        count = max(2, math.ceil(len(instance.commodities) * 0.25))
        selected = rng.sample(range(len(instance.commodities)), count)
        candidate = {i: path for i, path in paths.items() if i not in selected}
        occupied = {node for path in candidate.values() for node in path[1:-1]}
        terminals = {point for item in instance.commodities for point in (item.start, item.goal)}
        for index in sorted(selected, key=lambda i: scores[i], reverse=True):
            item = instance.commodities[index]
            path = astar(instance, item, occupied | (terminals - {item.start, item.goal}),
                         predicted, 0.0)
            if path is not None:
                candidate[index] = path
                occupied.update(path[1:-1])
        if objective(instance, candidate) <= objective(instance, paths):
            paths = candidate
        trace.append(objective(instance, paths))
    return paths, trace


def adaptive_repair_wallclock(instance, initial, predicted, seed, budget_s):
    """Apply reward-weighted conflict, longest, and random neighborhoods."""
    rng = random.Random(seed)
    paths = dict(initial)
    terminals = {point for item in instance.commodities for point in (item.start, item.goal)}
    trace = [objective(instance, paths)]
    operators = ("conflict", "longest", "random")
    rewards = {name: 1.0 for name in operators}
    started = time.perf_counter()
    for _ in range(ITERATION_CAP):
        if time.perf_counter() - started >= budget_s:
            break
        scores = conflict_scores(paths, predicted)
        operator = rng.choices(operators, weights=[rewards[name] for name in operators], k=1)[0]
        count = max(2, math.ceil(len(instance.commodities)
                                 * (0.20 if trace[-1] < 10000 else 0.40)))
        if operator == "conflict":
            selected = sorted(scores, key=scores.get, reverse=True)[:count]
        elif operator == "longest":
            selected = sorted(paths, key=lambda i: len(paths[i]), reverse=True)[:count]
            selected += [i for i in range(len(instance.commodities)) if i not in selected][
                :max(0, count - len(selected))]
        else:
            selected = rng.sample(range(len(instance.commodities)), count)
        kept = {i: path for i, path in paths.items() if i not in selected}
        occupied = {node for path in kept.values() for node in path[1:-1]}
        candidate = dict(kept)
        for index in sorted(selected, key=lambda i: scores.get(i, 1000.0), reverse=True):
            item = instance.commodities[index]
            path = astar(instance, item, occupied | (terminals - {item.start, item.goal}),
                         predicted, 2.0)
            if path:
                candidate[index] = path
                occupied.update(path[1:-1])
        before = objective(instance, paths)
        if objective(instance, candidate) <= before:
            paths = candidate
            rewards[operator] += 1.0
        else:
            rewards[operator] = max(0.25, rewards[operator] * 0.85)
        trace.append(objective(instance, paths))
    return paths, trace


def run_scene(scale: str, seed: int, budget_s: float) -> list[dict]:
    """Run both repair methods on one shared generated scene and incumbent."""
    instance = scaled_instance(scale, seed)
    predicted = estimate_demand(instance)
    order = list(range(len(instance.commodities)))
    random.Random(seed).shuffle(order)
    initial = route_order(instance, order, predicted, 0.0)
    validate_paths(instance, initial)
    scene_hash = fingerprint(instance)
    method_order = list(METHODS)
    random.Random(seed ^ 0x5A17).shuffle(method_order)
    outputs = {}
    for method in method_order:
        started = time.perf_counter()
        if method == "mspp_random_repair":
            paths, trace = random_repair_wallclock(instance, initial, predicted, seed, budget_s)
        else:
            paths, trace = adaptive_repair_wallclock(instance, initial, predicted, seed, budget_s)
        runtime = time.perf_counter() - started
        validate_paths(instance, paths)
        outputs[method] = {
            "scale": scale,
            "seed": seed,
            "scene_hash": scene_hash,
            "method": method,
            "systems": len(instance.commodities),
            "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths),
            "total": len(instance.commodities),
            "objective": objective(instance, paths),
            "physical_cost": solution_cost(instance, paths),
            "runtime_s": runtime,
            "budget_s": budget_s,
            "iterations_used": len(trace) - 1,
            "validated": 1,
        }
    return [outputs[method] for method in METHODS]


def exact_mcnemar(random_only: int, adaptive_only: int) -> float:
    """Return the two-sided exact McNemar p-value."""
    discordant = random_only + adaptive_only
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, k)
               for k in range(min(random_only, adaptive_only) + 1))
    return min(1.0, 2.0 * tail / (2 ** discordant))


def summarize(rows: list[dict]) -> dict:
    """Summarize paired outcomes, runtimes, and iteration counts by scale."""
    pairs = defaultdict(dict)
    for row in rows:
        pairs[(row["scale"], row["seed"])][row["method"]] = row
    results = []
    for scale in SCALES:
        selected = [pair for (name, _), pair in pairs.items() if name == scale]
        random_only = sum(pair[METHODS[0]]["success"] > pair[METHODS[1]]["success"]
                          for pair in selected)
        adaptive_only = sum(pair[METHODS[1]]["success"] > pair[METHODS[0]]["success"]
                            for pair in selected)
        method_stats = {}
        for method in METHODS:
            method_rows = [pair[method] for pair in selected]
            method_stats[method] = {
                "complete_scenes": sum(row["success"] for row in method_rows),
                "scenes": len(method_rows),
                "median_runtime_s": statistics.median(row["runtime_s"] for row in method_rows),
                "median_iterations": statistics.median(row["iterations_used"] for row in method_rows),
            }
        results.append({
            "scale": scale,
            "paired_scenes": len(selected),
            "random_only_successes": random_only,
            "adaptive_only_successes": adaptive_only,
            "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
            "methods": method_stats,
        })
    return {"scale_results": results, "paired_scenes": len(pairs), "validated_outputs": len(rows)}


def main() -> None:
    """Run the paired experiment and archive raw and summarized results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=110000)
    parser.add_argument("--budget-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1 or args.budget_seconds <= 0:
        parser.error("--seeds and --budget-seconds must be positive")
    rows = []
    for scale in SCALES:
        for offset in range(args.seeds):
            rows.extend(run_scene(scale, args.start_seed + offset, args.budget_seconds))
            print(f"{scale}: {offset + 1}/{args.seeds}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    summary.update({
        "protocol": "same scene and incumbent; equal wall-clock repair cap per method",
        "budget_seconds_per_method": args.budget_seconds,
        "seeds_per_scale": args.seeds,
        "start_seed": args.start_seed,
        "scales": list(SCALES),
        "methods": list(METHODS),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("run_routing_experiments.py", "run_advanced_validation.py")
        },
        "python": sys.version,
        "platform": platform.platform(),
        "wallclock_note": "Budget checked between complete repair iterations; observed runtimes may exceed the cap by one iteration.",
        "scope_note": "Synthetic generated cases; exploratory compute-matched repair comparison, not a general scaling claim.",
    })
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "raw_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "outputs": len(rows),
        "all_validated": all(row["validated"] == 1 for row in rows),
    }
    args.output.with_suffix(args.output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps({"raw": str(args.output), "summary": str(summary_path),
                      "outputs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
