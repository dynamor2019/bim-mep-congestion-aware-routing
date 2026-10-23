"""Stress-test the current router with a one-cell service envelope."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import random
import sys
from collections import defaultdict
from pathlib import Path


def load_router(path: Path):
    spec = importlib.util.spec_from_file_location("router", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def envelope(path, radius: int, shape: tuple[int, int, int]) -> set[tuple[int, int, int]]:
    result = set()
    for x, y, z in path[1:-1]:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    point = x + dx, y + dy, z + dz
                    if all(0 <= value < limit for value, limit in zip(point, shape)):
                        result.add(point)
    return result


def route_order(router, instance, order, predicted, weight, radius):
    paths = {}
    occupied = set()
    terminals = {item.start for item in instance.commodities} | {item.goal for item in instance.commodities}
    for index in order:
        item = instance.commodities[index]
        forbidden = occupied | (terminals - {item.start, item.goal})
        path = router.astar(instance, item, forbidden, predicted, weight)
        if path is not None:
            paths[index] = path
            occupied.update(envelope(path, radius, instance.shape))
    return paths


def solve(router, instance, method, seed, radius):
    rng = random.Random(seed)
    predicted = router.estimate_demand(instance)
    indices = list(range(len(instance.commodities)))
    candidates = []
    for _ in range(2):
        rng.shuffle(indices)
        weight = 2.0 if method == "guided" else 0.0
        candidates.append(route_order(router, instance, list(indices), predicted, weight, radius))
    paths = min(candidates, key=lambda value: router.objective(instance, value))
    for _ in range(5):
        load = defaultdict(int)
        for path in paths.values():
            load.update({node: load[node] + 1 for node in envelope(path, radius, instance.shape)})
        scores = {i: sum(load[node] + predicted.get(node, 0.0) for node in envelope(paths.get(i, []), radius, instance.shape)) + (1000.0 if i not in paths else 0.0) for i in range(len(instance.commodities))}
        count = max(2, math.ceil(len(instance.commodities) * 0.25))
        selected = sorted(scores, key=scores.get, reverse=True)[:count] if method == "guided" else rng.sample(range(len(instance.commodities)), count)
        kept = {i: p for i, p in paths.items() if i not in selected}
        occupied = {node for p in kept.values() for node in envelope(p, radius, instance.shape)}
        candidate = dict(kept)
        for i in sorted(selected, key=scores.get, reverse=True):
            path = router.astar(instance, instance.commodities[i], occupied, predicted, 2.0 if method == "guided" else 0.0)
            if path is not None:
                candidate[i] = path
                occupied.update(envelope(path, radius, instance.shape))
        if router.objective(instance, candidate) <= router.objective(instance, paths):
            paths = candidate
    return len(paths), router.objective(instance, paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("router", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seeds", type=int, default=30)
    args = parser.parse_args()
    router = load_router(args.router)
    rows = []
    for density in ("low", "medium", "high"):
        for seed in range(args.seeds):
            instance = router.generate_instance(density, seed)
            for radius in (0, 1):
                for method in ("random", "guided"):
                    routed, objective = solve(router, instance, method, seed, radius)
                    rows.append({"density": density, "seed": seed, "radius_cells": radius, "method": method, "routed": routed, "n_systems": len(instance.commodities), "success": int(routed == len(instance.commodities)), "objective": objective})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    print(f"rows={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
