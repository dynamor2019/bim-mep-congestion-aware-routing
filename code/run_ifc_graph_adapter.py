"""Run the manuscript's unit-occupancy repair logic on one IFC-derived graph."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def load_graph(path: Path) -> tuple[dict, dict[int, list[tuple[int, float]]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    adjacency = defaultdict(list)
    for edge in data["edges"]:
        adjacency[edge["from"]].append((edge["to"], float(edge["length"])))
    return data, adjacency


def demand_field(data: dict, blocked: set[int] | None = None) -> dict[int, float]:
    blocked = blocked or set()
    coords = {v["id"]: (v["x"], v["y"], v["z"]) for v in data["vertices"]}
    demand = defaultdict(float)
    for item in data["commodities"]:
        a, b = coords[item["source"]], coords[item["destination"]]
        candidates = []
        for node, point in coords.items():
            if node in blocked:
                continue
            if all(min(x, y) <= z <= max(x, y) for x, y, z in zip(a, b, point)):
                candidates.append(node)
        if candidates:
            contribution = math.dist(a, b) / len(candidates)
            for node in candidates:
                demand[node] += contribution
    return demand


def shortest_path(data: dict, adjacency: dict[int, list[tuple[int, float]]], item: dict,
                  occupied: set[int], predicted: dict[int, float], weight: float) -> list[int] | None:
    goal = item["destination"]
    queue = [(0.0, 0.0, item["source"])]
    parent: dict[int, int | None] = {item["source"]: None}
    best = {item["source"]: 0.0}
    coords = {v["id"]: (v["x"], v["y"], v["z"]) for v in data["vertices"]}
    while queue:
        _, cost, node = heapq.heappop(queue)
        if cost != best.get(node):
            continue
        if node == goal:
            path = []
            cursor: int | None = node
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            return list(reversed(path))
        for nxt, length in adjacency.get(node, []):
            if nxt in occupied and nxt != goal:
                continue
            congestion = weight * predicted.get(nxt, 0.0)
            new_cost = cost + length + congestion
            if new_cost < best.get(nxt, math.inf):
                best[nxt] = new_cost
                parent[nxt] = node
                heuristic = math.dist(coords[nxt], coords[goal])
                heapq.heappush(queue, (new_cost + heuristic, new_cost, nxt))
    return None


def objective(paths: dict[int, list[int]], n_items: int) -> float:
    return (n_items - len(paths)) * 10000.0 + sum(len(path) - 1 for path in paths.values())


def route_order(data: dict, adjacency: dict[int, list[tuple[int, float]]], order: list[int],
                predicted: dict[int, float], weight: float) -> dict[int, list[int]]:
    paths, occupied = {}, set()
    terminals = {x["source"] for x in data["commodities"]} | {x["destination"] for x in data["commodities"]}
    for index in order:
        item = data["commodities"][index]
        path = shortest_path(data, adjacency, item, occupied | (terminals - {item["source"], item["destination"]}), predicted, weight)
        if path:
            paths[index] = path
            occupied.update(path[1:-1])
    return paths


def repair(data: dict, adjacency: dict[int, list[tuple[int, float]]], paths: dict[int, list[int]],
           predicted: dict[int, float], guided: bool, rng: random.Random) -> dict[int, list[int]]:
    paths = dict(paths)
    for _ in range(5):
        load = defaultdict(int)
        for path in paths.values():
            for node in path:
                load[node] += 1
        scores = {i: sum(load[node] + predicted.get(node, 0.0) for node in paths.get(i, [])) for i in range(len(data["commodities"]))}
        count = max(2, math.ceil(len(data["commodities"]) * 0.25))
        selected = sorted(scores, key=scores.get, reverse=True)[:count] if guided else rng.sample(range(len(data["commodities"])), count)
        candidate = {i: p for i, p in paths.items() if i not in selected}
        occupied = {node for path in candidate.values() for node in path[1:-1]}
        for i in sorted(selected, key=scores.get, reverse=True):
            path = shortest_path(data, adjacency, data["commodities"][i], occupied, predicted, 2.0 if guided else 0.0)
            if path:
                candidate[i] = path
                occupied.update(path[1:-1])
        if objective(candidate, len(data["commodities"])) <= objective(paths, len(data["commodities"])):
            paths = candidate
    return paths


def run(data: dict, adjacency: dict[int, list[tuple[int, float]]], seed: int) -> list[dict]:
    rng = random.Random(seed)
    n = len(data["commodities"])
    predicted = demand_field(data)
    order = list(range(n))
    rng.shuffle(order)
    base = route_order(data, adjacency, order, predicted, 0.0)
    guided = repair(data, adjacency, base, predicted, True, rng)
    random_paths = repair(data, adjacency, base, predicted, False, rng)
    return [
        {"seed": seed, "method": "MSPP_random_repair", "routed": len(random_paths), "objective": objective(random_paths, n)},
        {"seed": seed, "method": "MSPP_guided_repair", "routed": len(guided), "objective": objective(guided, n)},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph", type=Path)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("results_ifc_adapter"))
    args = parser.parse_args()
    data, adjacency = load_graph(args.graph)
    rows = [row for seed in range(args.seeds) for row in run(data, adjacency, seed)]
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "ifc_adapter_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "manifest.json").write_text(json.dumps({"graph": str(args.graph), "seeds": args.seeds, "n_commodities": len(data["commodities"]), "metadata": data["metadata"]}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
