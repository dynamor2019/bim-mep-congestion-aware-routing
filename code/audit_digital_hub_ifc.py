"""Audit public RWTH Digital Hub IFC semantics and a bounded geometry sample."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
from ifcopenshell.util.element import get_psets
from ifcopenshell.util.unit import calculate_unit_scale

from audit_native_ifc_semantics import native_graph
from run_ifc_geometry_envelope import FLOW_TYPES, bounding_boxes


DATA_FILES = ("arc.ifc", "heating.ifc", "plumbing.ifc", "ventilation.ifc")
MEP_FILES = DATA_FILES[1:]
ARCH_TYPES = (
    "IfcWall", "IfcSlab", "IfcBeam", "IfcColumn", "IfcDoor", "IfcWindow",
    "IfcBuildingElementProxy",
)
DIMENSION_FIELDS = {
    "Au\u00dfendurchmesser": "external_diameter_m",
    "Innendurchmesser": "internal_diameter_m",
    "Breite": "width_m",
    "H\u00f6he": "height_m",
    "Durchmesser": "diameter_m",
}


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for an IFC input."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_identity(model) -> dict:
    """Read common IFC identity and map-conversion fields."""
    conversion = model.by_type("IfcMapConversion")
    crs = model.by_type("IfcProjectedCRS")
    identity = {}
    for entity_type in ("IfcProject", "IfcSite", "IfcBuilding"):
        entity = model.by_type(entity_type)[0]
        identity[entity_type] = entity.GlobalId
    mapping = conversion[0] if conversion else None
    return {
        "identity": identity,
        "crs": crs[0].Name if crs else None,
        "map_conversion": {
            field: getattr(mapping, field, None) if mapping else None
            for field in (
                "Eastings", "Northings", "OrthogonalHeight",
                "XAxisAbscissa", "XAxisOrdinate", "Scale",
            )
        },
    }


def segment_properties(model, unit_scale: float) -> dict:
    """Summarize native size and slope fields on flow segments."""
    values = {field: [] for field in DIMENSION_FIELDS.values()}
    slope_count = 0
    segments = model.by_type("IfcFlowSegment")
    for element in segments:
        properties = get_psets(element)
        dimensions = properties.get("Abmessungen", {})
        for native_name, output_name in DIMENSION_FIELDS.items():
            value = dimensions.get(native_name)
            if isinstance(value, (int, float)):
                values[output_name].append(float(value) * unit_scale)
        if any("neigung" in name.lower() for pset in properties.values() for name in pset):
            slope_count += 1
    summary = {}
    for name, items in values.items():
        if items:
            summary[name] = {
                "count": len(items),
                "p05_m": float(np.percentile(items, 5)),
                "median_m": float(np.median(items)),
                "p95_m": float(np.percentile(items, 95)),
            }
    return {"flow_segments": len(segments), "dimensions": summary,
            "segments_with_slope_property": slope_count}


def system_topology_summary(graph: dict) -> dict:
    """Summarize native port-graph fragmentation by authored IFC system."""
    vertices = graph["vertices"]
    edges = graph["edges"]
    records = []
    for system in graph["systems"]:
        system_id = system["id"]
        node_ids = {v["id"] for v in vertices if system_id in v["systems"]}
        adjacency = {node_id: set() for node_id in node_ids}
        for edge in edges:
            a, b = edge["from"], edge["to"]
            if a in node_ids and b in node_ids:
                adjacency[a].add(b)
                adjacency[b].add(a)
        unseen = set(node_ids)
        component_sizes = []
        while unseen:
            stack = [unseen.pop()]
            size = 0
            while stack:
                node_id = stack.pop()
                size += 1
                reached = adjacency[node_id] & unseen
                unseen.difference_update(reached)
                stack.extend(reached)
            component_sizes.append(size)
        degrees = [len(adjacency[node_id]) for node_id in node_ids]
        records.append({
            "system_ifc_id": system_id,
            "system_name": system["name"],
            "ports": len(node_ids),
            "connected_components": len(component_sizes),
            "largest_component_ports": max(component_sizes, default=0),
            "isolated_ports": sum(degree == 0 for degree in degrees),
            "branch_ports_degree_gt_2": sum(degree > 2 for degree in degrees),
        })
    return {
        "systems": records,
        "summary": {
            "system_count": len(records),
            "median_ports_per_system": float(np.median([r["ports"] for r in records])),
            "median_components_per_system": float(np.median([r["connected_components"] for r in records])),
            "systems_with_multiple_components": sum(r["connected_components"] > 1 for r in records),
            "isolated_port_memberships": sum(r["isolated_ports"] for r in records),
            "branch_port_memberships": sum(r["branch_ports_degree_gt_2"] for r in records),
        },
        "interpretation": (
            "Components use explicit port relations plus the stated within-segment/fitting "
            "assumption and describe only the extracted graph. Multiple components do not "
            "prove that authored systems are physically disconnected; this graph is not a "
            "validated route instance or accepted reroute target."
        ),
    }


def architecture_boxes(model, max_per_type: int) -> list[dict]:
    """Extract a deterministic architectural AABB sample."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    boxes = []
    for type_name in ARCH_TYPES:
        elements = sorted(model.by_type(type_name), key=lambda item: item.id())
        if len(elements) > max_per_type:
            indices = np.linspace(0, len(elements) - 1, max_per_type, dtype=int)
            elements = [elements[index] for index in indices]
        for element in elements:
            if element.Representation is None:
                continue
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)
            except (RuntimeError, ValueError):
                continue
            vertices = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            if len(vertices):
                boxes.append({"ifc_id": element.id(), "ifc_type": type_name,
                              "min": vertices.min(axis=0).tolist(),
                              "max": vertices.max(axis=0).tolist()})
    return boxes


