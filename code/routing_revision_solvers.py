"""Auditable permanent-occupancy PBS adaptation and matched LNS controls.

PBS high level follows Ma et al. AAAI 2019 Algorithm 2; spatial occupancy
replaces temporal collisions. LNS controls use the same low-level planner.
"""

from __future__ import annotations

import math
import heapq
import random
import time
from collections import defaultdict
from dataclasses import dataclass

from run_routing_experiments import astar, objective, path_cost


@dataclass(frozen=True)
class SearchBudget:
    """Shared per-method improvement budget, after shared initialization."""

    seconds: float = 1.0
    iterations: int = 20
    nodes: int = 256
    fraction: float = 0.25


class RoutingContext:
    """Route on the unchanged generator with globally protected terminals."""

    def __init__(self, instance, predicted):
        self.instance = instance
        self.predicted = predicted
        self.terminals = {p for c in instance.commodities for p in (c.start, c.goal)}
        self.calls = 0

    def plan(self, index, occupied=(), weight=0.0):
        """Apply identical endpoint protection for every baseline and repair."""
        self.calls += 1
        item = self.instance.commodities[index]
        forbidden = set(occupied) | (self.terminals - {item.start, item.goal})
        return astar(self.instance, item, forbidden, self.predicted, weight)

    def sequential(self, order, kept=None, weight=0.0):
        """Replan a selected neighborhood against all retained paths."""
        paths = dict(kept or {})
        occupied = {v for path in paths.values() for v in path}
        for index in order:
            path = self.plan(index, occupied, weight)
            if path:
                paths[index] = path
                occupied.update(path)
        return paths


def validate_paths(instance, paths):
    """Independently check full occupancy, obstacles, steps and drainage."""
    occupied = set()
    terminals = {v for c in instance.commodities for v in (c.start, c.goal)}
    for index, path in paths.items():
        item = instance.commodities[index]
        if not path or (path[0], path[-1]) != (item.start, item.goal):
            raise ValueError("Endpoint mismatch")
        if len(set(path)) != len(path) or occupied.intersection(path):
            raise ValueError("Repeated/shared occupied vertex")
        if set(path) & (terminals - {item.start, item.goal}):
            raise ValueError("Another service terminal is occupied")
        for node in path:
            if node in instance.blocked or any(x < 0 or x >= n for x, n in zip(node, instance.shape)):
                raise ValueError("Blocked or out-of-domain vertex")
        for a, b in zip(path, path[1:]):
            if sum(abs(x - y) for x, y in zip(a, b)) != 1:
                raise ValueError("Non-adjacent path step")
            if item.discipline == "drainage" and b[2] > a[2]:
                raise ValueError("Drainage rises")
        occupied.update(path)
    return True


def first_conflict(paths):
    """Return a deterministic pair sharing a permanently occupied vertex."""
    owner = {}
    for index in sorted(paths):
        for node in paths[index]:
            if node in owner:
                return owner[node], index
            owner[node] = index
    return None


def closure(edges, count):
    """Return ancestors and a stable topological order, rejecting cycles."""
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


def update_plan(context, paths, edges, changed):
    """Replan the lower-priority service and affected descendants in order."""
    result = closure(edges, len(context.instance.commodities))
    if result is None:
        return None
    ancestors, order = result
    paths = dict(paths)
    for index in order:
        if index != changed and changed not in ancestors[index]:
            continue
        occupied = {v for high in ancestors[index] for v in paths[high]}
        if index == changed or occupied.intersection(paths[index]):
            path = context.plan(index, occupied)
            if path is None:
                return None
            paths[index] = path
    return paths


def feasible_subset(paths):
    """Extract a valid incumbent from a conflicting priority-tree node."""
    kept, occupied = {}, set()
    for index in sorted(paths, key=lambda i: (len(paths[i]), i)):
        if not occupied.intersection(paths[index]):
            kept[index] = paths[index]
            occupied.update(paths[index])
    return kept


