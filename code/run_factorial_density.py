"""Factorial stress test separating system count from obstacle probability."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import random
import sys
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("router", type=Path); parser.add_argument("output", type=Path); parser.add_argument("--seeds", type=int, default=20); args = parser.parse_args()
    router = load_router(args.router); rows = []
    for n_systems in (5, 9):
        for obstacle_rate in (0.045, 0.085):
            for seed in range(args.seeds):
                instance = generate(router, seed, n_systems, obstacle_rate)
                for method in ("random", "guided"):
                    paths, trace, runtime = router.solve(instance, "pbs_random" if method == "random" else "stage3_only", seed)
                    rows.append({"seed": seed, "n_systems": n_systems, "obstacle_rate": obstacle_rate, "method": method, "n_generated": len(instance.commodities), "routed": len(paths), "success": int(len(paths) == len(instance.commodities)), "objective": router.objective(instance, paths), "runtime_s": runtime})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    print(f"rows={len(rows)} output={args.output}")


if __name__ == "__main__": main()
