"""Faithful spatial PBS (Priority-Based Search, Ma et al. AAAI 2019) for permanent occupancy.

Best-first search over the priority tree. Each node holds a partial order on agents.
When two routes share an interior voxel, branch by assigning priority (i>j or j>i);
the lower-priority agent replans avoiding the higher-priority agent's path.
No node limit; per-scene wall-clock deadline.
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


class Timeout(Exception):
    pass


def find_conflict(paths):
    """Return (agent_a, agent_b) for the smallest shared interior voxel, else None."""
    owners = {}
    for index in sorted(paths):
        for node in paths[index][1:-1]:
            if node in owners:
                return owners[node], index
            owners[node] = index
    return None


def closure(edges, count):
    """Return (ancestors, topological_order) or None if cyclic."""
    ancestors = {i: set() for i in range(count)}
    children = {i: set() for i in range(count)}
    for high, low in edges:
        ancestors[low].add(high)
        children[high].add(low)
    indegree = {i: len(ancestors[i]) for i in ancestors}
    ready = sorted(i for i in indegree if not indegree[i])
    order = []
    while ready:
        index = ready.pop(0)
        order.append(index)
        for child in sorted(children[index]):
            ancestors[child].update(ancestors[index])
            indegree[child] -= 1
            if not indegree[child]:
                ready.append(child)
                ready.sort()
    return (ancestors, order) if len(order) == count else None


def pbs(instance, deadline):
    """Return (paths|None, status, expanded, generated)."""
    demand = estimate_demand(instance)
    terminals = {p for c in instance.commodities for p in (c.start, c.goal)}
    n = len(instance.commodities)

    def plan(index, occupied):
        item = instance.commodities[index]
        forbidden = (terminals - {item.start, item.goal}) | set(occupied)
        route = astar(instance, item, forbidden, demand, 0.0, deadline=deadline)
        if route is None and time.perf_counter() >= deadline:
            raise Timeout
        return route

    expanded = generated = 0
    try:
        # Root: plan all independently
        root_paths = {}
        for index in range(n):
            route = plan(index, set())
            if route is None:
                return None, "root_infeasible", 0, 0
            root_paths[index] = route
        # Depth-first over the priority tree (Ma et al. [27]): both children are
        # pushed, the lower-cost child last so that it is expanded first.
        stack = [(frozenset(), root_paths)]
        seen = {frozenset()}
        generated = 1
        while stack:
            if time.perf_counter() >= deadline:
                raise Timeout
            edges, paths = stack.pop()
            expanded += 1
            conflict = find_conflict(paths)
            if conflict is None:
                return paths, "solved", expanded, generated
            i, j = conflict
            children = []
            for high, low in ((i, j), (j, i)):
                child_edges = edges | {(high, low)}
                sig = frozenset(child_edges)
                if sig in seen:
                    continue
                seen.add(sig)
                result = closure(child_edges, n)
                if result is None:
                    continue  # cyclic priority — skip
                ancestors, order = result
                # Replan the changed agent and affected descendants
                child_paths = dict(paths)
                feasible = True
                for index in order:
                    if index != low and low not in ancestors.get(index, set()):
                        continue
                    occupied = {v for a in ancestors.get(index, set()) for v in child_paths.get(a, [])}
                    if index == low or occupied.intersection(child_paths.get(index, [])):
                        route = plan(index, occupied)
                        if route is None:
                            feasible = False
                            break
                        child_paths[index] = route
                if not feasible:
                    continue
                child_cost = sum(path_cost(p, instance.commodities[a]) for a, p in child_paths.items())
                generated += 1
                children.append((child_cost, child_edges, child_paths))
            # Push higher-cost child first so the lower-cost child is popped next.
            for _, child_edges, child_paths in sorted(children, key=lambda c: c[0], reverse=True):
                stack.append((child_edges, child_paths))
        return None, "search_exhausted", expanded, generated
    except Timeout:
        return None, "timeout", expanded, generated


def run_one(task):
    density, seed, budget = task
    instance = generate_instance(density, 10000 * DENSITIES.index(density) + seed)
    started = time.perf_counter()
    paths, status, expanded, generated = pbs(instance, started + budget)
    runtime = time.perf_counter() - started
    valid = None
    if paths is not None:
        validate_paths(instance, paths)
        valid = 1
    cost = sum(path_cost(p, instance.commodities[i]) for i, p in paths.items()) if paths else 0.0
    total = len(instance.commodities)
    return {
        "density": density, "seed": seed, "method": "spatial_pbs",
        "routed": total if paths else 0, "total": total, "success": int(paths is not None),
        "cost": cost, "objective": (0 if paths else total) * 10000.0 + cost,
        "runtime_s": round(runtime, 4), "expanded": expanded, "generated": generated,
        "status": status, "validated": valid, "deadline_s": budget,
    }, {"density": density, "seed": seed,
        "paths": {str(i): p for i, p in paths.items()} if paths else None}


def main():
    import argparse, csv
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
    with (args.output / "spatial_pbs_raw.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with (args.output / "spatial_pbs_paths.jsonl").open("w", encoding="utf-8") as f:
        for _, rec in results: f.write(json.dumps(rec) + "\n")
    for d in DENSITIES:
        sub = [r for r in rows if r["density"] == d]
        st = {}
        for r in sub: st[r["status"]] = st.get(r["status"], 0) + 1
        print(d, "solved", sum(r["success"] for r in sub), "/", len(sub), st)


if __name__ == "__main__":
    main()
