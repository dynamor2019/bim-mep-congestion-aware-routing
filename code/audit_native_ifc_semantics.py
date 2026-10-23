"""Recover IFC port ownership, native service topology and geometry checks.

Topology describes existing services; it is not a free-space routing network.
All checks use explicit IFC associations and model-derived length units.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

import ifcopenshell
import numpy as np
from ifcopenshell.util.element import get_psets
from ifcopenshell.util.placement import get_local_placement
from ifcopenshell.util.unit import calculate_unit_scale


def port_owners(model):
    """Use native nesting and legacy port-to-element associations."""
    owners = {}
    for relation in model.by_type("IfcRelNests"):
        for obj in relation.RelatedObjects:
            if obj.is_a("IfcDistributionPort"):
                owners[obj.id()] = relation.RelatingObject.id()
    for relation in model.by_type("IfcRelConnectsPortToElement"):
        owners[relation.RelatingPort.id()] = relation.RelatedElement.id()
    return owners


def system_memberships(model):
    """Record only explicit IFC system groups, without inferred trade labels."""
    membership = defaultdict(set)
    systems = {}
    for relation in model.by_type("IfcRelAssignsToGroup"):
        group = relation.RelatingGroup
        if group.is_a("IfcSystem"):
            systems[group.id()] = {"id": group.id(), "type": group.is_a(), "name": group.Name}
            for obj in relation.RelatedObjects:
                membership[obj.id()].add(group.id())
    return membership, systems


def native_graph(model):
    """Recover external connections and within-owner connectivity, no kNN."""
    scale = calculate_unit_scale(model)
    owners = port_owners(model)
    membership, systems = system_memberships(model)
    vertices, id_map, grouped = [], {}, defaultdict(list)
    for port in sorted(model.by_type("IfcDistributionPort"), key=lambda p: p.id()):
        if port.ObjectPlacement is None:
            continue
        point = get_local_placement(port.ObjectPlacement)[:3, 3] * scale
        owner = owners.get(port.id())
        groups = membership[port.id()] | membership[owner]
        index = len(vertices)
        id_map[port.id()] = index
        vertices.append({"id": index, "ifc_id": port.id(), "owner_ifc_id": owner,
                         "owner_type": model.by_id(owner).is_a() if owner else None,
                         "systems": sorted(groups), "flow_direction": str(port.FlowDirection),
                         "x": float(point[0]), "y": float(point[1]), "z": float(point[2])})
        if owner:
            grouped[owner].append(index)
    edges = []
    for relation in model.by_type("IfcRelConnectsPorts"):
        a, b = id_map.get(relation.RelatingPort.id()), id_map.get(relation.RelatedPort.id())
        if a is not None and b is not None and a != b:
            edges.append({"from": a, "to": b, "kind": "explicit_port_connection"})
    for owner, indices in grouped.items():
        element = model.by_id(owner)
        if element.is_a("IfcFlowSegment") or element.is_a("IfcFlowFitting"):
            for a, b in itertools.combinations(indices, 2):
                edges.append({"from": a, "to": b, "kind": "within_component", "owner_ifc_id": owner})
    for edge in edges:
        a, b = vertices[edge["from"]], vertices[edge["to"]]
        edge["length"] = float(np.linalg.norm([a[k] - b[k] for k in ("x", "y", "z")]))
    return {"vertices": vertices, "edges": edges, "systems": list(systems.values()),
            "metadata": {"length_scale_to_m": scale, "knn_edges": 0,
                         "within_component_assumption": "all owned ports on a segment/fitting are internally connected; no free-space interpolation",
                         "scope": "Native installed-service topology; not a routing graph or constructability certificate."}}


def segment_hits_boxes(points_a, points_b, lower, upper):
    """Closed segment/AABB slab intersection, including endpoint contact."""
    delta = points_b - points_a
    enter = np.zeros((len(points_a), len(lower)))
    leave = np.ones_like(enter)
    for axis in range(3):
        start = points_a[:, None, axis]
        direction = delta[:, None, axis]
        parallel = np.abs(direction) < 1e-12
        safe = np.where(parallel, 1.0, direction)
        t1 = (lower[None, :, axis] - start) / safe
        t2 = (upper[None, :, axis] - start) / safe
        axis_enter = np.where(parallel, -np.inf, np.minimum(t1, t2))
        axis_leave = np.where(parallel, np.inf, np.maximum(t1, t2))
        outside = parallel & ((start < lower[None, :, axis]) | (start > upper[None, :, axis]))
        axis_enter = np.where(outside, np.inf, axis_enter)
        enter = np.maximum(enter, axis_enter)
        leave = np.minimum(leave, axis_leave)
    return enter <= leave


def geometry_checks(graph, boxes):
    """Count segment collisions with fixed ownership exemptions at each clearance."""
    vertices = graph["vertices"]
    edges = graph["edges"]
    lower = np.asarray([b["min"] for b in boxes])
    upper = np.asarray([b["max"] for b in boxes])
    box_ids = np.asarray([b["ifc_id"] for b in boxes])
    results, previous = [], set()
    for clearance in (0.0, 0.05, 0.15, 0.30):
        blocked, raw_count = set(), 0
        for offset in range(0, len(edges), 2000):
            batch = edges[offset:offset + 2000]
            starts = np.asarray([[vertices[e["from"]][k] for k in ("x", "y", "z")] for e in batch])
            ends = np.asarray([[vertices[e["to"]][k] for k in ("x", "y", "z")] for e in batch])
            hits = segment_hits_boxes(starts, ends, lower - clearance, upper + clearance)
            raw_count += int(hits.any(axis=1).sum())
            owners_a = np.asarray([vertices[e["from"]]["owner_ifc_id"] or -1 for e in batch])
            owners_b = np.asarray([vertices[e["to"]]["owner_ifc_id"] or -1 for e in batch])
            attached = (owners_a[:, None] == box_ids) | (owners_b[:, None] == box_ids)
            mask = (hits & ~attached).any(axis=1)
            blocked.update(offset + int(i) for i in np.flatnonzero(mask))
        if not previous.issubset(blocked):
            raise ValueError("Clearance monotonicity violated")
        results.append({"clearance_m": clearance, "raw_segment_box_intersections": raw_count,
                        "nonowner_intersecting_edges": len(blocked), "total_edges": len(edges),
                        "geometry_sample": len(boxes), "monotone": True})
        previous = blocked
    return results


def dimension_inventory(model, graph):
    """Count explicit dimensional/constructability properties, without guessing values."""
    keys = Counter()
    samples = []
    for owner in sorted({v["owner_ifc_id"] for v in graph["vertices"] if v["owner_ifc_id"]}):
        element = model.by_id(owner)
        found = {}
        for set_name, properties in get_psets(element).items():
            for name, value in properties.items():
                if any(token in name.lower() for token in ("diameter", "width", "height", "slope", "radius", "clearance", "maintenance")):
                    if isinstance(value, (float, int, str)) and name != "id":
                        key = f"{set_name}.{name}"
                        found[key] = value
                        keys[key] += 1
        if found:
            samples.append({"ifc_id": owner, "type": element.is_a(), "properties_native_units": found})
    return {"property_counts": dict(keys), "elements_with_properties": len(samples), "records": samples}


def swept_dimensions(model):
    """Measure extrusion profile extents; they need not be service cross-sections."""
    scale = calculate_unit_scale(model)
    records = []
    for element in model.by_type("IfcFlowSegment"):
        if element.Representation is None:
            continue
        for representation in element.Representation.Representations:
            for item in representation.Items:
                if not item.is_a("IfcExtrudedAreaSolid"):
                    continue
                profile = item.SweptArea
                if not profile.is_a("IfcArbitraryClosedProfileDef"):
                    continue
                curve = profile.OuterCurve
                if curve.is_a("IfcIndexedPolyCurve"):
                    points = np.asarray(curve.Points.CoordList, dtype=float)
                elif curve.is_a("IfcPolyline"):
                    points = np.asarray([p.Coordinates for p in curve.Points], dtype=float)
                else:
                    continue
                extent = np.ptp(points[:, :2], axis=0) * scale
                records.append({"ifc_id": element.id(), "type": element.is_a(),
                                "profile_ifc_id": profile.id(), "profile_extent_x_m": float(extent[0]),
                                "profile_extent_y_m": float(extent[1]), "extrusion_depth_m": float(item.Depth * scale),
                                "measurement": "profile-plane extents and depth; extrusion may be transverse to the service axis, so these are not nominal cross-sections"})
    return records


def main():
    """Write semantic graph and a monotonic geometry audit from cached boxes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("ifc", type=Path)
    parser.add_argument("boxes", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    model = ifcopenshell.open(args.ifc)
    graph = native_graph(model)
    boxes = json.loads(args.boxes.read_text(encoding="utf-8"))
    checks = geometry_checks(graph, boxes)
    inventory = dimension_inventory(model, graph)
    dimensions = swept_dimensions(model)
    summary = {"source": args.ifc.name, "ports": len(graph["vertices"]),
               "owned_ports": sum(v["owner_ifc_id"] is not None for v in graph["vertices"]),
               "ports_with_system": sum(bool(v["systems"]) for v in graph["vertices"]),
               "edge_types": dict(Counter(e["kind"] for e in graph["edges"])),
               "flow_directions": dict(Counter(v["flow_direction"] for v in graph["vertices"])),
               "geometry_checks": checks, "length_scale_to_m": graph["metadata"]["length_scale_to_m"],
               "dimension_property_counts": inventory["property_counts"],
               "segments_with_measured_profile_extents": len({r["ifc_id"] for r in dimensions}),
               "measured_segment_types": dict(Counter(r["type"] for r in dimensions)),
               "limitations": ["300-element geometry sample", "AABB is a conservative geometric proxy",
                               "own-component attachment exemption is fixed across clearances",
                               "clearances are sensitivity assumptions, not code requirements",
                               "installed topology does not describe available routing space"]}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in (("native_graph.json", graph), ("native_audit.json", summary), ("dimension_inventory.json", inventory), ("measured_profiles.json", dimensions)):
        (args.output / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (args.output / "clearance_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=checks[0])
        writer.writeheader()
        writer.writerows(checks)
    print(json.dumps({k: v for k, v in summary.items() if k != "dimension_property_counts"}, indent=2))


if __name__ == "__main__":
    main()
