"""Bounded priority-graph search for permanent-space routing.

This is a domain adaptation for static, vertex-capacity routing. It is not a
temporal MAPF solver and should not be reported as canonical MAPF-PBS.
"""

from __future__ import annotations

import random
from collections import deque

from run_routing_experiments import (
    Coord,
    Instance,
    astar,
    estimate_demand,
    objective,
)


def _topological_order(
    count: int, edges: frozenset[tuple[int, int]], tie_order: list[int]
) -> list[int] | None:
    """Return a deterministic linear extension, or None for a cycle."""
    outgoing = [[] for _ in range(count)]
    indegree = [0] * count
    for higher, lower in edges:
        outgoing[higher].append(lower)
        indegree[lower] += 1

    rank = {node: position for position, node in enumerate(tie_order)}
    ready = [node for node, degree in enumerate(indegree) if degree == 0]
    order = []
    while ready:
        ready.sort(key=rank.__getitem__)
        node = ready.pop(0)
        order.append(node)
        for lower in outgoing[node]:
            indegree[lower] -= 1
            if indegree[lower] == 0:
                ready.append(lower)
    return order if len(order) == count else None


def _route_priority_order(
    instance: Instance,
    order: list[int],
    predicted: dict[Coord, float],
) -> tuple[dict[int, list[Coord]], int | None]:
    """Route in priority order and return first failed commodity if any."""
    paths: dict[int, list[Coord]] = {}
    occupied: set[Coord] = set()
    terminals = {
        point
        for item in instance.commodities
        for point in (item.start, item.goal)
    }
    for index in order:
        item = instance.commodities[index]
        forbidden = occupied | (terminals - {item.start, item.goal})
        path = astar(instance, item, forbidden, predicted, 0.0)
        if path is None:
            return paths, index
        paths[index] = path
        occupied.update(path[1:-1])
    return paths, None


def permanent_priority_search(
    instance: Instance, seed: int, max_nodes: int = 128
) -> tuple[dict[int, list[Coord]], int, bool]:
    """Search a bounded tree of pairwise precedence constraints.

    A failed low-priority commodity branches above each earlier commodity,
    approximating permanent-occupancy rip-up decisions with a partial order.
    """
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")

    rng = random.Random(seed)
    tie_order = list(range(len(instance.commodities)))
    rng.shuffle(tie_order)
    predicted = estimate_demand(instance)
    queue = deque([frozenset()])
    seen = {frozenset()}
    best_paths: dict[int, list[Coord]] = {}
    best_score = objective(instance, best_paths)
    expanded = 0

    while queue and expanded < max_nodes:
        constraints = queue.popleft()
        order = _topological_order(len(instance.commodities), constraints, tie_order)
        if order is None:
            continue
        paths, failed = _route_priority_order(instance, order, predicted)
        expanded += 1
        score = objective(instance, paths)
        if score < best_score:
            best_paths, best_score = paths, score
        if failed is None:
            return paths, expanded, True

        failed_position = order.index(failed)
        for earlier in order[:failed_position]:
            branch = constraints | {(failed, earlier)}
            if branch not in seen and _topological_order(
                len(instance.commodities), branch, tie_order
            ) is not None:
                seen.add(branch)
                queue.append(branch)

    return best_paths, expanded, False
