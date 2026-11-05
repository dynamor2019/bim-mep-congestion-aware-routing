"""Bounded-suboptimal spatial CBS, BCBS(w, 1) of Barer et al. [25], for permanent occupancy.

High level: focal search with suboptimality factor w = 1.5. OPEN is ordered by the
sum of path costs. FOCAL holds every open node whose cost is at most w * (minimum
open cost), ordered by the number of conflicting voxels. Low level: the unchanged
optimal A* (congestion weight 0), so node cost is a valid lower bound and every
returned solution costs at most w times the optimum. Full ECBS also uses focal search
at the low level; that variant is not implemented here. No node limit; per-scene
wall-clock deadline.
"""

from __future__ import annotations

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
W = 1.5


class Timeout(Exception):
    pass


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


def bcbs(instance, deadline, w=W):
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

    nodes = []          # node id -> (cost, conflicts, constraints, paths)
    open_heap = []      # (cost, id)
    focal_heap = []     # (conflicts, cost, id)
    closed = set()
    in_focal = set()

    def add(cost, constraints, paths, bound):
        node_id = len(nodes)
        conflicts = count_conflicts(paths)
        nodes.append((cost, conflicts, constraints, paths))
        heapq.heappush(open_heap, (cost, node_id))
        if cost <= bound:
            heapq.heappush(focal_heap, (conflicts, cost, node_id))
            in_focal.add(node_id)

    expanded = 0
    try:
        root = {}
        for index in range(len(instance.commodities)):
            route = plan(index, ())
            if route is None:
                return None, "root_infeasible", 0, 0
            root[index] = route
        root_cost = sum(path_cost(p, instance.commodities[i]) for i, p in root.items())
        f_min = root_cost
        add(root_cost, {}, root, w * f_min)
        seen = {()}
        while True:
            if time.perf_counter() >= deadline:
                raise Timeout
            while open_heap and open_heap[0][1] in closed:
                heapq.heappop(open_heap)
            if not open_heap:
                return None, "search_exhausted", expanded, len(nodes)
            new_min = open_heap[0][0]
            if new_min > f_min:
                # The lower bound rose: admit open nodes inside the widened band.
                f_min = new_min
                for cost, node_id in open_heap:
                    if node_id not in closed and node_id not in in_focal and cost <= w * f_min:
                        heapq.heappush(focal_heap, (nodes[node_id][1], cost, node_id))
                        in_focal.add(node_id)
            while focal_heap and focal_heap[0][2] in closed:
                heapq.heappop(focal_heap)
            # The OPEN minimum is always within the band, so FOCAL is non-empty here.
            _, _, node_id = heapq.heappop(focal_heap)
            closed.add(node_id)
            expanded += 1
            cost, _, constraints, paths = nodes[node_id]
            nodes[node_id] = (cost, 0, None, None)  # release memory
            conflict = find_conflict(paths)
            if conflict is None:
                return paths, "solved", expanded, len(nodes)
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
                child_cost = sum(path_cost(p, instance.commodities[i]) for i, p in child_paths.items())
                add(child_cost, child_constraints, child_paths, w * f_min)
    except Timeout:
        return None, "timeout", expanded, len(nodes)


def run_one(task):
    density, seed, budget = task
    instance = generate_instance(density, 10000 * DENSITIES.index(density) + seed)
    started = time.perf_counter()
    paths, status, expanded, generated = bcbs(instance, started + budget)
    runtime = time.perf_counter() - started
    valid = None
    if paths is not None:
        validate_paths(instance, paths)
        valid = 1
    cost = sum(path_cost(p, instance.commodities[i]) for i, p in paths.items()) if paths else 0.0
    total = len(instance.commodities)
    return {
        "density": density, "seed": seed, "method": "spatial_bcbs_w1.5",
        "routed": total if paths else 0, "total": total, "success": int(paths is not None),
        "cost": cost, "objective": (0 if paths else total) * 10000.0 + cost,
        "runtime_s": round(runtime, 4), "expanded": expanded, "generated": generated,
        "status": status, "validated": valid, "deadline_s": budget, "w": W,
    }, {"density": density, "seed": seed,
        "paths": {str(i): p for i, p in paths.items()} if paths else None}


def main():
    import argparse
    import csv
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
    with (args.output / "spatial_bcbs_raw.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "spatial_bcbs_paths.jsonl").open("w", encoding="utf-8") as f:
        for _, rec in results:
            f.write(json.dumps(rec) + "\n")
    for d in DENSITIES:
        sub = [r for r in rows if r["density"] == d]
        st = {}
        for r in sub:
            st[r["status"]] = st.get(r["status"], 0) + 1
        print(d, "solved", sum(r["success"] for r in sub), "/", len(sub), st)


if __name__ == "__main__":
    main()
