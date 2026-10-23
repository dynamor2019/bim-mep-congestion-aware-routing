"""Factorial stress test separating system count from obstacle probability."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import platform
import random
import sys
from pathlib import Path

from routing_revision_solvers import validate_paths


def load_router(path: Path):
    spec = importlib.util.spec_from_file_location("router_factorial", path)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def generate(router, seed: int, n_systems: int, obstacle_rate: float):
    rng = random.Random(seed); shape = (16, 12, 3); blocked = set()
    for x in (5, 10):
        openings = {rng.randrange(1, 5), rng.randrange(7, 11)}
        for y in range(shape[1]):
            for z in range(shape[2]):
                if y not in openings and rng.random() < 0.82: blocked.add((x, y, z))
    for x in range(shape[0]):
        for y in range(shape[1]):
            for z in range(shape[2]):
                if rng.random() < obstacle_rate: blocked.add((x, y, z))
    free = [(x, y, z) for x in range(shape[0]) for y in range(shape[1]) for z in range(shape[2]) if (x, y, z) not in blocked]
    disciplines = (("HVAC", 1.8, 1.4), ("pressure", 1.2, 1.5), ("electrical", 0.8, 1.2), ("drainage", 1.3, 2.0))
    commodities = []; used = set(); attempts = 0
    while len(commodities) < n_systems and attempts < 10000:
        attempts += 1; lefts = [p for p in free if p[0] <= 3 and p not in used]; rights = [p for p in free if p[0] >= 12 and p not in used]
        if not lefts or not rights: break
        left, right = rng.choice(lefts), rng.choice(rights)
        if router.manhattan(left, right) < shape[0] - 3: continue
        discipline, bend, vertical = disciplines[len(commodities) % len(disciplines)]
        if discipline == "drainage" and left[2] < right[2]: left, right = right, left
        commodities.append(router.Commodity(left, right, discipline, bend, vertical)); used.update((left, right)); blocked.discard(left); blocked.discard(right)
    return router.Instance(shape, blocked, commodities)


def digest_payload(payload: dict) -> str:
    """Hash a canonical scene or terminal description."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    """Hash a source file for the run manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scene_fingerprints(instance) -> tuple[str, str]:
    """Return independent hashes for geometry and endpoint/discipline inputs."""
    terminals = [vars(item) for item in instance.commodities]
    scene_hash = digest_payload({
        "shape": instance.shape,
        "blocked": sorted(instance.blocked),
        "commodities": terminals,
    })
    terminal_hash = digest_payload(terminals)
    return scene_hash, terminal_hash


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("router", type=Path); parser.add_argument("output", type=Path); parser.add_argument("--seeds", type=int, default=20); args = parser.parse_args()
    router_path = args.router.resolve()
    router = load_router(router_path); rows = []
    for n_systems in (5, 9):
        for obstacle_rate in (0.045, 0.085):
            for seed in range(args.seeds):
                instance = generate(router, seed, n_systems, obstacle_rate)
                scene_hash, terminal_hash = scene_fingerprints(instance)
                for method in ("random", "guided"):
                    paths, trace, runtime = router.solve(instance, "pbs_random" if method == "random" else "stage3_only", seed)
                    validate_paths(instance, paths)
                    rows.append({"seed": seed, "scene_hash": scene_hash,
                                 "terminal_hash": terminal_hash,
                                 "n_systems": n_systems,
                                 "obstacle_rate": obstacle_rate, "method": method,
                                 "n_generated": len(instance.commodities),
                                 "routed": len(paths),
                                 "success": int(len(paths) == len(instance.commodities)),
                                 "objective": router.objective(instance, paths),
                                 "runtime_s": runtime, "validated": 1})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    cell_success = {}
    for n_systems in (5, 9):
        for obstacle_rate in (0.045, 0.085):
            cell = [row for row in rows if row["n_systems"] == n_systems
                    and row["obstacle_rate"] == obstacle_rate]
            cell_success[f"{n_systems}_{obstacle_rate}"] = {
                method: sum(row["success"] for row in cell if row["method"] == method)
                for method in ("random", "guided")
            }
    manifest = {
        "protocol": "2x2 system-count/obstacle-rate factorial, paired methods",
        "seeds": args.seeds,
        "rows": len(rows),
        "scenes": len(rows) // 2,
        "grid": [16, 12, 3],
        "systems": [5, 9],
        "obstacle_rates": [0.045, 0.085],
        "methods": ["random", "guided"],
        "cell_successes": cell_success,
        "all_routes_independently_validated": True,
        "source_sha256": file_digest(Path(__file__).resolve()),
        "router_sha256": file_digest(router_path),
        "output_sha256": file_digest(args.output),
        "output_bytes": args.output.stat().st_size,
        "python": sys.version,
        "platform": platform.platform(),
        "reproduction": (
            "python code/run_factorial_density.py code/run_routing_experiments.py "
            "data/revision_20261023/factorial_nested_800.csv --seeds 100"
        ),
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"rows={len(rows)} output={args.output}")


if __name__ == "__main__": main()
