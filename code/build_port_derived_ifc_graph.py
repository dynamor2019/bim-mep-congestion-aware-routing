"""Build a reproducible port-derived routing graph from an IFC MEP model."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import ifcopenshell
import numpy as np
from ifcopenshell.util.placement import get_local_placement
from scipy.spatial import cKDTree


def port_points(model) -> tuple[list[dict], dict[int, int]]:
    vertices = []
    ids = {}
    for port in model.by_type("IfcDistributionPort"):
        if port.ObjectPlacement is None:
            continue
        xyz = get_local_placement(port.ObjectPlacement)[:3, 3] / 1000.0
        ids[port.id()] = len(vertices)
        vertices.append({"id": len(vertices), "x": float(xyz[0]), "y": float(xyz[1]), "z": float(xyz[2]), "ifc_id": port.id()})
    return vertices, ids


def connected_edges(model, ids: dict[int, int]) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for relation in model.by_type("IfcRelConnectsPorts"):
        a = ids.get(relation.RelatingPort.id())
        b = ids.get(relation.RelatedPort.id())
        if a is not None and b is not None and a != b:
            edges.add((a, b)); edges.add((b, a))
    return edges


def add_geometric_edges(vertices: list[dict], edges: set[tuple[int, int]], k: int, radius: float) -> None:
    points = np.array([[v["x"], v["y"], v["z"]] for v in vertices])
    tree = cKDTree(points)
    for i, point in enumerate(points):
        distances, neighbors = tree.query(point, k=min(k + 1, len(points)))
        for distance, j in zip(np.atleast_1d(distances)[1:], np.atleast_1d(neighbors)[1:]):
            if float(distance) <= radius:
                edges.add((i, int(j))); edges.add((int(j), i))


def choose_pairs(vertices: list[dict], edges: set[tuple[int, int]], count: int) -> list[dict]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        adjacency[a].append(b)
    seen: set[int] = set(); pairs = []
    for start in range(len(vertices)):
        if start in seen or not adjacency[start]:
            continue
        component = []; queue = deque([start]); seen.add(start)
        while queue:
            node = queue.popleft(); component.append(node)
            for nxt in adjacency[node]:
                if nxt not in seen:
                    seen.add(nxt); queue.append(nxt)
        if len(component) < 12:
            continue
        ordered = sorted(component, key=lambda i: vertices[i]["x"])
        for a, b in zip(ordered[:count], ordered[-count:]):
            if a != b:
                pairs.append({"source": a, "destination": b})
        if len(pairs) >= count:
            break
    return pairs[:count]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ifc", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pairs", type=int, default=20)
    args = parser.parse_args()
    model = ifcopenshell.open(args.ifc)
    vertices, ids = port_points(model)
    edges = connected_edges(model, ids)
    connected_count = len(edges) // 2
    add_geometric_edges(vertices, edges, k=6, radius=1.5)
    commodities = choose_pairs(vertices, edges, args.pairs)
    payload = {
        "metadata": {"source_ifc": str(args.ifc), "schema": model.schema, "ports": len(vertices), "ifc_port_connections": connected_count, "adapter": "port connections plus 1.5-metre kNN completion", "warning": "This is a graph-adapter boundary check; it does not reconstruct service envelopes or construction clearances."},
        "vertices": vertices,
        "edges": [{"from": a, "to": b, "length": math.dist((vertices[a]["x"], vertices[a]["y"], vertices[a]["z"]), (vertices[b]["x"], vertices[b]["y"], vertices[b]["z"]))} for a, b in sorted(edges)],
        "commodities": commodities,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"vertices": len(vertices), "ifc_port_connections": connected_count, "edges": len(edges), "commodities": len(commodities)}, indent=2))


if __name__ == "__main__":
    main()