def pbs(context, initial, budget):
    """DFS over conflict-triggered partial priorities with two child orders."""
    started = time.perf_counter()
    deadline = started + budget.seconds
    best = dict(initial)
    roots = {i: context.plan(i) for i in range(len(context.instance.commodities))}
    if any(path is None for path in roots.values()):
        return best, [{"t": time.perf_counter() - started, "objective": objective(context.instance, best)}], {"status": "individual_infeasible", "nodes": 0}
    stack = [(frozenset(), roots)]
    trace, expanded = [], 0
    status = "exhausted"
    while stack:
        if time.perf_counter() >= deadline or expanded >= budget.nodes:
            status = "budget"
            break
        edges, paths = stack.pop()
        expanded += 1
        subset = feasible_subset(paths)
        if objective(context.instance, subset) < objective(context.instance, best):
            best = subset
        pair = first_conflict(paths)
        trace.append({"t": time.perf_counter() - started, "objective": objective(context.instance, best)})
        if pair is None:
            if objective(context.instance, paths) < objective(context.instance, best):
                best = paths
            status = "solved"
            break
        children = []
        for high, low in (pair, tuple(reversed(pair))):
            child_edges = edges | {(high, low)}
            child_paths = update_plan(context, paths, child_edges, low)
            if child_paths is not None:
                cost = sum(path_cost(p, context.instance.commodities[i]) for i, p in child_paths.items())
                children.append((cost, child_edges, child_paths))
        stack.extend((e, p) for _, e, p in sorted(children, key=lambda x: x[0], reverse=True))
    return best, trace, {"status": status, "nodes": expanded}


def spatial_cbs(context, budget):
    """Run CBS over permanent shared-voxel conflicts, not temporal conflicts."""
    started = time.perf_counter()
    deadline = started + budget.seconds
    terminals = context.terminals
    root_constraints = {}
    root_paths = {}
    for index in range(len(context.instance.commodities)):
        if time.perf_counter() >= deadline:
            return {}, [], {"status": "budget", "nodes": 0}
        path = context.plan(index, terminals - {
            context.instance.commodities[index].start,
            context.instance.commodities[index].goal,
        })
        if path is None:
            return {}, [], {"status": "individual_infeasible", "nodes": 0}
        root_paths[index] = path

    nodes = [(objective(context.instance, root_paths), 0, root_constraints, root_paths)]
    seen = {()}
    expanded = 0
    trace = []
    while nodes and expanded < budget.nodes and time.perf_counter() < deadline:
        _, _, constraints, paths = heapq.heappop(nodes)
        expanded += 1
        conflict = first_conflict(paths)
        trace.append({"t": time.perf_counter() - started,
                      "objective": objective(context.instance, paths)})
        if conflict is None:
            return paths, trace, {"status": "solved", "nodes": expanded}
        for agent in conflict:
            vertex = next(v for v in paths[conflict[0]] if v in paths[conflict[1]])
            child_constraints = {key: set(value) for key, value in constraints.items()}
            child_constraints.setdefault(agent, set()).add(vertex)
            signature = tuple((key, tuple(sorted(value)))
                              for key, value in sorted(child_constraints.items()))
            if signature in seen:
                continue
            seen.add(signature)
            item = context.instance.commodities[agent]
            forbidden = terminals - {item.start, item.goal}
            forbidden |= child_constraints[agent]
            route = context.plan(agent, forbidden)
            if route is None:
                continue
            child_paths = dict(paths)
            child_paths[agent] = route
            heapq.heappush(nodes, (
                objective(context.instance, child_paths), len(seen),
                child_constraints, child_paths,
            ))
    status = "budget" if nodes else "exhausted"
    return {}, trace, {"status": status, "nodes": expanded}


