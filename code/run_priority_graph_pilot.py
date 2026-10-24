"""Run a reproducible pilot of permanent-space priority-graph search."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

from permanent_priority_search import permanent_priority_search
from run_advanced_validation import scaled_instance
from run_routing_experiments import objective, solve


def scene_hash(instance) -> str:
    """Hash canonical instance data for paired-run verification."""
    payload = {
        "shape": instance.shape,
        "blocked": sorted(instance.blocked),
        "commodities": [
            [item.start, item.goal, item.discipline, item.bend_cost, item.vertical_cost]
            for item in instance.commodities
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_paths(instance, paths) -> bool:
    """Check endpoint, adjacency, obstacle, terminal, and vertex constraints."""
    terminals = {
        point
        for item in instance.commodities
        for point in (item.start, item.goal)
    }
    occupied = set()
    for index, path in paths.items():
        item = instance.commodities[index]
        if not path or path[0] != item.start or path[-1] != item.goal:
            return False
        for point in path:
            if point in instance.blocked or any(
                value < 0 or value >= limit
                for value, limit in zip(point, instance.shape)
            ):
                return False
        if any(sum(abs(a - b) for a, b in zip(left, right)) != 1 for left, right in zip(path, path[1:])):
            return False
        if item.discipline == "drainage" and any(
            right[2] > left[2] for left, right in zip(path, path[1:])
        ):
            return False
        if any(point in terminals - {item.start, item.goal} for point in path):
            return False
        internal = set(path[1:-1])
        if internal & occupied:
            return False
        occupied.update(internal)
    return True


def exact_mcnemar_p(wins: int, losses: int) -> float:
    """Return a two-sided exact McNemar p-value from discordant pairs."""
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def summarize_rows(rows: list[dict], first_seed: int, max_nodes: int) -> dict:
    """Summarize paired completion and routed-count outcomes separately."""
    paired = {}
    for row in rows:
        paired.setdefault(row["seed"], {})[row["method"]] = row
    methods = ("mspp_random_repair", "permanent_priority_graph")
    routed_more = routed_fewer = routed_ties = 0
    completion_wins = completion_losses = completion_ties = 0
    for pair in paired.values():
        baseline, candidate = (pair[name] for name in methods)
        routed_delta = int(candidate["routed"]) - int(baseline["routed"])
        routed_more += routed_delta > 0
        routed_fewer += routed_delta < 0
        routed_ties += routed_delta == 0
        completion_delta = int(candidate["success"]) - int(baseline["success"])
        completion_wins += completion_delta > 0
        completion_losses += completion_delta < 0
        completion_ties += completion_delta == 0
    return {
        "scenes": len(paired),
        "rows": len(rows),
        "seed_range": [first_seed, first_seed + len(paired) - 1],
        "methods": list(methods),
        "priority_node_cap": max_nodes,
        "completion_counts": {
            name: sum(int(row["success"]) for row in rows if row["method"] == name)
            for name in methods
        },
        "paired_completion_wins": completion_wins,
        "paired_completion_losses": completion_losses,
        "paired_completion_ties": completion_ties,
        "completion_mcnemar_exact_two_sided_p": exact_mcnemar_p(
            completion_wins, completion_losses
        ),
        "paired_routed_count_more": routed_more,
        "paired_routed_count_fewer": routed_fewer,
        "paired_routed_count_ties": routed_ties,
        "all_outputs_independently_validated": all(int(row["validated"]) for row in rows),
        "interpretation": "Exploratory synthetic cohort; permanent-space priority-graph adaptation, not canonical temporal MAPF-PBS.",
        "raw_csv": "priority_graph_pilot_raw.csv",
    }


def _random_restarts(instance, seed: int, time_budget_s: float):
    """Spend a wall-clock budget on repeated random-repair trials."""
    started = time.perf_counter()
    deadline = started + time_budget_s
    best_paths = {}
    attempts = 0
    while attempts == 0 or time.perf_counter() < deadline:
        candidate, _, _ = solve(
            instance, "pbs_random", seed + attempts, deadline=deadline
        )
        attempts += 1
        if objective(instance, candidate) < objective(instance, best_paths):
            best_paths = candidate
        if len(best_paths) == len(instance.commodities):
            break
    return best_paths, time.perf_counter() - started, attempts


def run_budget_matched(
    seed_count: int, first_seed: int, time_budget_s: float, output: Path
) -> dict:
    """Compare random restarts and priority search under equal time caps."""
    rows = []
    for seed in range(first_seed, first_seed + seed_count):
        instance = scaled_instance("base", seed)
        digest = scene_hash(instance)
        baseline, baseline_seconds, attempts = _random_restarts(
            instance, seed, time_budget_s
        )
        started = time.perf_counter()
        candidate, expanded, _ = permanent_priority_search(
            instance, seed, max_nodes=10000, time_budget_s=time_budget_s
        )
        candidate_seconds = time.perf_counter() - started
        outcomes = (
            ("mspp_random_restarts", baseline, baseline_seconds, attempts),
            ("permanent_priority_search", candidate, candidate_seconds, expanded),
        )
        for method, paths, elapsed, work in outcomes:
            rows.append({
                "seed": seed,
                "scene_hash": digest,
                "method": method,
                "success": int(len(paths) == len(instance.commodities)),
                "routed": len(paths),
                "total": len(instance.commodities),
                "objective": objective(instance, paths),
                "runtime_s": elapsed,
                "work_units": work,
                "validated": int(validate_paths(instance, paths)),
            })

    output.mkdir(parents=True, exist_ok=True)
    with (output / "priority_graph_budget_matched_raw.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = _summarize_budget_rows(rows, first_seed, time_budget_s)
    (output / "priority_graph_budget_matched_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _summarize_budget_rows(rows: list[dict], first_seed: int, budget_s: float) -> dict:
    """Summarize paired completion and observed wall-clock use."""
    pairs = {}
    for row in rows:
        pairs.setdefault(row["seed"], {})[row["method"]] = row
    methods = ("mspp_random_restarts", "permanent_priority_search")
    wins = losses = 0
    for pair in pairs.values():
        delta = int(pair[methods[1]]["success"]) - int(pair[methods[0]]["success"])
        wins += delta > 0
        losses += delta < 0
    return {
        "scenes": len(pairs),
        "rows": len(rows),
        "seed_range": [first_seed, first_seed + len(pairs) - 1],
        "methods": list(methods),
        "per_scene_wallclock_cap_s": budget_s,
        "completion_counts": {
            method: sum(int(row["success"]) for row in rows if row["method"] == method)
            for method in methods
        },
        "paired_candidate_wins": wins,
        "paired_candidate_losses": losses,
        "completion_mcnemar_exact_two_sided_p": exact_mcnemar_p(wins, losses),
        "mean_runtime_s": {
            method: sum(float(row["runtime_s"]) for row in rows if row["method"] == method)
            / len(pairs)
            for method in methods
        },
        "maximum_runtime_s": {
            method: max(float(row["runtime_s"]) for row in rows if row["method"] == method)
            for method in methods
        },
        "all_outputs_independently_validated": all(int(row["validated"]) for row in rows),
        "interpretation": "Exploratory permanent-space comparison with equal per-scene wall-clock caps; not canonical temporal MAPF-PBS.",
        "raw_csv": "priority_graph_budget_matched_raw.csv",
    }


def run(seed_count: int, first_seed: int, max_nodes: int, output: Path) -> dict:
    """Run paired random-repair and priority-graph outcomes on shared scenes."""
    rows = []
    for seed in range(first_seed, first_seed + seed_count):
        instance = scaled_instance("base", seed)
        digest = scene_hash(instance)

        baseline_paths, _, baseline_seconds = solve(instance, "pbs_random", seed)
        priority_started = time.perf_counter()
        priority_paths, expanded, _ = permanent_priority_search(
            instance, seed, max_nodes=max_nodes
        )
        priority_seconds = time.perf_counter() - priority_started
        for method, paths, elapsed, nodes in (
            ("mspp_random_repair", baseline_paths, baseline_seconds, 0),
            ("permanent_priority_graph", priority_paths, priority_seconds, expanded),
        ):
            rows.append({
                "seed": seed,
                "scene_hash": digest,
                "method": method,
                "success": int(len(paths) == len(instance.commodities)),
                "routed": len(paths),
                "total": len(instance.commodities),
                "objective": objective(instance, paths),
                "runtime_s": elapsed,
                "expanded_nodes": nodes,
                "validated": int(validate_paths(instance, paths)),
            })

    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "priority_graph_pilot_raw.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize_rows(rows, first_seed, max_nodes)
    (output / "priority_graph_pilot_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=100)
    parser.add_argument("--first-seed", type=int, default=300000)
    parser.add_argument("--max-nodes", type=int, default=16)
    parser.add_argument("--time-budget-s", type=float)
    parser.add_argument("--output", type=Path, default=Path("data/priority_graph_pilot"))
    args = parser.parse_args()
    if args.scenes < 1 or args.first_seed < 0 or args.max_nodes < 1:
        parser.error("scenes, first-seed, and max-nodes must be positive")
    if args.time_budget_s is not None:
        if args.time_budget_s <= 0:
            parser.error("time-budget-s must be positive")
        result = run_budget_matched(
            args.scenes, args.first_seed, args.time_budget_s, args.output
        )
    else:
        result = run(args.scenes, args.first_seed, args.max_nodes, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
