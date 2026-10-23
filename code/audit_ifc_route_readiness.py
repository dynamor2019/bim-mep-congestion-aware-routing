"""Audit whether native IFC port graphs define point-to-point route tasks."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import ifcopenshell
from ifcopenshell.util.element import get_psets


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of an IFC source file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connected_component_summary(
    owner_ids: set[int],
    owner_edges: list[tuple[int, int]],
    terminal_directions: dict[int, set[str]],
) -> dict:
    """Summarize owner-level components and strict directed terminal pairs."""
    adjacency = collections.defaultdict(set)
    for owner_id in owner_ids:
        adjacency[owner_id]
    for first, second in owner_edges:
        adjacency[first].add(second)
        adjacency[second].add(first)

    unseen = set(owner_ids)
    terminal_count_histogram = collections.Counter()
    directed_pair_components = 0
    component_sizes = []
    while unseen:
        stack = [unseen.pop()]
        component = set()
        while stack:
            current = stack.pop()
            component.add(current)
            reached = adjacency[current] & unseen
            unseen.difference_update(reached)
            stack.extend(reached)
        component_sizes.append(len(component))
        terminals = {key: terminal_directions[key] for key in component
                     if key in terminal_directions}
        terminal_count_histogram[len(terminals)] += 1
        roles = {frozenset(value) for value in terminals.values()}
        if (len(terminals) == 2
                and roles == {frozenset({"SOURCE"}), frozenset({"SINK"})}):
            directed_pair_components += 1

    return {
        "owner_component_count": len(component_sizes),
        "largest_owner_component": max(component_sizes, default=0),
        "components_by_terminal_owner_count": {
            str(key): value for key, value in sorted(terminal_count_histogram.items())
        },
        "components_with_exact_source_sink_terminal_pair": directed_pair_components,
    }


def safe_count(model, ifc_type: str) -> int:
    """Return an IFC type count, including zero for absent schema entities."""
    try:
        return len(model.by_type(ifc_type))
    except RuntimeError:
        return 0


def audit_model(path: Path) -> dict:
    """Audit schema counts and explicit port-owner connectivity for one IFC."""
    model = ifcopenshell.open(str(path))
    ports = {port.id(): port for port in model.by_type("IfcDistributionPort")}
    owners = {}
    owner_ports = collections.defaultdict(list)
    for relation in model.by_type("IfcRelConnectsPortToElement"):
        port_id = relation.RelatingPort.id()
        owner = relation.RelatedElement
        owners[port_id] = owner
        owner_ports[owner.id()].append(ports[port_id])

    edges = []
    for relation in model.by_type("IfcRelConnectsPorts"):
        first = owners.get(relation.RelatingPort.id())
        second = owners.get(relation.RelatedPort.id())
        if first is not None and second is not None and first.id() != second.id():
            edges.append((first.id(), second.id()))

    entities = {owner.id(): owner for owner in owners.values()}
    terminal_directions = {
        owner_id: {port.FlowDirection for port in attached_ports}
        for owner_id, attached_ports in owner_ports.items()
        if entities[owner_id].is_a("IfcFlowTerminal")
    }
    role_counts = collections.Counter(
        direction for attached_ports in owner_ports.values()
        for port in attached_ports for direction in [port.FlowDirection]
    )
    segments = model.by_type("IfcFlowSegment")
    dimension_fields = collections.Counter()
    segments_with_dimensions = 0
    for segment in segments:
        dimensions = get_psets(segment).get("Dimensions", {})
        if dimensions:
            segments_with_dimensions += 1
            dimension_fields.update(key for key in dimensions if key != "id")
    topology = connected_component_summary(
        set(entities), edges, terminal_directions
    )

    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "schema": model.schema,
        "counts": {
            "distribution_systems": safe_count(model, "IfcDistributionSystem"),
            "systems": safe_count(model, "IfcSystem"),
            "distribution_ports": len(ports),
            "ports_with_owner_relation": len(owners),
            "port_connections": safe_count(model, "IfcRelConnectsPorts"),
            "flow_terminals": safe_count(model, "IfcFlowTerminal"),
            "flow_segments": safe_count(model, "IfcFlowSegment"),
            "flow_fittings": safe_count(model, "IfcFlowFitting"),
            "segments_with_geometry_representation": sum(
                segment.Representation is not None for segment in segments
            ),
            "segments_with_dimensions_pset": segments_with_dimensions,
            "dimension_field_occurrences": dict(sorted(dimension_fields.items())),
            "terminal_owners_with_ports": len(terminal_directions),
            "port_flow_directions": dict(sorted(role_counts.items())),
        },
        "owner_graph": topology,
        "scope": (
            "Owner-level connectivity joins ports belonging to the same IFC element "
            "and follows explicit IfcRelConnectsPorts relations. It is a readiness "
            "screen, not an accepted rerouting task, exact clash test, or route validation."
        ),
    }


def main() -> None:
    """Write a deterministic readiness summary for IFC2X3 or IFC4 files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ifc", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    missing = [str(path) for path in args.ifc if not path.is_file()]
    if missing:
        parser.error(f"IFC file not found: {', '.join(missing)}")
    report = {
        "dataset": "buildingSMART Medical-Dental Clinic sample, IFC2X3",
        "license": "CC BY 4.0",
        "source": "https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/main/IFC%202.3.0.1%20%28IFC%202x3%29/Medical-Dental%20Clinic",
        "audit_script_sha256": sha256_file(Path(__file__)),
        "models": [audit_model(path) for path in args.ifc],
        "interpretation": (
            "The source contains an already-modelled multi-terminal network. Its "
            "native graph does not identify project-approved point-to-point reroute "
            "requests, candidate alternatives, or coordinator-accepted outcomes."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"models": [
        {"file": row["file"], "counts": row["counts"], "owner_graph": row["owner_graph"]}
        for row in report["models"]
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
