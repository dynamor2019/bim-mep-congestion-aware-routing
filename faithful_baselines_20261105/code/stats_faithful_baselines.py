"""Paired statistics for the spatial CBS, PBS and BCBS(1.5) runs against main_150_raw.csv.

Completion: exact two-sided McNemar per density, Holm across the three densities
within each solver-versus-comparator family. Physical cost: paired bootstrap of the
mean difference on jointly completed scenes (seed 20261104, 10,000 resamples).
"""

import csv
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[1] / "data" / "revision_20261023" / "main_150_raw.csv"
D = ("low", "medium", "high")
SOLVERS = {
    "CBS": HERE.parent / "data" / "formal_cbs" / "spatial_cbs_raw.csv",
    "PBS": HERE.parent / "data" / "formal_pbs" / "spatial_pbs_raw.csv",
    "BCBS1.5": HERE.parent / "data" / "formal_bcbs" / "spatial_bcbs_raw.csv",
}
COMPARATORS = ("pbs_random", "stage3_only", "proposed")


def load(path):
    return {(r["density"], int(r["seed"])): r for r in csv.DictReader(open(path, encoding="utf-8"))}


main = {}
for r in csv.DictReader(open(MAIN, encoding="utf-8")):
    main.setdefault(r["method"], {})[(r["density"], int(r["seed"]))] = r


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, ps[i] * (len(ps) - rank)))
        adj[i] = running
    return adj


print("== Completion counts (of 50)")
for name, path in SOLVERS.items():
    rows = load(path)
    print(name, [sum(int(rows[(d, s)]["success"]) for s in range(50)) for d in D])
for m in COMPARATORS:
    print(m, [sum(int(main[m][(d, s)]["success"]) for s in range(50)) for d in D])

print("\n== Exact McNemar (solver-only / comparator-only), Holm over densities")
for name, path in SOLVERS.items():
    rows = load(path)
    for comp in COMPARATORS:
        res = []
        for d in D:
            b = sum(1 for s in range(50) if rows[(d, s)]["success"] == "1" and main[comp][(d, s)]["success"] != "1")
            c = sum(1 for s in range(50) if rows[(d, s)]["success"] != "1" and main[comp][(d, s)]["success"] == "1")
            p = binomtest(min(b, c), b + c, 0.5).pvalue if b + c else 1.0
            res.append((d, b, c, p))
        adj = holm([r[3] for r in res])
        print(f"{name:8} vs {comp:11} " + "  ".join(
            f"{d}: {b}/{c} p={p:.4g} holm={a:.4g}" for (d, b, c, p), a in zip(res, adj)))

print("\n== Physical cost, solver minus pbs_random, jointly completed")
rng = np.random.default_rng(20261104)
for name, path in SOLVERS.items():
    rows = load(path)
    for d in D:
        diffs = np.array([float(rows[(d, s)]["cost"]) - float(main["pbs_random"][(d, s)]["cost"])
                          for s in range(50)
                          if rows[(d, s)]["success"] == "1" and main["pbs_random"][(d, s)]["success"] == "1"])
        if len(diffs) == 0:
            print(f"{name:8} {d:7} n=0")
            continue
        boot = [diffs[rng.integers(0, len(diffs), len(diffs))].mean() for _ in range(10000)]
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"{name:8} {d:7} n={len(diffs)} mean={diffs.mean():+.3f} CI=[{lo:+.3f}, {hi:+.3f}]")

print("\n== Runtime (s): median / max")
for name, path in SOLVERS.items():
    rows = load(path)
    for d in D:
        rt = sorted(float(rows[(d, s)]["runtime_s"]) for s in range(50))
        print(f"{name:8} {d:7} median={np.median(rt):.2f} max={rt[-1]:.2f}")
