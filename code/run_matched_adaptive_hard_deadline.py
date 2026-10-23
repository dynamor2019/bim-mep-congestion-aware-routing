"""Strict-deadline paired comparison of random and adaptive repair."""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from run_advanced_validation import conflict_scores, scaled_instance
from run_routing_experiments import (
    astar,
    estimate_demand,
    manhattan,
    objective,
    route_order,
    solution_cost,
)
from routing_revision_solvers import validate_paths
from run_revision_benchmark import fingerprint

SCALES = ("base", "large", "xlarge")
METHODS = ("mspp_random_repair", "adaptive_multi_operator")


class SearchDeadlineExceeded(TimeoutError):
    """Signal an interrupted low-level search without changing old solvers."""


def bounded_astar(instance, item, occupied, predicted, weight, deadline):
    """Run the benchmark A* objective with a hard expansion-time cutoff."""
    start_state = item.start, (0, 0, 0)
    queue = [(manhattan(item.start, item.goal), 0.0, start_state)]
    parent = {start_state: None}
    best = {start_state: 0.0}
    while queue:
        if time.perf_counter() >= deadline:
            raise SearchDeadlineExceeded
        _, cost, state = heapq.heappop(queue)
        node, previous_direction = state
        if cost != best.get(state):
            continue
        if node == item.goal:
            path, cursor = [], state
            while cursor is not None:
                path.append(cursor[0])
                cursor = parent[cursor]
            return list(reversed(path))
        for nxt in sorted_neighbors(node, instance.shape):
            if time.perf_counter() >= deadline:
                raise SearchDeadlineExceeded
            if nxt in instance.blocked or (nxt in occupied and nxt != item.goal):
                continue
            direction = tuple(b - a for a, b in zip(node, nxt))
            if item.discipline == "drainage" and direction[2] > 0:
                continue
            bend = item.bend_cost if previous_direction not in ((0, 0, 0), direction) else 0.0
            vertical = item.vertical_cost if direction[2] else 0.0
            rho = predicted.get(nxt, 0.0)
            congestion = weight * (rho + 4.0 * max(0.0, rho - 0.65) ** 2)
            new_cost = cost + 1.0 + bend + vertical + congestion
            next_state = nxt, direction
            if new_cost < best.get(next_state, math.inf):
                best[next_state] = new_cost
                parent[next_state] = state
                heuristic = manhattan(nxt, item.goal)
                heapq.heappush(queue, (new_cost + heuristic, new_cost, next_state))
    return None


def sorted_neighbors(node, shape):
    """Match the canonical six-connected neighbor order."""
    x, y, z = node
    candidates = ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z),
                  (x, y - 1, z), (x, y, z + 1), (x, y, z - 1))
    return [point for point in candidates
            if all(0 <= value < limit for value, limit in zip(point, shape))]


def repair(instance, initial, predicted, seed, budget_s, adaptive):
    """Return the best completed incumbent before a strict shared deadline."""
    paths = dict(initial)
    terminals = {point for item in instance.commodities for point in (item.start, item.goal)}
    rng = random.Random(seed)
    operators = ("conflict", "longest", "random")
    rewards = {name: 1.0 for name in operators}
    iterations = 0
    deadline = time.perf_counter() + budget_s
    while time.perf_counter() < deadline:
        route_demand = defaultdict(int)
        for path in paths.values():
            for node in path:
                route_demand[node] += 1
        scores = {}
        for index, item in enumerate(instance.commodities):
            path = paths.get(index, [])
            scores[index] = sum(predicted.get(node, 0.0) + route_demand[node]
                                for node in path) + (1000.0 if index not in paths else 0.0)
        if adaptive:
            operator = rng.choices(operators, weights=[rewards[name] for name in operators])[0]
            count = max(2, math.ceil(len(instance.commodities)
                                     * (0.20 if objective(instance, paths) < 10000 else 0.40)))
            if operator == "conflict":
                selected = sorted(scores, key=scores.get, reverse=True)[:count]
            elif operator == "longest":
                selected = sorted(paths, key=lambda index: len(paths[index]), reverse=True)[:count]
                selected += [index for index in range(len(instance.commodities))
                             if index not in selected][:max(0, count - len(selected))]
            else:
                selected = rng.sample(range(len(instance.commodities)), count)
            weight = 2.0
        else:
            selected = rng.sample(range(len(instance.commodities)),
                                  max(2, math.ceil(len(instance.commodities) * 0.25)))
            weight = 0.0
        candidate = {index: path for index, path in paths.items() if index not in selected}
        occupied = {node for path in candidate.values() for node in path[1:-1]}
        try:
            for index in sorted(selected, key=lambda item_index: scores[item_index], reverse=True):
                item = instance.commodities[index]
                forbidden = occupied | (terminals - {item.start, item.goal})
                path = bounded_astar(instance, item, forbidden, predicted, weight, deadline)
                if path:
                    candidate[index] = path
                    occupied.update(path[1:-1])
        except SearchDeadlineExceeded:
            break
        if time.perf_counter() >= deadline:
            break
        previous = objective(instance, paths)
        current = objective(instance, candidate)
        if current <= previous:
            paths = candidate
            if adaptive:
                rewards[operator] += 1.0
        elif adaptive:
            rewards[operator] = max(0.25, rewards[operator] * 0.85)
        iterations += 1
    return paths, iterations


