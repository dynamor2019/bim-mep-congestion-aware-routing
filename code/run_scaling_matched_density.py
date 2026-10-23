"""Run a seeded matched-density stress test across three grid scales."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from routing_revision_solvers import RoutingContext, SearchBudget, lns, pbs, validate_paths  # noqa: E402
from run_revision_benchmark import fingerprint, initial_routes  # noqa: E402
from run_routing_experiments import Commodity, Instance, estimate_demand, manhattan, objective, solution_cost  # noqa: E402


SCALES = ((9, (16, 12, 3)), (27, (24, 18, 4)), (60, (32, 24, 5)))
METHODS = ("random", "blocker", "adaptive", "pbs_static")


def generate_instance(shape: tuple[int, int, int], count: int, seed: int) -> Instance:
    """Generate a fixed corridor motif with a controlled obstacle rate."""
    rng = random.Random(seed)
    blocked = set()
    wall_x = (shape[0] // 3, 2 * shape[0] // 3)
    for x in wall_x:
        openings = {rng.randrange(1, shape[1] // 3), rng.randrange(2 * shape[1] // 3, shape[1] - 1)}
        for y in range(shape[1]):
            for z in range(shape[2]):
                if y not in openings and rng.random() < 0.82:
                    blocked.add((x, y, z))
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                if rng.random() < 0.085:
                    blocked.add((x, y, z))
    components_3d = connected_components(shape, blocked, planar=False)
    components_2d = connected_components(shape, blocked, planar=True)
    pairs_3d = feasible_long_pairs(shape, components_3d, same_layer=False)
    pairs_2d = feasible_long_pairs(shape, components_2d, same_layer=True)
    disciplines = (("HVAC", 1.8, 1.4), ("pressure", 1.2, 1.5),
                   ("electrical", 0.8, 1.2), ("drainage", 1.3, 2.0))
    commodities = []
    used = set()
    while len(commodities) < count:
        discipline, bend_cost, vertical_cost = disciplines[len(commodities) % len(disciplines)]
        pairs = pairs_2d if discipline == "drainage" else pairs_3d
        candidates = [(start, goal) for start, goal in pairs
                      if start not in used and goal not in used]
        if not candidates:
            break
        start, goal = rng.choice(candidates)
        if discipline == "drainage" and start[2] < goal[2]:
            start, goal = goal, start
        commodities.append(Commodity(start, goal, discipline, bend_cost, vertical_cost))
        used.update((start, goal))
    if len(commodities) != count:
        raise RuntimeError(f"Generated {len(commodities)} of {count} requested commodities")
    return Instance(shape, blocked, commodities)


def connected_components(shape: tuple[int, int, int], blocked: set[tuple[int, int, int]], planar: bool) -> dict:
    """Label free-space components with optional same-elevation connectivity."""
    labels = {}
    component = 0
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                root = (x, y, z)
                if root in blocked or root in labels:
                    continue
                queue = deque([root])
                labels[root] = component
                while queue:
                    point = queue.popleft()
                    for axis in range(2 if planar else 3):
                        for step in (-1, 1):
                            neighbor = list(point)
                            neighbor[axis] += step
                            neighbor = tuple(neighbor)
                            if (all(0 <= value < limit for value, limit in zip(neighbor, shape))
                                    and neighbor not in blocked and neighbor not in labels):
                                labels[neighbor] = component
                                queue.append(neighbor)
                component += 1
    return labels


def feasible_long_pairs(shape: tuple[int, int, int], labels: dict, same_layer: bool) -> list:
    """List long left-to-right pairs connected in 3-D or at fixed elevation."""
    left = [point for point in labels if point[0] <= shape[0] // 5]
    right = [point for point in labels if point[0] >= shape[0] - shape[0] // 5]
    return [(start, goal) for start in left for goal in right
            if (not same_layer or start[2] == goal[2]) and labels[start] == labels[goal]
            and manhattan(start, goal) >= shape[0] - 3]


def run_scene(instance: Instance, seed: int, rng_seed: int, budget: SearchBudget) -> list[dict]:
    """Run each method on one scene with shared best-of-two initialization."""
    predicted = estimate_demand(instance)
    init_context = RoutingContext(instance, predicted)
    started = time.perf_counter()
    initial = initial_routes(init_context, seed)
    initial_runtime = time.perf_counter() - started
    validate_paths(instance, initial)
    rows = []
    for method in METHODS:
        context = RoutingContext(instance, predicted)
        started = time.perf_counter()
        if method == "pbs_static":
            paths, _, info = pbs(context, initial, budget)
        else:
            paths, _, info = lns(context, initial, method, seed, budget)
        elapsed = time.perf_counter() - started
        validate_paths(instance, paths)
        rows.append({
            "shape": "x".join(map(str, instance.shape)),
            "seed": seed,
            "rng_seed": rng_seed,
            "n_systems": len(instance.commodities),
            "scene_hash": fingerprint(instance),
            "method": method,
            "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths),
            "physical_cost": solution_cost(instance, paths),
            "objective": objective(instance, paths),
            "runtime_s": elapsed,
            "initial_runtime_s": initial_runtime,
            "astar_calls": context.calls,
            "status": info["status"],
            "nodes": info["nodes"],
            "validated": 1,
        })
    return rows


def run(seeds: int, output: Path, budget: SearchBudget) -> None:
    """Write one row per scene/method, flushing after each scene."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = None
        for scale_index, (count, shape) in enumerate(SCALES):
            for seed in range(seeds):
                rng_seed = 200_000 + scale_index * 10_000 + seed
                instance = generate_instance(shape, count, rng_seed)
                rows = run_scene(instance, seed, rng_seed, budget)
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                    writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                print(f"scale={count}: {seed + 1}/{seeds}", flush=True)
    write_manifest(output, seeds, budget)


def write_manifest(output: Path, seeds: int, budget: SearchBudget) -> None:
    """Write source, output, platform, and protocol metadata for a result file."""
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "protocol": "matched-density synthetic scale stress test",
        "source_sha256": source_hash,
        "output_sha256": output_hash,
        "python": sys.version,
        "platform": platform.platform(),
        "seeds_per_scale": seeds,
        "scales": [{"systems": count, "shape": list(shape)} for count, shape in SCALES],
        "methods": list(METHODS),
        "budget": {"seconds": budget.seconds, "iterations": budget.iterations,
                   "nodes": budget.nodes},
        "generator": "8.5% random obstacles plus two probabilistic wall motifs; each commodity is individually reachable before routing.",
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def main() -> None:
    """Parse experiment size and shared search budgets."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=15)
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--nodes", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    budget = SearchBudget(seconds=args.seconds, iterations=args.iterations, nodes=args.nodes)
    run(args.seeds, args.output, budget)


if __name__ == "__main__":
    main()
