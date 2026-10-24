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
    parser.add_argument("--output", type=Path, default=Path("data/priority_graph_pilot"))
    args = parser.parse_args()
    if args.scenes < 1 or args.first_seed < 0 or args.max_nodes < 1:
        parser.error("scenes, first-seed, and max-nodes must be positive")
    print(json.dumps(run(args.scenes, args.first_seed, args.max_nodes, args.output), indent=2))


if __name__ == "__main__":
    main()
