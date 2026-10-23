"""Run paired, equal-iteration adaptive versus random repair at three scales."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run_advanced_validation import adaptive_repair, scaled_instance  # noqa: E402
from run_routing_experiments import (  # noqa: E402
    estimate_demand,
    improve,
    objective,
    route_order,
    solution_cost,
)
from routing_revision_solvers import validate_paths  # noqa: E402
from run_revision_benchmark import fingerprint  # noqa: E402


SCALES = ("base", "large", "xlarge")
METHODS = ("mspp_random_repair", "adaptive_multi_operator")
ITERATIONS = 8


def run_scene(scale: str, seed: int) -> list[dict]:
    """Run both methods from the same deterministic initial routing."""
    instance = scaled_instance(scale, seed)
    predicted = estimate_demand(instance)
    rng = random.Random(seed)
    order = list(range(len(instance.commodities)))
    rng.shuffle(order)
    initial = route_order(instance, order, predicted, 0.0)
    validate_paths(instance, initial)
    scene_hash = fingerprint(instance)
    outputs = []
    for method in METHODS:
        started = time.perf_counter()
        if method == "mspp_random_repair":
            paths, trace = improve(
                instance, initial, predicted, False, random.Random(seed),
                iterations=ITERATIONS,
            )
        else:
            paths, trace = adaptive_repair(instance, initial, predicted, seed)
        runtime = time.perf_counter() - started
        validate_paths(instance, paths)
        outputs.append({
            "scale": scale,
            "seed": seed,
            "scene_hash": scene_hash,
            "method": method,
            "systems": len(instance.commodities),
            "success": int(len(paths) == len(instance.commodities)),
            "routed": len(paths),
            "total": len(instance.commodities),
            "objective": objective(instance, paths),
            "physical_cost": solution_cost(instance, paths),
            "runtime_s": runtime,
            "iterations": ITERATIONS,
            "validated": 1,
            "trace": json.dumps(trace),
        })
    return outputs


def write_results(output: Path, rows: list[dict], seeds: int, start_seed: int) -> None:
    """Write paired raw outcomes and their provenance manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "protocol": "same-scene adaptive versus random repair; equal 8-iteration budget",
        "seeds_per_scale": seeds,
        "start_seed": start_seed,
        "scales": list(SCALES),
        "methods": list(METHODS),
        "outputs": len(rows),
        "all_validated": all(row["validated"] == 1 for row in rows),
        "scene_hash_count": len({row["scene_hash"] for row in rows}),
        "runtime_note": "Equal iteration count, not equal wall-clock time; runtime is reported per method.",
        "scope_note": "Synthetic generated cases; no causal or real-project claim.",
        "python": sys.version,
        "platform": platform.platform(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


def main() -> None:
    """Run matched scales and flush scene pairs for recoverability."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=50000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    rows = []
    for scale in SCALES:
        for offset in range(args.seeds):
            pair = run_scene(scale, args.start_seed + offset)
            rows.extend(pair)
            print(f"{scale}: {offset + 1}/{args.seeds}", flush=True)
    write_results(args.output, rows, args.seeds, args.start_seed)
    print(json.dumps({"outputs": len(rows), "path": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
