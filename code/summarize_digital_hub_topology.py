"""Summarize cached native IFC port graphs without regenerating geometry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from audit_digital_hub_ifc import system_topology_summary  # noqa: E402


def summarize(graph_dir: Path) -> dict:
    """Return deterministic per-discipline summaries from audited graphs."""
    disciplines = {}
    for name in ("heating", "plumbing", "ventilation"):
        graph_path = graph_dir / f"{name}_native_graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        disciplines[name] = system_topology_summary(graph)
    return {
        "source": "RWTH Aachen Digital Hub IFC-Bench",
        "graph_files": [f"{name}_native_graph.json" for name in disciplines],
        "topology_by_discipline": disciplines,
        "interpretation": (
            "System graphs use explicit port relations plus the documented "
            "within-segment/fitting assumption. Multiple components describe "
            "the extracted graph only and do not prove physical disconnection; "
            "the graphs do not establish accepted route targets or alternatives."
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
    print(json.dumps({name: record["summary"] for name, record in result["topology_by_discipline"].items()}, indent=2))


if __name__ == "__main__":
    main()
