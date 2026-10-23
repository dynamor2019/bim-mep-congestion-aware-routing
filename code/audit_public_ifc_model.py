"""Create a provenance-aware IFC route-readiness audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_ifc_route_readiness import audit_model


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file using bounded-memory reads."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_report(ifc_path: Path, source_url: str, license_name: str) -> dict:
    """Audit native owner connectivity and record source provenance."""
    if not ifc_path.is_file():
        raise FileNotFoundError(ifc_path)
    return {
        "dataset": ifc_path.parent.name,
        "source_url": source_url,
        "model_license": license_name,
        "file_sha256": sha256_file(ifc_path),
        "models": [audit_model(ifc_path)],
        "interpretation": (
            "Readiness screen only; it does not create accepted rerouting tasks, "
            "perform exact clash checks, or validate routing performance."
        ),
    }


def main() -> None:
    """Write a machine-readable public-IFC readiness report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ifc", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.ifc, args.source_url, args.license)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": report["file_sha256"]}))


if __name__ == "__main__":
    main()
