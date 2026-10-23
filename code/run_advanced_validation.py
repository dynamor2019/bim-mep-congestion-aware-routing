"""Exploratory adaptive-repair and scale checks for the routing prototype."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

from run_routing_experiments import (
    Commodity,
    Instance,
    astar,
    estimate_demand,
    manhattan,
    objective,
    path_cost,
    route_order,
    solution_cost,
    generate_instance,
    improve,
)
from routing_revision_solvers import validate_paths


def scaled_instance(size: str, seed: int) -> Instance:
    """Generate larger deterministic scenes while retaining the corridor motif."""
    shapes = {"base": (16, 12, 3), "large": (24, 18, 4), "xlarge": (32, 24, 5)}
    counts = {"base": 9, "large": 12, "xlarge": 15}
    if size == "base":
        return generate_instance("high", seed)
    shape = shapes[size]
    rng = random.Random(seed)
    obstacle_rate = 0.085
    blocked = set()
    walls = (shape[0] // 3, 2 * shape[0] // 3)
    for x in walls:
        openings = {rng.randrange(1, shape[1] // 3), rng.randrange(2 * shape[1] // 3, shape[1] - 1)}
        for y in range(shape[1]):
            for z in range(shape[2]):
                if y not in openings and rng.random() < 0.82:
                    blocked.add((x, y, z))
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                if rng.random() < obstacle_rate:
                    blocked.add((x, y, z))
    free = [(x, y, z) for x in range(shape[0]) for y in range(shape[1]) for z in range(shape[2]) if (x, y, z) not in blocked]
    disciplines = (("HVAC", 1.8, 1.4), ("pressure", 1.2, 1.5), ("electrical", 0.8, 1.2), ("drainage", 1.3, 2.0))
    commodities = []
    used = set()
    attempts = 0
    while len(commodities) < counts[size] and attempts < 20000:
        attempts += 1
        left = rng.choice([p for p in free if p[0] <= shape[0] // 5 and p not in used])
        right = rng.choice([p for p in free if p[0] >= shape[0] - shape[0] // 5 and p not in used])
        if manhattan(left, right) < shape[0] - 3:
            continue
        discipline, bend, vertical = disciplines[len(commodities) % len(disciplines)]
        start, goal = left, right
        if discipline == "drainage" and start[2] < goal[2]:
            start, goal = goal, start
        commodities.append(Commodity(start, goal, discipline, bend, vertical))
        used.update((start, goal)); blocked.discard(start); blocked.discard(goal)
    return Instance(shape, blocked, commodities)


def conflict_scores(paths: dict, predicted: dict) -> dict[int, float]:
    load = defaultdict(int)
    for path in paths.values():
        for node in path:
            load[node] += 1
    return {index: sum(load[node] + predicted.get(node, 0.0) for node in path) for index, path in paths.items()}


def adaptive_repair(instance: Instance, initial: dict, predicted: dict, seed: int, conflict_only: bool = False) -> tuple[dict, list[float]]:
    """Use hotspot, longest-path, and random operators with simple reward adaptation."""
    rng = random.Random(seed)
    paths = dict(initial)
    terminals = {point for item in instance.commodities for point in (item.start, item.goal)}
    trace = [objective(instance, paths)]
    operators = ["conflict", "longest", "random"]
    rewards = {name: 1.0 for name in operators}
    for _ in range(8):
        scores = conflict_scores(paths, predicted)
        if conflict_only:
            operator = "conflict"
        else:
            operator = rng.choices(operators, weights=[rewards[name] for name in operators], k=1)[0]
        count = max(2, math.ceil(len(instance.commodities) * (0.20 if trace[-1] < 10000 else 0.40)))
        if operator == "conflict":
            selected = sorted(scores, key=scores.get, reverse=True)[:count]
        elif operator == "longest":
            selected = sorted(paths, key=lambda i: len(paths[i]), reverse=True)[:count]
            selected += [i for i in range(len(instance.commodities)) if i not in selected][:max(0, count - len(selected))]
        else:
            selected = rng.sample(range(len(instance.commodities)), count)
        kept = {i: p for i, p in paths.items() if i not in selected}
        occupied = {node for path in kept.values() for node in path[1:-1]}
        candidate = dict(kept)
        for index in sorted(selected, key=lambda i: scores.get(i, 1000.0), reverse=True):
            item = instance.commodities[index]
            forbidden = occupied | (terminals - {item.start, item.goal})
            path = astar(instance, item, forbidden, predicted, 2.0)
            if path:
                candidate[index] = path
                occupied.update(path[1:-1])
        before = objective(instance, paths)
        after = objective(instance, candidate)
        if after <= before:
            paths = candidate
            rewards[operator] += 1.0
        else:
            rewards[operator] = max(0.25, rewards[operator] * 0.85)
        trace.append(objective(instance, paths))
    return paths, trace


def run_case(instance: Instance, method: str, seed: int) -> dict:
    started = time.perf_counter()
    predicted = estimate_demand(instance)
    indices = list(range(len(instance.commodities)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    base = route_order(instance, indices, predicted, 0.0)
    if method == "mspp_random_repair":
        paths, trace = improve(instance, base, predicted, False, rng, iterations=5)
    elif method == "adaptive_multi_operator":
        paths, trace = adaptive_repair(instance, base, predicted, seed)
    elif method == "conflict_guided":
        paths, trace = adaptive_repair(instance, base, predicted, seed, conflict_only=True)
    else:
        paths, trace = adaptive_repair(instance, base, predicted, seed, conflict_only=False)
    validate_paths(instance, paths)
    return {"method": method, "seed": seed, "routed": len(paths), "total": len(instance.commodities), "success": int(len(paths) == len(instance.commodities)), "objective": objective(instance, paths), "cost": solution_cost(instance, paths), "runtime_s": time.perf_counter() - started, "validated": 1, "trace": json.dumps(trace)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("results/advanced_validation"))
    args = parser.parse_args()
    rows = []
    for size in ("base", "large", "xlarge"):
        for seed in range(args.seeds):
            instance = scaled_instance(size, 50000 + seed)
            for method in ("mspp_random_repair", "adaptive_multi_operator", "conflict_guided"):
                rows.append(dict(run_case(instance, method, seed), size=size, shape="x".join(map(str, instance.shape))))
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "advanced_validation_raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    (args.output / "advanced_validation_summary.json").write_text(json.dumps({"methods": ["mspp_random_repair", "adaptive_multi_operator", "conflict_guided"], "note": "Exploratory prototype extension; not faithful PBS or MAPF-LNS.", "rows": len(rows)}, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
