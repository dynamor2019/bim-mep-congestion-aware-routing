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

    def plan(self, index, occupied=(), weight=0.0, soft_occupied_weight=0.0):
        """Apply identical endpoint protection for every baseline and repair."""
        self.calls += 1
        item = self.instance.commodities[index]
        forbidden = set(occupied) | (self.terminals - {item.start, item.goal})
        return astar(self.instance, item, forbidden, self.predicted, weight,
                     soft_occupied_weight)

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


def _cbs_signature(constraints, dropped):
    return (tuple((i, tuple(sorted(nodes)))
                  for i, nodes in sorted(constraints.items())),
            tuple(sorted(dropped)))


def _cbs_child(context, constraints, dropped, paths, agent, vertex):
    child_constraints = {i: set(nodes) for i, nodes in constraints.items()}
    child_constraints.setdefault(agent, set()).add(vertex)
    child_dropped = set(dropped)
    child_paths = dict(paths)
    route = context.plan(agent, child_constraints[agent])
    if route is None:
        child_dropped.add(agent)
        child_paths.pop(agent, None)
    else:
        child_paths[agent] = route
    return child_constraints, child_dropped, child_paths


def spatial_cbs(context, budget, initial=None):
    """Search permanent vertex conflicts from a shared partial incumbent."""
    started = time.perf_counter()
    deadline = started + budget.seconds
    best = dict(initial or {})
    best_cost = objective(context.instance, best)
    constraints, dropped, paths = {}, set(), dict(initial or {})
    for index in range(len(context.instance.commodities)):
        if index in paths:
            continue
        if time.perf_counter() >= deadline:
            return best, [], {"status": "budget", "nodes": 0}
        route = context.plan(index)
        if route is None:
            dropped.add(index)
        else:
            paths[index] = route
    priority = objective(context.instance, paths)
    nodes = [(priority, 0, constraints, dropped, paths)]
    seen = {_cbs_signature(constraints, dropped)}
    candidate = feasible_subset(paths)
    if objective(context.instance, candidate) < best_cost:
        best, best_cost = candidate, objective(context.instance, candidate)
    expanded, trace = 0, []
    while nodes and expanded < budget.nodes and time.perf_counter() < deadline:
        _, _, constraints, dropped, paths = heapq.heappop(nodes)
        expanded += 1
        candidate = feasible_subset(paths)
        if objective(context.instance, candidate) < best_cost:
            best, best_cost = candidate, objective(context.instance, candidate)
        conflict = first_conflict(paths)
        trace.append({"t": time.perf_counter() - started,
                      "objective": objective(context.instance, paths)})
        if conflict is None:
            return paths, trace, {"status": "solved", "nodes": expanded}
        vertex = next(v for v in paths[conflict[0]] if v in paths[conflict[1]])
        for agent in conflict:
            child = _cbs_child(context, constraints, dropped, paths, agent, vertex)
            signature = _cbs_signature(child[0], child[1])
            if signature in seen:
                continue
            seen.add(signature)
            heapq.heappush(nodes, (objective(context.instance, child[2]),
                                   len(seen), *child))
    status = "budget" if nodes else "exhausted"
    return best, trace, {"status": status, "nodes": expanded}


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


def route_conflict_graph(paths):
    """Build static conflict adjacency and overlap counts for current routes."""
    owners = defaultdict(set)
    for index, path in paths.items():
        for node in set(path):
            owners[node].add(index)
    scores = defaultdict(int)
    neighbors = defaultdict(set)
    for indices in owners.values():
        for index in indices:
            for other in indices - {index}:
                scores[index] += 1
                neighbors[index].add(other)
    return scores, neighbors


def route_conflict_count(paths):
    """Count pairwise permanent-occupancy conflicts by shared voxel."""
    scores, _ = route_conflict_graph(paths)
    return sum(scores.values()) // 2


def spatial_lns2(context, initial, seed, budget):
    """Adapt LNS2 destroy-repair to permanent vertex occupancy."""
    started = time.perf_counter()
    deadline = started + budget.seconds
    rng = random.Random(seed)
    paths = dict(initial)
    for index in range(len(context.instance.commodities)):
        if index in paths:
            continue
        occupied = {node for path in paths.values() for node in path}
        path = context.plan(index, occupied, soft_occupied_weight=1000.0)
        if path:
            paths[index] = path

    def quality(candidate):
        missing = len(context.instance.commodities) - len(candidate)
        conflicts = route_conflict_count(candidate)
        cost = sum(path_cost(path, context.instance.commodities[i])
                   for i, path in candidate.items())
        return missing, conflicts, cost

    trace = [{"t": time.perf_counter() - started, "objective": objective(context.instance, initial),
              "conflicts": route_conflict_count(paths)}]
    best_valid = dict(initial)
    best_valid_objective = objective(context.instance, best_valid)
    steps = 0
    while steps < budget.iterations and time.perf_counter() < deadline:
        scores, neighbors = route_conflict_graph(paths)
        conflicted = [index for index in paths if scores.get(index, 0)]
        if not conflicted:
            conflicted = [index for index in range(len(context.instance.commodities))
                          if index not in paths]
        if not conflicted:
            conflicted = list(range(len(context.instance.commodities)))
        count = min(len(context.instance.commodities),
                    max(2, math.ceil(len(context.instance.commodities) * budget.fraction)))
        selected = []
        frontier = list(conflicted)
        while frontier and len(selected) < count:
            frontier.sort(key=lambda i: (scores.get(i, 0), rng.random()), reverse=True)
            current = frontier.pop(0)
            if current in selected:
                continue
            selected.append(current)
            frontier.extend(neighbors[current] - set(selected))
        if len(selected) < count:
            remaining = [i for i in range(len(context.instance.commodities))
                         if i not in selected]
            rng.shuffle(remaining)
            selected.extend(remaining[:count - len(selected)])
        rng.shuffle(selected)
        selected.sort(key=lambda i: i in paths)
        kept = {i: path for i, path in paths.items() if i not in selected}
        candidate = dict(kept)
        for index in selected:
            occupied = {node for path in candidate.values() for node in path}
            path = context.plan(index, occupied, soft_occupied_weight=1000.0)
            if path:
                candidate[index] = path
        if quality(candidate) < quality(paths):
            paths = candidate
        if route_conflict_count(paths) == 0:
            value = objective(context.instance, paths)
            if value < best_valid_objective:
                best_valid, best_valid_objective = dict(paths), value
        steps += 1
        trace.append({"t": time.perf_counter() - started,
                      "objective": objective(context.instance, best_valid),
                      "conflicts": route_conflict_count(paths)})
    return best_valid, trace, {"status": "budget", "nodes": steps,
                               "residual_conflicts": route_conflict_count(paths)}


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
    if method == "spatial_mapf_lns2":
        return spatial_lns2(context, initial, seed, budget)
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
