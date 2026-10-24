"""Reproducible synthetic experiments for congestion-aware BIM-MEP routing."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import wilcoxon


Coord = tuple[int, int, int]


@dataclass(frozen=True)
class Commodity:
    """One terminal pair with discipline-specific routing parameters."""

    start: Coord
    goal: Coord
    discipline: str
    bend_cost: float
    vertical_cost: float


@dataclass
class Instance:
    """A discretized ceiling-void routing instance."""

    shape: tuple[int, int, int]
    blocked: set[Coord]
    commodities: list[Commodity]


def neighbors(node: Coord, shape: tuple[int, int, int]) -> list[Coord]:
    """Return six-connected grid neighbors."""
    x, y, z = node
    result = []
    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        nxt = x + dx, y + dy, z + dz
        if all(0 <= value < limit for value, limit in zip(nxt, shape)):
            result.append(nxt)
    return result


def manhattan(a: Coord, b: Coord) -> int:
    """Return Manhattan distance between two grid nodes."""
    return sum(abs(x - y) for x, y in zip(a, b))


def generate_instance(density: str, seed: int) -> Instance:
    """Create deterministic architectural scenes with corridor bottlenecks."""
    rng = random.Random(seed)
    shape = (16, 12, 3)
    counts = {"low": 5, "medium": 7, "high": 9}
    obstacle_rates = {"low": 0.045, "medium": 0.065, "high": 0.085}
    blocked: set[Coord] = set()

    # Two structural walls with openings create realistic shared service corridors.
    for x in (5, 10):
        openings = {rng.randrange(1, 5), rng.randrange(7, 11)}
        for y in range(shape[1]):
            for z in range(shape[2]):
                if y not in openings and rng.random() < 0.82:
                    blocked.add((x, y, z))
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                if rng.random() < obstacle_rates[density]:
                    blocked.add((x, y, z))

    free = [(x, y, z) for x in range(shape[0]) for y in range(shape[1]) for z in range(shape[2]) if (x, y, z) not in blocked]
    commodities: list[Commodity] = []
    used: set[Coord] = set()
    disciplines = (("HVAC", 1.8, 1.4), ("pressure", 1.2, 1.5), ("electrical", 0.8, 1.2), ("drainage", 1.3, 2.0))
    attempts = 0
    while len(commodities) < counts[density] and attempts < 10000:
        attempts += 1
        left = rng.choice([p for p in free if p[0] <= 3 and p not in used])
        right = rng.choice([p for p in free if p[0] >= shape[0] - 4 and p not in used])
        if manhattan(left, right) < shape[0] - 3:
            continue
        discipline, bend_cost, vertical_cost = disciplines[len(commodities) % len(disciplines)]
        start, goal = left, right
        if discipline == "drainage" and start[2] < goal[2]:
            start, goal = goal, start
        commodities.append(Commodity(start, goal, discipline, bend_cost, vertical_cost))
        used.update((start, goal))
        blocked.discard(start)
        blocked.discard(goal)
    return Instance(shape, blocked, commodities)


def estimate_demand(instance: Instance) -> dict[Coord, float]:
    """Estimate route-independent RUDY-like node demand from terminal prisms."""
    demand: dict[Coord, float] = defaultdict(float)
    for item in instance.commodities:
        mins = tuple(min(a, b) for a, b in zip(item.start, item.goal))
        maxs = tuple(max(a, b) for a, b in zip(item.start, item.goal))
        candidates = []
        for x in range(mins[0], maxs[0] + 1):
            for y in range(mins[1], maxs[1] + 1):
                for z in range(mins[2], maxs[2] + 1):
                    node = (x, y, z)
                    if node not in instance.blocked:
                        candidates.append(node)
        if not candidates:
            continue
        contribution = manhattan(item.start, item.goal) / len(candidates)
        for node in candidates:
            demand[node] += contribution
    return demand


def astar(
    instance: Instance,
    item: Commodity,
    occupied: set[Coord],
    predicted: dict[Coord, float],
    congestion_weight: float,
    soft_occupied_weight: float = 0.0,
) -> list[Coord] | None:
    """Find a discipline-aware route with optional soft occupancy penalties."""
    start_state = item.start, (0, 0, 0)
    queue = [(0.0, 0.0, start_state)]
    parent: dict[tuple[Coord, Coord], tuple[Coord, Coord] | None] = {start_state: None}
    best = {start_state: 0.0}
    while queue:
        _, cost, state = heapq.heappop(queue)
        node, previous_direction = state
        if cost != best.get(state):
            continue
        if node == item.goal:
            path = []
            cursor: tuple[Coord, Coord] | None = state
            while cursor is not None:
                path.append(cursor[0])
                cursor = parent[cursor]
            return list(reversed(path))
        for nxt in neighbors(node, instance.shape):
            if nxt in instance.blocked:
                continue
            if nxt in occupied and nxt != item.goal and soft_occupied_weight <= 0:
                continue
            direction = tuple(b - a for a, b in zip(node, nxt))
            if item.discipline == "drainage" and direction[2] > 0:
                continue
            bend = item.bend_cost if previous_direction != (0, 0, 0) and direction != previous_direction else 0.0
            vertical = item.vertical_cost if direction[2] else 0.0
            rho = predicted.get(nxt, 0.0)
            congestion = congestion_weight * (rho + 4.0 * max(0.0, rho - 0.65) ** 2)
            overlap = soft_occupied_weight if nxt in occupied and nxt != item.goal else 0.0
            new_cost = cost + 1.0 + bend + vertical + congestion + overlap
            new_state = nxt, direction
            if new_cost < best.get(new_state, math.inf):
                best[new_state] = new_cost
                parent[new_state] = state
                heuristic = manhattan(nxt, item.goal)
                heapq.heappush(queue, (new_cost + heuristic, new_cost, new_state))
    return None


def path_cost(path: list[Coord], item: Commodity) -> float:
    """Calculate length, bend, and vertical-movement cost."""
    if not path:
        return math.inf
    cost = len(path) - 1
    previous = None
    for a, b in zip(path, path[1:]):
        direction = tuple(y - x for x, y in zip(a, b))
        if previous is not None and direction != previous:
            cost += item.bend_cost
        if direction[2]:
            cost += item.vertical_cost
        previous = direction
    return cost


def route_order(
    instance: Instance,
    order: list[int],
    predicted: dict[Coord, float],
    congestion_weight: float,
) -> dict[int, list[Coord]]:
    """Route commodities sequentially under a supplied priority order."""
    paths: dict[int, list[Coord]] = {}
    occupied: set[Coord] = set()
    for index in order:
        item = instance.commodities[index]
        forbidden = occupied | foreign_terminal_cells(instance, index)
        path = astar(instance, item, forbidden, predicted, congestion_weight)
        if path is not None:
            paths[index] = path
            occupied.update(path[1:-1])
    return paths


def foreign_terminal_cells(instance: Instance, index: int) -> set[Coord]:
    """Return every other commodity's endpoint that this route must avoid."""
    item = instance.commodities[index]
    terminals = {
        point
        for commodity in instance.commodities
        for point in (commodity.start, commodity.goal)
    }
    return terminals - {item.start, item.goal}


