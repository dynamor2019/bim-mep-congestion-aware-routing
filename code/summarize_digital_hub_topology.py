"""Summarize cached native IFC port graphs without regenerating geometry."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from audit_digital_hub_ifc import system_topology_summary  # noqa: E402

TERMINAL_TYPES = {"IfcSpaceHeater", "IfcSanitaryTerminal", "IfcWasteTerminal", "IfcAirTerminal"}


def directed_terminal_pair_summary(graph: dict) -> dict:
    """Count components with two distinct terminal owners and opposite roles."""
    vertices = {vertex["id"]: vertex for vertex in graph["vertices"]}
    adjacency = collections.defaultdict(set)
    for edge in graph["edges"]:
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])

    pairs = []
    two_terminal_components = 0
    for system in graph["systems"]:
        system_id = system["id"]
        members = {node for node, vertex in vertices.items() if system_id in vertex.get("systems", [])}
        visited = set()
        for start in members:
            if start in visited:
                continue
            component = []
            stack = [start]
            visited.add(start)
            while stack:
                node = stack.pop()
                component.append(node)
                for neighbor in adjacency[node] & members:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            terminal_owners = {}
            for node in component:
                vertex = vertices[node]
                if vertex.get("owner_type") not in TERMINAL_TYPES:
                    continue
                owner_id = vertex.get("owner_ifc_id")
                if owner_id is None:
                    owner_id = vertex["id"]
                owner = terminal_owners.setdefault(owner_id, {
                    "owner_type": vertex["owner_type"], "directions": set(),
                })
                if vertex.get("flow_direction"):
                    owner["directions"].add(vertex["flow_direction"])
            if len(terminal_owners) != 2:
                continue
            two_terminal_components += 1
            source_owners = [owner_id for owner_id, owner in terminal_owners.items()
                             if owner["directions"] == {"SOURCE"}]
            sink_owners = [owner_id for owner_id, owner in terminal_owners.items()
                           if owner["directions"] == {"SINK"}]
            if len(source_owners) == 1 and len(sink_owners) == 1:
                pairs.append({
                    "system_name": system["name"],
                    "source_owner_ifc_id": source_owners[0],
                    "sink_owner_ifc_id": sink_owners[0],
                })
    return {
        "recognized_terminal_types": sorted(TERMINAL_TYPES),
        "two_terminal_components": two_terminal_components,
        "directed_source_sink_pairs": len(pairs),
        "directed_pairs": pairs,
    }


def summarize(graph_dir: Path) -> dict:
    """Return deterministic per-discipline summaries from audited graphs."""
    disciplines = {}
    pair_readiness = {}
    for name in ("heating", "plumbing", "ventilation"):
        graph_path = graph_dir / f"{name}_native_graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        disciplines[name] = system_topology_summary(graph)
        pair_readiness[name] = directed_terminal_pair_summary(graph)
    return {
        "source": "RWTH Aachen Digital Hub IFC-Bench",
        "graph_files": [f"{name}_native_graph.json" for name in disciplines],
        "topology_by_discipline": disciplines,
        "terminal_pair_readiness": pair_readiness,
        "interpretation": (
            "System graphs use explicit port relations plus the documented "
            "within-segment/fitting assumption. Multiple components describe "
            "the extracted graph only and do not prove physical disconnection; "
            "the directed-pair count is a schema-level screen, not evidence of "
            "accepted reroute targets or alternatives."
        ),
    }


def main() -> None:
    """Write the cached-graph diagnostic as a machine-readable JSON file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("graph_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.graph_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "topology": {name: record["summary"] for name, record in result["topology_by_discipline"].items()},
        "terminal_pair_readiness": result["terminal_pair_readiness"],
    }, indent=2))


if __name__ == "__main__":
    main()
