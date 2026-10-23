"""Audit native topology and swept-profile dimensions in IFC-Bench hospital MEP files."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import ifcopenshell
import numpy as np
from ifcopenshell.util.unit import calculate_unit_scale

from audit_ifc_route_readiness import audit_model


def summarize_values(values: list[list[float]]) -> dict:
    """Summarize raw representation-profile parameters in metres."""
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return {"count": 0, "median_m": [], "p90_m": [], "maximum_m": []}
    return {
        "count": int(data.shape[0]),
        "median_m": np.median(data, axis=0).round(6).tolist(),
        "p90_m": np.percentile(data, 90, axis=0).round(6).tolist(),
        "maximum_m": np.max(data, axis=0).round(6).tolist(),
        "parameters_over_10m": int(np.sum(data > 10.0)),
    }


def profile_inventory(path: Path) -> dict:
    """Count extractable segment profiles without treating them as clearances."""
    model = ifcopenshell.open(str(path))
    scale = calculate_unit_scale(model)
    counts = Counter()
    measured = defaultdict(list)
    for segment in model.by_type("IfcFlowSegment"):
        if segment.Representation is None:
            continue
        for representation in segment.Representation.Representations:
            for item in representation.Items:
                if not item.is_a("IfcExtrudedAreaSolid"):
                    continue
                profile = item.SweptArea
                profile_type = profile.is_a()
                counts[profile_type] += 1
                if profile_type == "IfcCircleProfileDef":
                    measured["circular_diameter"].append([2 * float(profile.Radius) * scale])
                elif profile_type == "IfcRectangleProfileDef":
                    measured["rectangular_sides"].append([
                        float(profile.XDim) * scale,
                        float(profile.YDim) * scale,
                    ])
    return {
        "schema": model.schema,
        "length_scale_to_m": scale,
        "flow_segments": len(model.by_type("IfcFlowSegment")),
        "flow_fittings": len(model.by_type("IfcFlowFitting")),
        "swept_profile_types": dict(sorted(counts.items())),
        "measured_parameters": {
            key: summarize_values(values) for key, values in sorted(measured.items())
        },
        "interpretation": (
            "Representation parameters are not verified nominal dimensions; orientation, "
            "geometry validity, insulation, fitting envelopes, and installation clearance "
            "require separate checks."
        ),
    }


def build_report(ifc_paths: list[Path]) -> dict:
    """Compare IFC2X3 and IFC4 topology and profile readiness."""
    models = []
    for path in ifc_paths:
        models.append({"topology": audit_model(path), "profiles": profile_inventory(path)})
    return {
        "dataset": "West Riverside Hospital IFC models, hosted by IFC-Bench",
        "attribution": (
            "Solihin, W. West Riverside Hospital IFC Models, OpenIFC Model Repository, "
            "University of Auckland. CC BY 3.0."
        ),
        "models": models,
        "scope": (
            "Readiness audit only. Existing installed networks do not define approved "
            "independent rerouting requests or accepted alternative routes."
        ),
    }


def main() -> None:
    """Write the machine-readable IFC schema comparison."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ifc", type=Path, nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    missing = [str(path) for path in args.ifc if not path.is_file()]
    if missing:
        parser.error(f"IFC file not found: {', '.join(missing)}")
    report = build_report(args.ifc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "models": [{
            "file": item["topology"]["file"],
            "counts": item["topology"]["counts"],
            "profiles": item["profiles"]["swept_profile_types"],
        } for item in report["models"]],
    }, indent=2))


if __name__ == "__main__":
    main()