def improve(
    instance: Instance,
    initial: dict[int, list[Coord]],
    predicted: dict[Coord, float],
    guided: bool,
    rng: random.Random,
    iterations: int = 5,
    destroy_fraction: float = 0.25,
    congestion_weight: float = 2.0,
) -> tuple[dict[int, list[Coord]], list[float]]:
    """Apply random or congestion-guided destroy-and-repair."""
    paths = dict(initial)
    trace = [objective(instance, paths)]
    for _ in range(iterations):
        route_demand: dict[Coord, int] = defaultdict(int)
        for path in paths.values():
            for node in path:
                route_demand[node] += 1
        scores = {}
        for index, item in enumerate(instance.commodities):
            path = paths.get(index, [])
            hotspot = sum(predicted.get(node, 0.0) + route_demand[node] for node in path)
            scores[index] = hotspot + (1000.0 if index not in paths else 0.0)
        count = max(2, math.ceil(len(instance.commodities) * destroy_fraction))
        if guided:
            selected = sorted(scores, key=scores.get, reverse=True)[:count]
        else:
            selected = rng.sample(range(len(instance.commodities)), count)
        kept = {index: path for index, path in paths.items() if index not in selected}
        occupied = {node for path in kept.values() for node in path[1:-1]}
        candidate = dict(kept)
        selected.sort(key=lambda index: scores[index], reverse=True)
        for index in selected:
            item = instance.commodities[index]
            forbidden = occupied | foreign_terminal_cells(instance, index)
            path = astar(instance, item, forbidden, predicted, congestion_weight if guided else 0.0)
            if path is not None:
                candidate[index] = path
                occupied.update(path[1:-1])
        if objective(instance, candidate) <= objective(instance, paths):
            paths = candidate
        trace.append(objective(instance, paths))
    return paths, trace


