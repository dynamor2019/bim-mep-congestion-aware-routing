"""Render corrected manuscript figures from archived observation-level data."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "fix_order": "#687480", "pbs_random": "#D97706", "stage1_only": "#2876B8",
    "stage3_only": "#07877C", "proposed": "#B43767", "random": "#687480",
    "guided": "#07877C", "length": "#2876B8", "blocker": "#D97706",
    "adaptive": "#775DA6", "pbs_static": "#253B53", "spatial_cbs": "#323B45",
    "conflict": "#9A6B45",
}
LABELS = {
    "fix_order": "Fixed order", "pbs_random": "MSPP + random",
    "stage1_only": "Static + random", "stage3_only": "Guided repair",
    "proposed": "Full method", "random": "Random repair", "guided": "Guided",
    "length": "Length only", "blocker": "Conflict blockers", "adaptive": "Adaptive",
    "pbs_static": "Spatial PBS", "spatial_cbs": "Spatial CBS",
    "conflict": "Conflict graph",
}
DENSITY_COLORS = {"low": "#687480", "medium": "#07877C", "high": "#B43767"}


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV into dictionaries."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def wilson(successes: int, total: int) -> tuple[float, float]:
    """Return a two-sided 95% Wilson interval."""
    if total <= 0:
        return 0.0, 0.0
    z = 1.959963984540054
    p = successes / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / den
    return max(0.0, center - half), min(1.0, center + half)


def style() -> None:
    """Apply restrained journal figure defaults."""
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 8, "axes.titlesize": 9,
        "axes.labelsize": 8, "axes.linewidth": 0.7, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "xtick.major.width": 0.65,
        "ytick.major.width": 0.65, "savefig.dpi": 600,
    })


def save(fig: plt.Figure, out_dir: Path, stem: str) -> None:
    """Save TIFF, PNG, and PDF versions with tight bounds."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".tif", ".png", ".pdf"):
        fig.savefig(out_dir / f"{stem}{suffix}", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot primary completion, penalized cost, runtime, and method legend."""
    methods = ["fix_order", "pbs_random", "stage1_only", "stage3_only", "proposed"]
    densities = ["low", "medium", "high"]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.3), constrained_layout=True)
    for j, density in enumerate(densities):
        subset = [r for r in rows if r["density"] == density]
        for i, method in enumerate(methods):
            vals = [r for r in subset if r["method"] == method]
            n = len(vals)
            successes = sum(int(r["success"]) for r in vals)
            rate = successes / n
            lo, hi = wilson(successes, n)
            x = i + (j - 1) * 0.19
            axes[0].errorbar(x, rate, yerr=[[rate - lo], [hi - rate]], fmt="o",
                             ms=4, capsize=2, lw=0.85, color=DENSITY_COLORS[density])
            costs = [float(r["normalized_cost"]) for r in vals]
            axes[1].plot(x, np.mean(costs), "o", ms=4, color=DENSITY_COLORS[density])
            axes[1].vlines(x, np.percentile(costs, 25), np.percentile(costs, 75),
                           lw=1.2, color=DENSITY_COLORS[density])
            times = [float(r["runtime_s"]) for r in vals]
            axes[2].plot(x, np.mean(times), "o", ms=4, color=DENSITY_COLORS[density])
    for ax in axes:
        ax.set_xticks(range(len(methods)), [LABELS[m] for m in methods], rotation=28, ha="right")
        ax.grid(axis="y", color="#D9DEE3", lw=0.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("Complete-scene success")
    axes[0].set_title("A  Feasibility (95% Wilson CI)", loc="left")
    axes[1].set_ylabel("Normalized penalized cost")
    axes[1].set_title("B  Mean and interquartile range", loc="left")
    axes[2].set_ylabel("Mean runtime (s)")
    axes[2].set_title("C  Runtime", loc="left")
    handles = [plt.Line2D([], [], marker="o", color=DENSITY_COLORS[d], linestyle="", label=d.title())
               for d in ("low", "medium", "high")]
    fig.legend(handles=handles, frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.06))
    save(fig, out_dir, "Figure_1")


def paired_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot paired feasibility outcomes against random repair by stress level."""
    fig, axes = plt.subplots(1, 3, figsize=(8.7, 3.0), sharey=True, constrained_layout=True)
    pairs = [("stage3_only", "Guided repair"), ("proposed", "Full method"), ("stage1_only", "Static + random")]
    for ax, (method, title) in zip(axes, pairs):
        for j, density in enumerate(("low", "medium", "high")):
            subset = [r for r in rows if r["density"] == density]
            lookup = {(r["seed"], r["method"]): int(r["success"]) for r in subset}
            gains = losses = ties = 0
            for seed in {r["seed"] for r in subset}:
                a = lookup[(seed, "pbs_random")]
                b = lookup[(seed, method)]
                gains += int(b > a)
                losses += int(b < a)
                ties += int(b == a)
            y = j
            ax.scatter(gains, y, color="#07877C", s=24, zorder=3)
            ax.scatter(-losses, y, color="#D97706", s=24, zorder=3)
            ax.plot([-losses, gains], [y, y], color="#C7CDD3", lw=1)
            ax.text(0, y + 0.13, f"{ties} ties", ha="center", va="bottom", fontsize=7, color="#606870")
        ax.axvline(0, color="#7A8793", lw=0.7)
        ax.set_title(title)
        ax.set_xlabel("Paired gains (right) / losses (left)")
        ax.set_yticks([0, 1, 2], ["Low", "Medium", "High"])
        ax.grid(axis="x", color="#E0E4E8", lw=0.55)
        ax.spines[["top", "right"]].set_visible(False)
    save(fig, out_dir, "Figure_2")


def sensitivity_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot high-stress sensitivity rates with Wilson intervals."""
    high = [r for r in rows if r["density"] == "high"]
    panels = [("weight", "Static weight $\\alpha$", [0, .5, 1, 2, 4]),
              ("fraction", "Destroy fraction $q$", [.15, .25, .4]),
              ("iterations", "Iterations $T$", [2, 5, 10])]
    fig, axes = plt.subplots(1, 3, figsize=(8.8, 3.0), constrained_layout=True)
    for ax, (analysis, title, values) in zip(axes, panels):
        xs, ys, lows, highs = [], [], [], []
        for x in values:
            subset = [r for r in high if r["analysis"] == analysis and float(r["parameter"]) == x]
            n = len(subset); k = sum(int(r["success"]) for r in subset)
            rate = k / n if n else 0
            lo, hi = wilson(k, n)
            xs.append(x); ys.append(rate); lows.append(rate - lo); highs.append(hi - rate)
        ax.errorbar(xs, ys, yerr=[lows, highs], color=COLORS["proposed"], marker="o", ms=4,
                    lw=1.0, capsize=2, label="Guided configuration")
        ax.set_title(title)
        ax.set_ylim(0, .5)
        ax.set_ylabel("Complete-scene success" if ax is axes[0] else "")
        ax.set_xlabel("Setting")
        ax.grid(axis="y", color="#D9DEE3", lw=.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1].legend(frameon=False, fontsize=7)
    save(fig, out_dir, "Figure_4")


def ablation_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot completion and penalized-cost contrasts for the component ablation."""
    methods = ["pbs_random", "stage1_only", "stage3_only", "proposed"]
    densities = ["low", "medium", "high"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), constrained_layout=True)
    for j, density in enumerate(densities):
        subset = [r for r in rows if r["density"] == density]
        for i, method in enumerate(methods):
            vals = [r for r in subset if r["method"] == method]
            n = len(vals); k = sum(int(r["success"]) for r in vals)
            rate = k / n; lo, hi = wilson(k, n)
            x = i + (j - 1) * 0.07
            axes[0].errorbar(x, rate, yerr=[[rate - lo], [hi - rate]], fmt="o", ms=4,
                             capsize=2, color=COLORS[method], lw=.8)
            costs = [float(r["normalized_cost"]) for r in vals]
            axes[1].plot(x, np.mean(costs), "o", ms=4, color=COLORS[method])
            axes[1].vlines(x, np.percentile(costs, 25), np.percentile(costs, 75),
                           color=COLORS[method], lw=1.2)
    for ax in axes:
        ax.set_xticks(range(len(methods)), [LABELS[m] for m in methods], rotation=28, ha="right")
        ax.grid(axis="y", color="#D9DEE3", lw=.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylim(0, 1.05); axes[0].set_ylabel("Complete-scene success")
    axes[0].set_title("A  Feasibility (95% Wilson CI)", loc="left")
    axes[1].set_ylabel("Normalized penalized cost")
    axes[1].set_title("B  Mean and interquartile range", loc="left")
    handles = [plt.Line2D([], [], marker="o", color=DENSITY_COLORS[d], linestyle="", label=d.title())
               for d in ("low", "medium", "high")]
    axes[1].legend(handles=handles, frameon=False, fontsize=7)
    save(fig, out_dir, "Figure_3")


def holdout_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot holdout success counts and paired differences by method."""
    methods = ["random", "static_random", "guided", "guided_select_only", "length", "blocker", "conflict", "adaptive", "pbs_static", "spatial_cbs"]
    labels = ["Random", "Static + random", "Guided", "Guided select only", "Length", "Blocker", "Conflict graph", "Adaptive", "Spatial PBS", "Spatial CBS"]
    fig, ax = plt.subplots(figsize=(7.2, 3.5), constrained_layout=True)
    for i, method in enumerate(methods):
        subset = [r for r in rows if r["method"] == method]
        n = len(subset); k = sum(int(r["success"]) for r in subset)
        lo, hi = wilson(k, n)
        ax.errorbar(k, i, xerr=[[max(0.0, k - n * lo)], [max(0.0, n * hi - k)]], fmt="o", ms=4,
                    capsize=2, color=COLORS.get(method, "#555555"), lw=.9)
    ax.set_yticks(range(len(methods)), labels)
    ax.invert_yaxis(); ax.set_xlim(0, 36)
    ax.set_xlabel("Complete scenes / 100 (95% Wilson CI)")
    ax.grid(axis="x", color="#D9DEE3", lw=.55)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, out_dir, "Figure_6")


def factor_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot completion by independently varied system count and obstacle rate."""
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0), sharey=True, constrained_layout=True)
    for ax, systems in zip(axes, (5, 9)):
        for method, color, marker in (("random", COLORS["random"], "o"), ("guided", COLORS["guided"], "s")):
            xs, ys, lo_err, hi_err = [], [], [], []
            for rate in (.045, .085):
                subset = [r for r in rows if int(r["n_systems"]) == systems and float(r["obstacle_rate"]) == rate and r["method"] == method]
                n = len(subset); k = sum(int(r["success"]) for r in subset); p = k / n
                lo, hi = wilson(k, n)
                xs.append(rate * 100); ys.append(p); lo_err.append(p - lo); hi_err.append(hi - p)
            ax.errorbar(xs, ys, yerr=[lo_err, hi_err], color=color, marker=marker, ms=4, lw=1, capsize=2, label=LABELS[method])
        ax.set_title(f"{systems} systems")
        ax.set_xlabel("Obstacle probability (%)")
        ax.grid(axis="y", color="#D9DEE3", lw=.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Complete-scene success")
    axes[0].legend(frameon=False, fontsize=7)
    save(fig, out_dir, "Figure_7")


def scaling_figure(rows: list[dict[str, str]], out_dir: Path) -> None:
    """Plot completion and runtime for matched-density scale stress tests."""
    sizes = ["16x12x3", "24x18x4", "32x24x5"]
    labels = ["9 systems", "27 systems", "60 systems"]
    methods = [("random", "Random"), ("blocker", "Blocker"), ("adaptive", "Adaptive"), ("pbs_static", "Spatial PBS")]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), constrained_layout=True)
    for method, label in methods:
        means_success, means_time = [], []
        for size in sizes:
            subset = [r for r in rows if r["shape"] == size and r["method"] == method]
            means_success.append(np.mean([float(r["success"]) for r in subset]))
            means_time.append(np.mean([float(r["runtime_s"]) + float(r["initial_runtime_s"]) for r in subset]))
        color = COLORS.get(method, "#555555")
        axes[0].plot(range(3), means_success, marker="o", ms=3.7, lw=1.1, color=color, label=label)
        axes[1].plot([9, 27, 60], means_time, marker="o", ms=3.7, lw=1.1, color=color, label=label)
    axes[0].set_xticks(range(3), labels)
    axes[0].set_ylabel("Complete-scene success")
    axes[0].set_ylim(-.03, 1.03)
    axes[1].set_xticks([9, 27, 60]); axes[1].set_xlabel("Number of systems")
    axes[1].set_ylabel("Mean total runtime (s)")
    for ax in axes:
        ax.grid(axis="y", color="#D9DEE3", lw=.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=7)
    save(fig, out_dir, "Figure_8")


