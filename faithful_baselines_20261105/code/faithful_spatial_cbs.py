"""Spatial CBS baseline for permanent MEP occupancy (protocol.json, frozen 2026-11-05).

High level: best-first conflict tree on sum of physical path costs (Sharon et al. 2012),
no node limit, wall-clock deadline per scene. Conflict: an interior voxel shared by
two or more routes. Branching: forbid the voxel for one of the conflicting routes.
Low level: the unchanged publish-repo A* with congestion weight 0 (optimal for
length + bend + vertical cost under a consistent Manhattan heuristic).
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

CODE = Path(__file__).resolve().parents[2] / "code"
sys.path.insert(0, str(CODE))

from run_routing_experiments import astar, estimate_demand, generate_instance, path_cost  # noqa: E402
from routing_revision_solvers import validate_paths  # noqa: E402

DENSITIES = ("low", "medium", "high")


def find_conflict(paths):
    """Return (voxel, agents) for the smallest shared interior voxel, else None."""
    owners = {}
    for index, path in paths.items():
        for node in path[1:-1]:
            owners.setdefault(node, []).append(index)
    shared = [(node, sorted(users)) for node, users in owners.items() if len(users) > 1]
    return min(shared) if shared else None


def count_conflicts(paths):
    owners = {}
    for path in paths.values():
        for node in path[1:-1]:
            owners[node] = owners.get(node, 0) + 1
    return sum(1 for value in owners.values() if value > 1)


class Timeout(Exception):
    pass


def spatial_cbs(instance, deadline):
    """Return (paths|None, status, expanded, generated)."""
    demand = estimate_demand(instance)
    terminals = {p for c in instance.commodities for p in (c.start, c.goal)}

    def plan(index, forbidden_extra):
        item = instance.commodities[index]
        forbidden = (terminals - {item.start, item.goal}) | set(forbidden_extra)
        route = astar(instance, item, forbidden, demand, 0.0, deadline=deadline)
        if route is None and time.perf_counter() >= deadline:
            raise Timeout
        return route

    expanded = generated = 0
    try:
        root = {}
        for index in range(len(instance.commodities)):
            route = plan(index, ())
            if route is None:
                return None, "root_infeasible", 0, 0
            root[index] = route
        cost = {i: path_cost(p, instance.commodities[i]) for i, p in root.items()}
        nodes = [({}, root, cost)]
        queue = [(sum(cost.values()), count_conflicts(root), 0)]
        seen = {()}
        generated = 1
        while queue:
            if time.perf_counter() >= deadline:
                raise Timeout
            _, _, node_id = heapq.heappop(queue)
            constraints, paths, costs = nodes[node_id]
            nodes[node_id] = None  # release memory of expanded node
            expanded += 1
            conflict = find_conflict(paths)
            if conflict is None:
                return paths, "solved", expanded, generated
            voxel, agents = conflict
            for agent in agents:
                child_constraints = dict(constraints)
                child_constraints[agent] = frozenset(child_constraints.get(agent, frozenset()) | {voxel})
                signature = tuple(sorted((i, tuple(sorted(v))) for i, v in child_constraints.items()))
                if signature in seen:
                    continue
                seen.add(signature)
                route = plan(agent, child_constraints[agent])
                if route is None:
                    continue
                child_paths = dict(paths)
                child_paths[agent] = route
                child_costs = dict(costs)
                child_costs[agent] = path_cost(route, instance.commodities[agent])
                nodes.append((child_constraints, child_paths, child_costs))
                generated += 1
                heapq.heappush(queue, (sum(child_costs.values()), count_conflicts(child_paths), len(nodes) - 1))
        return None, "search_exhausted", expanded, generated
    except Timeout:
        return None, "timeout", expanded, generated


def run_one(task):
    density, seed, budget = task
    instance = generate_instance(density, 10000 * DENSITIES.index(density) + seed)
    started = time.perf_counter()
    paths, status, expanded, generated = spatial_cbs(instance, started + budget)
    runtime = time.perf_counter() - started
    valid = None
    if paths is not None:
        validate_paths(instance, paths)  # raises on any violation
        valid = 1
    cost = sum(path_cost(p, instance.commodities[i]) for i, p in paths.items()) if paths else 0.0
    total = len(instance.commodities)
    row = {
        "density": density, "seed": seed, "method": "spatial_cbs",
        "routed": total if paths else 0, "total": total, "success": int(paths is not None),
        "cost": cost, "objective": (0 if paths else total) * 10000.0 + cost,
        "runtime_s": round(runtime, 4), "expanded": expanded, "generated": generated,
        "status": status, "validated": valid, "deadline_s": budget,
    }
    record = {"density": density, "seed": seed,
              "paths": {str(i): p for i, p in paths.items()} if paths else None}
    return row, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--deadline", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=14)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tasks = [(d, s, args.deadline) for d in DENSITIES for s in range(args.seeds)]
    with Pool(args.workers) as pool:
        results = pool.map(run_one, tasks, chunksize=1)
    rows = [r for r, _ in results]
    with (args.output / "spatial_cbs_raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "spatial_cbs_paths.jsonl").open("w", encoding="utf-8") as handle:
        for _, record in results:
            handle.write(json.dumps(record) + "\n")
    for d in DENSITIES:
        sub = [r for r in rows if r["density"] == d]
        statuses = {}
        for r in sub:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        print(d, "solved", sum(r["success"] for r in sub), "/", len(sub), statuses)


if __name__ == "__main__":
    main()