def solution_cost(instance: Instance, paths: dict[int, list[Coord]]) -> float:
    """Return finite cost of routed commodities."""
    return sum(path_cost(path, instance.commodities[index]) for index, path in paths.items())


def objective(instance: Instance, paths: dict[int, list[Coord]]) -> float:
    """Use a large lexicographic penalty for unrouted commodities."""
    return (len(instance.commodities) - len(paths)) * 10000.0 + solution_cost(instance, paths)


def solve(instance: Instance, method: str, seed: int) -> tuple[dict[int, list[Coord]], list[float], float]:
    """Run one baseline, ablation, or proposed solver configuration."""
    started = time.perf_counter()
    rng = random.Random(seed)
    predicted = estimate_demand(instance)
    indices = list(range(len(instance.commodities)))
    if method in {"pbs_random", "stage3_only", "proposed"}:
        # Multi-start priority search approximates PBS's ordering-space exploration.
        candidates = []
        for _ in range(2):
            rng.shuffle(indices)
            weight = 2.0 if method == "proposed" else 0.0
            result = route_order(instance, list(indices), predicted, weight)
            candidates.append(result)
        paths = min(candidates, key=lambda value: objective(instance, value))
    else:
        order = sorted(indices, key=lambda i: (-instance.commodities[i].bend_cost, i))
        weight = 2.0 if method == "stage1_only" else 0.0
        paths = route_order(instance, order, predicted, weight)
    trace = [objective(instance, paths)]
    if method == "pbs_random":
        paths, trace = improve(instance, paths, predicted, False, rng)
    elif method in {"stage3_only", "proposed"}:
        paths, trace = improve(instance, paths, predicted, True, rng)
    return paths, trace, time.perf_counter() - started


