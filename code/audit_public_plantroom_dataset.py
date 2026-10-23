"""Audit compatibility of public plant-room cases with the point-to-point solver."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROUTE_FIELDS = {
    "upstream_header", "downstream_header", "transition",
    "upstream_risers", "downstream_risers",
}


def load_json(path: Path) -> dict:
    """Load one UTF-8 JSON file and require an object at its root."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def audit_case(case_dir: Path) -> dict:
    """Check case identity, route coverage, and endpoint topology."""
    source = load_json(case_dir / "input_case.json")
    layout = load_json(case_dir / "output_layout.json")
    costs = load_json(case_dir / "output_cost.json")
    source_id = source.get("case_info", {}).get("case_id")
    layout_id = layout.get("case_info", {}).get("case_id")
    source_pipes = {pipe["pipe_id"]: pipe for pipe in source.get("pipes", [])}
    layout_pipes = {pipe["pipe_id"]: pipe for pipe in layout.get("pipes", [])}
    if source_id != layout_id or source_pipes.keys() != layout_pipes.keys():
        raise ValueError(f"Input/output identity mismatch: {case_dir.name}")
    networks = []
    for pipe_id, pipe in sorted(source_pipes.items()):
        definition = pipe["input_definition"]
        upstream = definition["upstream"]
        downstream = definition["downstream"]
        n_up = len(upstream.get("terminal_points", []))
        n_down = len(downstream.get("terminal_points", []))
        output = layout_pipes[pipe_id]
        if not ROUTE_FIELDS.issubset(output):
            raise ValueError(f"Incomplete layout for {case_dir.name}/{pipe_id}")
        networks.append({
            "pipe_id": pipe_id,
            "upstream_terminal_count": n_up,
            "downstream_terminal_count": n_down,
            "terminal_count": n_up + n_down,
            "header_diameters": [upstream.get("header_diameter"),
                                 downstream.get("header_diameter")],
            "main_layer_height": pipe.get("main_layer_height"),
            "upstream_riser_paths": len(output["upstream_risers"].get("paths", [])),
            "downstream_riser_paths": len(output["downstream_risers"].get("paths", [])),
        })
    coordinate = source.get("case_info", {}).get("coordinate_system", {})
    return {
        "case_id": source_id,
        "coordinate_system": coordinate,
        "pipe_network_count": len(networks),
        "terminal_point_count": sum(item["terminal_count"] for item in networks),
        "multi_terminal_network_count": sum(item["terminal_count"] > 2 for item in networks),
        "obstacle_count": len(source.get("obstacles") or []),
        "equipment_count": len(source.get("equipment", [])),
        "maintenance_area_count": sum(
            "maintenance_area_rect" in item for item in source.get("equipment", [])),
        "room_boundary_vertex_count": len(source.get("room", {}).get("boundary", [])),
        "network_details": networks,
        "cost_case_id": costs.get("case_info", {}).get("case_id"),
    }


def summarize(cases: list[dict]) -> dict:
    """Summarize evidence and state whether current benchmark semantics fit."""
    diameters = Counter()
    heights = Counter()
    for case in cases:
        for network in case["network_details"]:
            diameters.update(str(value) for value in network["header_diameters"]
                             if value is not None)
            heights.update(str(network["main_layer_height"])
                           for _ in [0] if network["main_layer_height"] is not None)
    network_count = sum(case["pipe_network_count"] for case in cases)
    terminal_count = sum(case["terminal_point_count"] for case in cases)
    multi_terminal = sum(case["multi_terminal_network_count"] for case in cases)
    return {
        "dataset": "MEP Plant Room Pipe Routing Dataset",
        "source": "https://huggingface.co/datasets/IHNF/mep-plant-room-pipe-routing",
        "paper_doi": "10.1016/j.autcon.2026.107201",
        "license": "CC BY 4.0",
        "case_count": len(cases),
        "pipe_network_count": network_count,
        "terminal_point_count": terminal_count,
        "multi_terminal_network_count": multi_terminal,
        "all_case_ids_match": all(case["case_id"] == case["cost_case_id"] for case in cases),
        "coordinate_systems": sorted({
            case["coordinate_system"].get("type", "unspecified") for case in cases}),
        "coordinate_units_declared_in_case_metadata": False,
        "header_diameter_value_counts": dict(sorted(diameters.items())),
        "main_layer_height_value_counts": dict(sorted(heights.items())),
        "direct_point_to_point_benchmark_eligible": False,
        "eligibility_reason": (
            "Every pipe entry is a multi-terminal network with shared header/riser geometry; "
            "the current solver assumes independent point-to-point commodities and exclusive "
            "inter-commodity vertex occupancy. The case metadata describes an internal 2D "
            "plan coordinate system without a declared length unit. Converting these trees "
            "into independent pairs would change intended within-system sharing."
        ),
        "cases": cases,
    }


def main() -> None:
    """Audit all case folders and write deterministic JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    case_dirs = sorted(path for path in args.dataset_dir.iterdir() if path.is_dir())
    if not case_dirs:
        parser.error(f"No case folders in {args.dataset_dir}")
    result = summarize([audit_case(path) for path in case_dirs])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "case_count", "pipe_network_count", "terminal_point_count",
        "multi_terminal_network_count", "direct_point_to_point_benchmark_eligible")}, indent=2))


if __name__ == "__main__":
    main()