def count_aabb_pairs(mep: list[dict], architecture: list[dict], margin: float) -> int:
    """Count intersecting sampled AABBs as a broad-phase screen."""
    mep_min = np.asarray([box["min"] for box in mep])
    mep_max = np.asarray([box["max"] for box in mep])
    arch_min = np.asarray([box["min"] for box in architecture])
    arch_max = np.asarray([box["max"] for box in architecture])
    overlap = (mep_max[:, None, :] + margin >= arch_min[None, :, :])
    overlap &= (arch_max[None, :, :] + margin >= mep_min[:, None, :])
    return int(np.count_nonzero(np.all(overlap, axis=2)))


def audit_dataset(source: Path, output: Path, max_per_type: int) -> dict:
    """Audit all four IFCs and save bounded geometry and native graphs."""
    missing = [name for name in DATA_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing IFC inputs: {', '.join(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    summary = {"source": "RWTH Aachen Digital Hub IFC-Bench",
               "inputs": {}, "geometry_sample": {"max_per_type": max_per_type}}
    mep_boxes = []
    architecture_sample = []
    for filename in DATA_FILES:
        model_path = source / filename
        model = ifcopenshell.open(str(model_path))
        record = model_identity(model)
        record.update({"sha256": sha256_file(model_path),
                       "length_scale_to_m": calculate_unit_scale(model)})
        if filename in MEP_FILES:
            graph = native_graph(model)
            record["native_topology"] = system_topology_summary(graph)
            record.update({
                "systems": len(model.by_type("IfcSystem")),
                "ports_with_placement": len(graph["vertices"]),
                "ports_with_system": sum(bool(port["systems"]) for port in graph["vertices"]),
                "explicit_port_relations": len(model.by_type("IfcRelConnectsPorts")),
                "flow_fittings": len(model.by_type("IfcFlowFitting")),
                "segment_properties": segment_properties(model, record["length_scale_to_m"]),
            })
            (output / f"{model_path.stem}_native_graph.json").write_text(
                json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
            boxes = bounding_boxes(model, max_per_type)
            record["geometry_boxes_sampled"] = len(boxes)
            for box in boxes:
                box["source"] = filename
            mep_boxes.extend(boxes)
        else:
            record["geometry_boxes_sampled"] = 0
        summary["inputs"][filename] = record
    architecture = ifcopenshell.open(str(source / "arc.ifc"))
    architecture_sample = architecture_boxes(architecture, max_per_type)
    summary["inputs"]["arc.ifc"]["geometry_boxes_sampled"] = len(architecture_sample)
    summary["geometry_sample"].update({
        "mep_boxes": len(mep_boxes), "architecture_boxes": len(architecture_sample),
        "architecture_types": list(ARCH_TYPES), "mep_types": list(FLOW_TYPES),
        "not_full_model_geometry": True,
        "aabb_pair_candidates": [
            {"added_margin_m": margin,
             "count": count_aabb_pairs(mep_boxes, architecture_sample, margin)}
            for margin in (0.0, 0.05, 0.15, 0.30)
        ],
    })
    summary["interpretation"] = (
        "AABB candidates are broad-phase pairs, not exact clashes or route outcomes. "
        "The data audit does not establish accepted reroutes or construction validity."
    )
    (output / "digital_hub_ifc_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "digital_hub_mep_geometry_sample.json").write_text(
        json.dumps(mep_boxes, ensure_ascii=False), encoding="utf-8")
    (output / "digital_hub_architecture_geometry_sample.json").write_text(
        json.dumps(architecture_sample, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> None:
    """Run the deterministic public IFC audit from local files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-per-type", type=int, default=25)
    args = parser.parse_args()
    if args.max_per_type < 1:
        parser.error("--max-per-type must be positive")
    print(json.dumps(audit_dataset(args.source, args.output, args.max_per_type),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