def blocker_graph(context, paths, probes):
    """Count actual incumbent intersections with failed unconstrained paths."""
    scores = defaultdict(float)
    neighbors = defaultdict(set)
    for failed, probe in probes.items():
        if failed in paths or probe is None:
            continue
        for routed, path in paths.items():
            overlap = len(set(probe).intersection(path))
            if overlap:
                scores[routed] += overlap
                scores[failed] += overlap
                neighbors[failed].add(routed)
                neighbors[routed].add(failed)
    return scores, neighbors


def select_neighborhood(context, paths, probes, config):
    """Select random, ranked, blocker or conflict-graph neighborhoods."""
    method, count, rng = config
    indices = list(range(len(context.instance.commodities)))
    failed = [i for i in indices if i not in paths]
    if method == "random":
        return rng.sample(indices, count)
    if method == "length":
        scores = {i: len(paths.get(i, [])) for i in indices}
    elif method == "guided":
        load = defaultdict(int)
        for path in paths.values():
            for node in path:
                load[node] += 1
        scores = {i: sum(context.predicted.get(v, 0) + load[v] for v in paths.get(i, [])) for i in indices}
    elif method in {"blocker", "conflict"}:
        scores, _ = blocker_graph(context, paths, probes)
    else:
        raise ValueError(f"Unknown neighborhood selector: {method}")
    for i in failed:
        scores[i] = scores.get(i, 0.0) + 1000.0
    tie = {i: rng.random() for i in indices}
    if method == "conflict":
        _, neighbors = blocker_graph(context, paths, probes)
        selected = []
        frontier = sorted(indices, key=lambda i: (scores.get(i, 0), tie[i]), reverse=True)
        while frontier and len(selected) < count:
            current = frontier.pop(0)
            if current in selected:
                continue
            selected.append(current)
            frontier.extend(sorted(neighbors[current] - set(selected),
                                   key=lambda i: (scores.get(i, 0), tie[i]), reverse=True))
            frontier = list(dict.fromkeys(frontier))
        if len(selected) < count:
            selected.extend(i for i in sorted(indices,
                             key=lambda i: (scores.get(i, 0), tie[i]), reverse=True)
                            if i not in selected)
        return selected[:count]
    return sorted(indices, key=lambda i: (scores.get(i, 0), tie[i]), reverse=True)[:count]


def lns(context, initial, method, seed, budget):
    """Compare selectors with matched repair, acceptance and terminal policy."""
    started = time.perf_counter()
    rng = random.Random(seed)
    paths = dict(initial)
    probes = {i: context.plan(i) for i in range(len(context.instance.commodities))}
    trace = [{"t": 0.0, "objective": objective(context.instance, paths)}]
    weights = {name: 1.0 for name in ("random", "length", "blocker", "conflict")}
    for step in range(budget.iterations):
        if time.perf_counter() - started >= budget.seconds:
            break
        if method == "adaptive":
            operator = rng.choices(list(weights), list(weights.values()))[0]
        else:
            operator = {"guided_select_only": "guided", "static_random": "random"}.get(method, method)
        fraction = min(0.6, budget.fraction + 0.05 * (step // 5)) if method == "adaptive" else budget.fraction
        count = min(len(probes), max(2, math.ceil(len(probes) * fraction)))
        selected = select_neighborhood(context, paths, probes, (operator, count, rng))
        rng.shuffle(selected)
        selected.sort(key=lambda i: i in paths)
        kept = {i: p for i, p in paths.items() if i not in selected}
        candidate = context.sequential(selected, kept, weight=2.0 if method in {"guided", "static_random"} else 0.0)
        before, after = objective(context.instance, paths), objective(context.instance, candidate)
        weights[operator] = 0.95 * weights.get(operator, 1.0) + (1.0 if after < before else 0.05)
        if after <= before:
            paths = candidate
        trace.append({"t": time.perf_counter() - started, "objective": objective(context.instance, paths)})
    return paths, trace, {"status": "budget" if len(trace) <= budget.iterations else "iterations", "nodes": 0}
