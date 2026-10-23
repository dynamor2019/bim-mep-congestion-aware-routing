"""Extract IFC MEP geometry and run clearance-aware port-graph checks."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np

from run_ifc_graph_adapter import load_graph, run


FLOW_TYPES = (
    "IfcFlowSegment",
    "IfcFlowFitting",
    "IfcFlowTerminal",
    "IfcFlowController",
    "IfcFlowMovingDevice",
    "IfcFlowStorageDevice",
    "IfcFlowTreatmentDevice",
)


def bounding_boxes(model, max_elements: int) -> list[dict]:
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    boxes = []
    elements = []
    for type_name in FLOW_TYPES:
        typed = sorted(model.by_type(type_name), key=lambda item: item.id())
        if len(typed) > max_elements:
            indices = np.linspace(0, len(typed) - 1, max_elements, dtype=int)
            typed = [typed[index] for index in indices]
        elements.extend((type_name, element) for element in typed)
    for type_name, element in elements:
            if element.Representation is None:
                continue
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)
                # IfcOpenShell geometry is already expressed in the model's SI length unit.
                values = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
                lower = values.min(axis=0)
                upper = values.max(axis=0)
            except Exception:
                continue
            boxes.append({
                "ifc_id": element.id(),
                "ifc_type": type_name,
                "min": lower.tolist(),
                "max": upper.tolist(),
                "size": (upper - lower).tolist(),
            })
    return boxes


def envelope_summary(boxes: list[dict], clearance: float) -> dict:
    sizes = np.asarray([item["size"] for item in boxes], dtype=float)
    expanded = sizes + 2.0 * clearance
    volume = np.prod(expanded, axis=1)
    return {
        "clearance_m": clearance,
        "elements_with_geometry": len(boxes),
        "median_envelope_size_m": np.median(expanded, axis=0).round(4).tolist(),
        "total_envelope_volume_m3": float(volume.sum()),
        "p95_envelope_volume_m3": float(np.percentile(volume, 95)),
    }


def edge_midpoint_blocked(a: dict, b: dict, boxes: list[dict], clearance: float) -> bool:
    midpoint = (np.asarray([a["x"], a["y"], a["z"]]) + np.asarray([b["x"], b["y"], b["z"]])) / 2.0
    for box in boxes:
        lower = np.asarray(box["min"]) - clearance
        upper = np.asarray(box["max"]) + clearance
        if np.all(midpoint >= lower) and np.all(midpoint <= upper):
            inside_a = np.all(np.asarray([a["x"], a["y"], a["z"]]) >= lower) and np.all(np.asarray([a["x"], a["y"], a["z"]]) <= upper)
            inside_b = np.all(np.asarray([b["x"], b["y"], b["z"]]) >= lower) and np.all(np.asarray([b["x"], b["y"], b["z"]]) <= upper)
            if not inside_a and not inside_b:
                return True
    return False


def filtered_graph(data: dict, clearance: float, boxes: list[dict]) -> dict:
    vertices = {item["id"]: item for item in data["vertices"]}
    edges = list(data["edges"])
    if not boxes:
        return dict(data, metadata=dict(data["metadata"], geometry_clearance_m=clearance, blocked_edges=0))
    lower = np.asarray([item["min"] for item in boxes], dtype=float) - clearance
    upper = np.asarray([item["max"] for item in boxes], dtype=float) + clearance
    keep = np.ones(len(edges), dtype=bool)
    for start in range(0, len(edges), 5000):
        batch = edges[start:start + 5000]
        points_a = np.asarray([[vertices[e["from"]][key] for key in ("x", "y", "z")] for e in batch])
        points_b = np.asarray([[vertices[e["to"]][key] for key in ("x", "y", "z")] for e in batch])
        mid = (points_a + points_b) / 2.0
        mid_inside = np.all((mid[:, None, :] >= lower[None, :, :]) & (mid[:, None, :] <= upper[None, :, :]), axis=2)
        a_inside = np.all((points_a[:, None, :] >= lower[None, :, :]) & (points_a[:, None, :] <= upper[None, :, :]), axis=2)
        b_inside = np.all((points_b[:, None, :] >= lower[None, :, :]) & (points_b[:, None, :] <= upper[None, :, :]), axis=2)
        keep[start:start + len(batch)] = ~np.any(mid_inside & ~a_inside & ~b_inside, axis=1)
    blocked = int((~keep).sum())
    edges = [edge for edge, valid in zip(edges, keep) if valid]
    result = dict(data)
    result["edges"] = edges
    result["metadata"] = dict(data["metadata"], geometry_clearance_m=clearance, blocked_edges=blocked)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ifc", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--max-elements-per-type", type=int, default=100, help="Deterministic geometry sample per IFC type.")
    args = parser.parse_args()
    model = ifcopenshell.open(args.ifc)
    boxes = bounding_boxes(model, args.max_elements_per_type)
    base, _ = load_graph(args.graph)
    clearances = [0.0, 0.05, 0.15, 0.30]
    summaries = [envelope_summary(boxes, clearance) for clearance in clearances]
    rows = []
    for clearance in clearances:
        graph = filtered_graph(base, clearance, boxes)
        adjacency = load_graph_from_data(graph)
        for seed in range(args.seeds):
            for item in run(graph, adjacency, seed):
                rows.append(dict(item, clearance_m=clearance, blocked_edges=graph["metadata"]["blocked_edges"], geometry_elements=len(boxes)))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ifc_geometry_summary.json").write_text(json.dumps({"flow_types": FLOW_TYPES, "max_elements_per_type": args.max_elements_per_type, "summaries": summaries}, indent=2), encoding="utf-8")
    with (args.output / "ifc_geometry_routing.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "ifc_geometry_boxes.json").write_text(json.dumps(boxes), encoding="utf-8")
    print(json.dumps({"geometry_elements": len(boxes), "clearances": clearances, "rows": len(rows)}, indent=2))


def load_graph_from_data(data: dict) -> dict[int, list[tuple[int, float]]]:
    adjacency = {}
    for edge in data["edges"]:
        adjacency.setdefault(edge["from"], []).append((edge["to"], float(edge["length"])))
    return adjacency


if __name__ == "__main__":
    main()
