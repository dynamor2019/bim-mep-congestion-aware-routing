"""Exact permanent-occupancy multi-commodity routing benchmark.

The MILP optimizes unrouted penalties plus unit and vertical-step costs.
Reported physical costs are recomputed with the full route-cost function.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from run_routing_experiments import (
    Instance,
    generate_instance,
    objective,
    solution_cost,
)
from routing_revision_solvers import validate_paths


def solve_exact_mcf(
    instance: Instance,
    time_limit_s: float = 5.0,
    failure_penalty: float = 10000.0,
) -> tuple[dict[int, list[tuple[int, int, int]]], dict]:
    """Solve vertex-disjoint paths exactly, with per-route failure penalties."""
    if time_limit_s <= 0 or failure_penalty <= 0:
        raise ValueError("time_limit_s and failure_penalty must be positive")

    terminals = {node for item in instance.commodities for node in (item.start, item.goal)}
    node_rows: list[tuple[int, tuple[int, int, int]]] = []
    row_index = {}
    allowed_nodes = []
    for index, item in enumerate(instance.commodities):
        forbidden = terminals - {item.start, item.goal}
        allowed = {
            node for node in np.ndindex(instance.shape)
            if node not in instance.blocked and node not in forbidden
        }
        allowed_nodes.append(allowed)
        for node in sorted(allowed):
            row_index[index, node] = len(node_rows)
            node_rows.append((index, node))

    arc_vars: list[tuple[int, tuple[int, int, int], tuple[int, int, int], float]] = []
    for index, item in enumerate(instance.commodities):
        allowed = allowed_nodes[index]
        for node in sorted(allowed):
            if node == item.goal:
                continue
            for neighbor in _neighbors(node, instance.shape):
                if neighbor not in allowed or neighbor == item.start:
                    continue
                if item.discipline == "drainage" and neighbor[2] > node[2]:
                    continue
                vertical_cost = item.vertical_cost if neighbor[2] != node[2] else 0.0
                var = len(arc_vars)
                arc_vars.append((index, node, neighbor, 1.0 + vertical_cost))

    y_offset = len(arc_vars)
    n_vars = y_offset + len(instance.commodities)
    n_flow_rows = len(node_rows)
    vertex_rows = {
        node: n_flow_rows + offset
        for offset, node in enumerate(sorted(set().union(*allowed_nodes)))
    }
    rows, cols, values = [], [], []
    lower = np.zeros(n_flow_rows + len(vertex_rows))
    upper = np.zeros_like(lower)
    upper[n_flow_rows:] = 1.0

    for var, (index, start, goal, _) in enumerate(arc_vars):
        rows.extend((row_index[index, start], row_index[index, goal], vertex_rows[goal]))
        cols.extend((var, var, var))
        values.extend((1.0, -1.0, 1.0))
    for index, item in enumerate(instance.commodities):
        y_var = y_offset + index
        rows.extend((row_index[index, item.start], row_index[index, item.goal], vertex_rows[item.start]))
        cols.extend((y_var, y_var, y_var))
        values.extend((-1.0, 1.0, 1.0))

    matrix = coo_array(
        (values, (rows, cols)),
        shape=(len(lower), n_vars),
    ).tocsr()
    # Flow rows equal zero; shared-vertex rows are bounded above by one.
    flow_upper = np.zeros(n_flow_rows)
    constraints = LinearConstraint(matrix, lower, np.concatenate((flow_upper, upper[n_flow_rows:])))
    costs = np.zeros(n_vars)
    for var, (_, _, _, edge_cost) in enumerate(arc_vars):
        costs[var] = edge_cost
    costs[y_offset:] = -failure_penalty

    result = milp(
        c=costs,
        integrality=np.ones(n_vars),
        bounds=Bounds(np.zeros(n_vars), np.ones(n_vars)),
        constraints=constraints,
        options={"time_limit": time_limit_s, "mip_rel_gap": 0.0},
    )
    paths = _extract_paths(instance, arc_vars, result.x, y_offset)
    validate_paths(instance, paths)
    return paths, {
        "status": _status_name(result.status),
        "message": result.message,
        "nodes": int(getattr(result, "mip_node_count", 0) or 0),
        "mip_gap": getattr(result, "mip_gap", None),
        "solver_objective": result.fun,
        "n_variables": n_vars,
        "n_constraints": matrix.shape[0],
    }


def _extract_paths(instance, arcs, solution, y_offset):
    """Decode the selected unit flows into ordered vertex paths."""
    if solution is None:
        return {}
    selected = [[] for _ in instance.commodities]
    for var, (index, start, goal, _) in enumerate(arcs):
        if solution[var] > 0.5:
            selected[index].append((start, goal))
    result = {}
    for index, item in enumerate(instance.commodities):
        if solution[y_offset + index] <= 0.5:
            continue
        successors = {start: goal for start, goal in selected[index]}
        path = [item.start]
        while path[-1] != item.goal:
            nxt = successors.get(path[-1])
            if nxt is None or nxt in path:
                raise ValueError("MILP returned a disconnected or cyclic unit flow")
            path.append(nxt)
        result[index] = path
    return result


def _neighbors(node, shape):
    x, y, z = node
    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        neighbor = (x + dx, y + dy, z + dz)
        if all(0 <= value < limit for value, limit in zip(neighbor, shape)):
            yield neighbor


def _status_name(status):
    return {0: "optimal", 1: "limit", 2: "infeasible", 3: "unbounded", 4: "solver_error"}.get(status, "unknown")


def run_batch(seeds, start_seed, time_limit_s, output):
    """Solve a matched high-density cohort and write auditable observations."""
    output.mkdir(parents=True, exist_ok=True)
    fields = ["seed", "scene_hash", "success", "routed", "total", "physical_cost", "objective",
              "runtime_s", "status", "nodes", "mip_gap", "n_variables", "n_constraints", "validated"]
    from run_revision_benchmark import fingerprint

    with (output / "raw.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for seed in range(start_seed, start_seed + seeds):
            instance = generate_instance("high", seed)
            started = time.perf_counter()
            paths, info = solve_exact_mcf(instance, time_limit_s=time_limit_s)
            elapsed = time.perf_counter() - started
            writer.writerow({
                "seed": seed, "scene_hash": fingerprint(instance),
                "success": int(len(paths) == len(instance.commodities)),
                "routed": len(paths), "total": len(instance.commodities),
                "physical_cost": solution_cost(instance, paths),
                "objective": objective(instance, paths), "runtime_s": elapsed,
                "status": info["status"], "nodes": info["nodes"], "mip_gap": info["mip_gap"],
                "n_variables": info["n_variables"], "n_constraints": info["n_constraints"],
                "validated": 1,
            })
            stream.flush()
            print(f"exact_mcf: {seed - start_seed + 1}/{seeds} status={info['status']} routed={len(paths)}/{len(instance.commodities)}", flush=True)


def main():
    """Run an exact-flow benchmark cohort from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--start-seed", type=int, default=100000)
    parser.add_argument("--time-limit", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds <= 0 or args.time_limit <= 0:
        parser.error("--seeds and --time-limit must be positive")
    run_batch(args.seeds, args.start_seed, args.time_limit, args.output)


if __name__ == "__main__":
    main()
