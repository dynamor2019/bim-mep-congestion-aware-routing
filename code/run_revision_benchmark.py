"""Matched difficult-scene comparison with independently validated outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
import time
from pathlib import Path

from routing_revision_solvers import RoutingContext, SearchBudget, lns, pbs, spatial_cbs, validate_paths
from run_routing_experiments import estimate_demand, generate_instance, objective, solution_cost


def initial_routes(context, seed):
    """Use identical best-of-two priority initialization for all methods."""
    rng = random.Random(seed)
    order = list(range(len(context.instance.commodities)))
    candidates = []
    for _ in range(2):
        rng.shuffle(order)
        candidates.append(context.sequential(order))
    return min(candidates, key=lambda paths: objective(context.instance, paths))


def fingerprint(instance):
    """Hash geometry and terminal attributes to expose accidental mismatches."""
    payload = {"shape": instance.shape, "blocked": sorted(instance.blocked),
               "commodities": [vars(c) for c in instance.commodities]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_scene(scene_seed, cohort, budget, methods):
    """Run all selectors and PBS with a shared valid starting solution."""
    instance = generate_instance("high", scene_seed)
    predicted = estimate_demand(instance)
    started = time.perf_counter()
    initial = initial_routes(RoutingContext(instance, predicted), scene_seed)
    initial_time = time.perf_counter() - started
    validate_paths(instance, initial)
    rows = []
    for method in methods:
        context = RoutingContext(instance, predicted)
        started = time.perf_counter()
        if method == "pbs_static":
            paths, trace, info = pbs(context, initial, budget)
        elif method == "spatial_cbs":
            paths, trace, info = spatial_cbs(context, budget)
        else:
            paths, trace, info = lns(context, initial, method, scene_seed, budget)
        elapsed = time.perf_counter() - started
        validate_paths(instance, paths)
        rows.append({
            "cohort": cohort, "seed": scene_seed, "scene_hash": fingerprint(instance),
            "method": method, "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths), "total": len(instance.commodities),
            "physical_cost": solution_cost(instance, paths),
            "objective": objective(instance, paths), "runtime_s": elapsed,
            "initial_runtime_s": initial_time, "initial_routed": len(initial),
            "initial_objective": objective(instance, initial), "astar_calls": context.calls,
            "status": info["status"], "nodes": info["nodes"],
            "validated": 1, "trace": json.dumps(trace),
        })
    return rows


def main():
    """Write incremental outputs so a long experiment remains auditable."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=100000)
    parser.add_argument("--cohort", default="holdout")
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--nodes", type=int, default=256)
    parser.add_argument("--methods", nargs="+", default=["random", "static_random", "guided", "guided_select_only", "length", "blocker", "conflict", "adaptive", "spatial_mapf_lns2", "pbs_static"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.nodes < 1:
        parser.error("--nodes must be positive")
    budget = SearchBudget(seconds=args.seconds, iterations=args.iterations, nodes=args.nodes)
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {"arguments": vars(args) | {"output": str(args.output)},
                "budget": vars(budget), "python": sys.version, "platform": platform.platform(),
                "timing": "Improvement phase including probes; shared initial planning reported separately. Deadline checked between A* calls; actual elapsed and overshoot recorded.",
                "scope": "Permanent-occupancy PBS/CBS adaptations and LNS selector controls; no temporal MAPF claim."}
    (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with (args.output / "raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = None
        for seed in range(args.start_seed, args.start_seed + args.seeds):
            rows = run_scene(seed, args.cohort, budget, args.methods)
            if writer is None:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            print(f"{args.cohort}: {seed - args.start_seed + 1}/{args.seeds}", flush=True)


if __name__ == "__main__":
    main()