def summarize(rows: list[dict[str, object]], output_dir: Path) -> dict[str, object]:
    """Aggregate results, compute paired tests, and save publication tables."""
    methods = ["fix_order", "pbs_random", "stage1_only", "stage3_only", "proposed"]
    densities = ["low", "medium", "high"]
    summary_rows = []
    tests = {}
    for density in densities:
        for method in methods:
            subset = [row for row in rows if row["density"] == density and row["method"] == method]
            success = np.array([row["success"] for row in subset], dtype=float)
            costs = np.array([row["normalized_cost"] for row in subset], dtype=float)
            runtimes = np.array([row["runtime_s"] for row in subset], dtype=float)
            ci = 1.96 * costs.std(ddof=1) / math.sqrt(len(costs))
            summary_rows.append({
                "density": density,
                "method": method,
                "success_rate": success.mean(),
                "normalized_cost_mean": costs.mean(),
                "normalized_cost_ci95": ci,
                "runtime_mean_s": runtimes.mean(),
            })
        paired = {}
        for row in rows:
            if row["density"] == density:
                paired.setdefault((row["seed"], row["method"]), row["objective"])
        proposed = np.array([paired[(seed, "proposed")] for seed in sorted({key[0] for key in paired})])
        baseline = np.array([paired[(seed, "pbs_random")] for seed in sorted({key[0] for key in paired})])
        differences = baseline - proposed
        try:
            statistic, p_value = wilcoxon(differences, alternative="greater")
        except ValueError:
            statistic, p_value = 0.0, 1.0
        tests[density] = {
            "wilcoxon_statistic": float(statistic),
            "p_value_one_sided": float(p_value),
            "paired_rank_biserial": float((np.sum(differences > 0) - np.sum(differences < 0)) / len(differences)),
        }
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)
    payload = {"summary": summary_rows, "tests": tests}
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def make_figures(rows: list[dict[str, object]], output_dir: Path) -> None:
    """Create convergence and ablation figures from raw observations."""
    labels = ["low", "medium", "high"]
    advantages = []
    for density in labels:
        proposed = np.mean([r["normalized_cost"] for r in rows if r["density"] == density and r["method"] == "proposed"])
        baseline = np.mean([r["normalized_cost"] for r in rows if r["density"] == density and r["method"] == "pbs_random"])
        advantages.append(100 * (baseline - proposed) / baseline)
    plt.figure(figsize=(6.4, 4.0))
    plt.plot(labels, advantages, marker="o", linewidth=2)
    plt.ylabel("Normalized-cost advantage (%)")
    plt.xlabel("Routing density")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_dir / "figure1_density_advantage.png", dpi=220)
    plt.close()

    plt.figure(figsize=(7.0, 4.2))
    for density, linestyle in zip(labels, ("-", "--", ":")):
        for method, color in (("pbs_random", "#777777"), ("stage3_only", "#006d77")):
            traces = [json.loads(r["trace"]) for r in rows if r["density"] == density and r["method"] == method]
            normalized = []
            for trace in traces:
                initial = max(trace[0], 1.0)
                normalized.append([value / initial for value in trace])
            mean_trace = np.mean(np.asarray(normalized), axis=0)
            label = f"{density}: {'guided' if method == 'stage3_only' else 'random'}"
            plt.plot(range(len(mean_trace)), mean_trace, color=color, linestyle=linestyle, label=label)
    plt.xlabel("Destroy-and-repair iteration")
    plt.ylabel("Cost / initial cost")
    plt.grid(alpha=0.25)
    plt.legend(frameon=False, ncol=2, fontsize=8)
    plt.tight_layout()
    plt.savefig(output_dir / "figure2_convergence.png", dpi=220)
    plt.close()

    means = {}
    for method in ("stage1_only", "stage3_only", "proposed"):
        means[method] = []
        for density in labels:
            base = np.mean([r["normalized_cost"] for r in rows if r["density"] == density and r["method"] == "pbs_random"])
            value = np.mean([r["normalized_cost"] for r in rows if r["density"] == density and r["method"] == method])
            means[method].append(100 * (base - value) / base)
    x = np.arange(len(labels))
    width = 0.24
    plt.figure(figsize=(7.0, 4.1))
    for offset, method in zip((-width, 0, width), means):
        plt.bar(x + offset, means[method], width, label=method.replace("_", " "))
    plt.xticks(x, labels)
    plt.ylabel("Improvement over PBS-random (%)")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(output_dir / "figure3_ablation.png", dpi=220)
    plt.close()


def run(seeds: int, output_dir: Path) -> None:
    """Run all methods across density levels and persist raw observations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    methods = ["fix_order", "pbs_random", "stage1_only", "stage3_only", "proposed"]
    for density_index, density in enumerate(("low", "medium", "high")):
        for seed in range(seeds):
            instance = generate_instance(density, 10000 * density_index + seed)
            lower_bound = sum(manhattan(item.start, item.goal) for item in instance.commodities)
            for method in methods:
                paths, trace, runtime = solve(instance, method, seed)
                cost = solution_cost(instance, paths)
                rows.append({
                    "density": density,
                    "seed": seed,
                    "method": method,
                    "routed": len(paths),
                    "total": len(instance.commodities),
                    "success": int(len(paths) == len(instance.commodities)),
                    "cost": cost,
                    "objective": objective(instance, paths),
                    "normalized_cost": objective(instance, paths) / lower_bound,
                    "runtime_s": runtime,
                    "trace": json.dumps(trace),
                })
    with (output_dir / "raw_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summarize(rows, output_dir)
    make_figures(rows, output_dir)


def main() -> None:
    """Parse command-line options and execute the benchmark."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    run(args.seeds, args.output)


if __name__ == "__main__":
    main()