def exact_mcnemar(random_only, adaptive_only):
    """Compute the two-sided exact McNemar p-value."""
    discordant = random_only + adaptive_only
    if not discordant:
        return 1.0
    lower_tail = sum(math.comb(discordant, k)
                     for k in range(min(random_only, adaptive_only) + 1))
    return min(1.0, 2.0 * lower_tail / (2 ** discordant))


def run_scene(scale, seed, budget_s):
    """Pair both methods on identical geometry, terminals, and incumbent."""
    instance = scaled_instance(scale, seed)
    predicted = estimate_demand(instance)
    order = list(range(len(instance.commodities)))
    random.Random(seed).shuffle(order)
    initial = route_order(instance, order, predicted, 0.0)
    validate_paths(instance, initial)
    scene_hash = fingerprint(instance)
    rows = []
    for method in METHODS:
        started = time.perf_counter()
        paths, iterations = repair(instance, initial, predicted, seed, budget_s,
                                   method == "adaptive_multi_operator")
        runtime = time.perf_counter() - started
        validate_paths(instance, paths)
        rows.append({
            "scale": scale, "seed": seed, "scene_hash": scene_hash,
            "method": method, "systems": len(instance.commodities),
            "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths), "total": len(instance.commodities),
            "objective": objective(instance, paths),
            "physical_cost": solution_cost(instance, paths),
            "runtime_s": runtime, "budget_s": budget_s,
            "iterations_used": iterations, "validated": 1,
        })
    return rows


def summarize(rows):
    """Summarize paired completion and hard-cap runtime by scale."""
    paired = defaultdict(dict)
    for row in rows:
        paired[(row["scale"], row["seed"])][row["method"]] = row
    results = []
    for scale in SCALES:
        pairs = [value for (name, _), value in paired.items() if name == scale]
        random_only = sum(pair[METHODS[0]]["success"] > pair[METHODS[1]]["success"]
                          for pair in pairs)
        adaptive_only = sum(pair[METHODS[1]]["success"] > pair[METHODS[0]]["success"]
                            for pair in pairs)
        methods = {}
        for method in METHODS:
            selected = [pair[method] for pair in pairs]
            methods[method] = {
                "complete_scenes": sum(row["success"] for row in selected),
                "median_runtime_s": statistics.median(row["runtime_s"] for row in selected),
                "max_runtime_s": max(row["runtime_s"] for row in selected),
                "median_iterations": statistics.median(row["iterations_used"] for row in selected),
            }
        results.append({
            "scale": scale, "paired_scenes": len(pairs),
            "random_only_successes": random_only,
            "adaptive_only_successes": adaptive_only,
            "exact_two_sided_mcnemar_p": exact_mcnemar(random_only, adaptive_only),
            "methods": methods,
        })
    return {"scale_results": results, "paired_scenes": len(paired),
            "validated_outputs": len(rows)}


def main():
    """Run the preregistered paired scale cohort and write checksummed results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=140000)
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
        "protocol": "paired same-scene repair under a hard A* wall-clock deadline",
        "budget_seconds_per_method": args.budget_seconds,
        "seeds_per_scale": args.seeds, "start_seed": args.start_seed,
        "scales": list(SCALES), "methods": list(METHODS),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timer_note": "Deadline checked inside A*; small interpreter and return overhead may exceed the cap.",
        "scope_note": "Synthetic comparison; this does not establish general scaling behavior.",
    })
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "raw_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "outputs": len(rows), "all_validated": all(row["validated"] for row in rows),
    }
    args.output.with_suffix(args.output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"raw": str(args.output), "summary": str(summary_path),
                      "outputs": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