def ifc_figure(path: Path, out_dir: Path) -> None:
    """Plot broad-phase IFC intersection candidates without implying clash rates."""
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    checks = data["intersection_checks"]
    clearance = [item["clearance_m"] for item in checks]
    counts = [item["nonowner_box_intersecting_edges"] for item in checks]
    fig, ax = plt.subplots(figsize=(5.2, 2.8), constrained_layout=True)
    ax.plot(clearance, counts, color="#2876B8", marker="o", lw=1.2, ms=4)
    ax.set_xlabel("Assumed isotropic clearance (m)")
    ax.set_ylabel("Candidate port-segment / AABB intersections")
    ax.set_title("Conservative broad-phase screen; not exact clashes", loc="left")
    ax.grid(axis="y", color="#D9DEE3", lw=.55)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, out_dir, "Figure_S1")


def main() -> None:
    """Render all corrected quantitative figures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--sensitivity", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--conflict-neighborhood", type=Path)
    parser.add_argument("--spatial-cbs", type=Path)
    parser.add_argument("--factorial", type=Path, required=True)
    parser.add_argument("--scaling", type=Path, required=True)
    parser.add_argument("--ifc-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    style()
    main_rows = read_rows(args.main)
    main_figure(main_rows, args.output)
    paired_figure(main_rows, args.output)
    ablation_figure(main_rows, args.output)
    sensitivity_figure(read_rows(args.sensitivity), args.output)
    holdout_rows = read_rows(args.holdout)
    if args.conflict_neighborhood:
        holdout_rows.extend(read_rows(args.conflict_neighborhood))
    if args.spatial_cbs:
        holdout_rows.extend(read_rows(args.spatial_cbs))
    holdout_figure(holdout_rows, args.output)
    factor_figure(read_rows(args.factorial), args.output)
    scaling_figure(read_rows(args.scaling), args.output)
    ifc_figure(args.ifc_audit, args.output)


if __name__ == "__main__":
    main()
