"""Bounded priority-tree and conflict-control experiments.

This is an auditable PBS-like baseline, not a claim of full PBS/MAPF-LNS
equivalence. The bounded tree branches on failed commodities and swaps their
priority with earlier commodities that occupy the failed route's bottleneck.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run_advanced_validation import adaptive_repair, scaled_instance  # noqa: E402
from run_routing_experiments import (  # noqa: E402
    estimate_demand,
    improve,
    objective,
    route_order,
)


def pbs_like(instance, predicted, seed: int, max_nodes: int = 64):
    """Run bounded priority-tree search with conflict-driven swaps."""
    rng = random.Random(seed)
    root = list(range(len(instance.commodities)))
    rng.shuffle(root)
    queue = [root]
    seen = {tuple(root)}
    best_paths = {}
    best_objective = float("inf")
    expanded = 0
    while queue and expanded < max_nodes:
        order = queue.pop(0)
        expanded += 1
        paths = route_order(instance, order, predicted, 0.0)
        score = objective(instance, paths)
        if score < best_objective:
            best_objective, best_paths = score, paths
        failed = [idx for idx in order if idx not in paths]
        if not failed:
            return paths, expanded
        failed_idx = failed[0]
        failed_pos = order.index(failed_idx)
        # Branch against earlier commodities first; these are the only routes
        # that can have occupied cells when the failed commodity is planned.
        for prior_pos in range(failed_pos - 1, -1, -1):
            candidate = order.copy()
            candidate[prior_pos], candidate[failed_pos] = candidate[failed_pos], candidate[prior_pos]
            key = tuple(candidate)
            if key not in seen:
                seen.add(key)
                queue.append(candidate)
    return best_paths, expanded


def run_case(instance, seed: int, max_nodes: int):
    predicted = estimate_demand(instance)
    started = time.perf_counter()
    pbs_paths, expanded = pbs_like(instance, predicted, seed, max_nodes)
    pbs_time = time.perf_counter() - started
    rng = random.Random(seed)
    order = list(range(len(instance.commodities)))
    rng.shuffle(order)
    base = route_order(instance, order, predicted, 0.0)
    random_paths, _ = improve(instance, base, predicted, False, rng)
    conflict_paths, _ = adaptive_repair(instance, base, predicted, seed, conflict_only=True)
    rows = []
    for method, paths, runtime in (
        ("bounded_pbs_like", pbs_paths, pbs_time),
        ("mspp_random_repair", random_paths, 0.0),
        ("conflict_only", conflict_paths, 0.0),
    ):
        rows.append({
            "method": method,
            "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths),
            "objective": objective(instance, paths),
            "runtime_s": runtime,
            "pbs_nodes": expanded if method == "bounded_pbs_like" else 0,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--max-nodes", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("../results/strong_baselines"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for scale in ("base", "large", "xlarge"):
        for seed in range(args.seeds):
            instance = scaled_instance(scale, seed)
            for row in run_case(instance, seed, args.max_nodes):
                row.update({"scale": scale, "seed": seed, "max_nodes": args.max_nodes})
                rows.append(row)
    with (args.output / "strong_baselines_raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = {"rows": len(rows), "methods": sorted({row["method"] for row in rows}), "note": "Bounded PBS-like priority tree; not a full PBS/MAPF-LNS implementation."}
    (args.output / "strong_baselines_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
