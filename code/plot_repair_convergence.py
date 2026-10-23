"""Plot matched incumbent feasibility traces for random and guided repair."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


FAILURE_PENALTY = 10_000.0
METHODS = ("random", "guided")
COLORS = {"random": "#687480", "guided": "#07877C"}
LABELS = {"random": "MSPP + random repair", "guided": "Congestion-guided repair"}


def read_matched_traces(path: Path) -> dict[str, list[dict[str, object]]]:
    """Load and validate paired traces from the archived high-stress cohort."""
    grouped: dict[str, dict[str, dict[str, object]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            method = row["method"]
            if method not in METHODS:
                continue
            trace = json.loads(row["trace"])
            if not trace or int(row["validated"]) != 1:
                raise ValueError(f"Missing trace or failed validation: {row['seed']} {method}")
            times = [float(point["t"]) for point in trace]
            objectives = [float(point["objective"]) for point in trace]
            if times[0] != 0.0 or times != sorted(times):
                raise ValueError(f"Invalid trace clock: {row['seed']} {method}")
            if any(b > a + 1e-7 for a, b in zip(objectives, objectives[1:])):
                raise ValueError(f"Incumbent objective increased: {row['seed']} {method}")
            routed = [_routed_count(value, int(row["total"])) for value in objectives]
            if routed[-1] != int(row["routed"]):
                raise ValueError(f"Trace endpoint mismatch: {row['seed']} {method}")
            trace_rows = [
                {"t": t, "objective": objective, "routed": count}
                for t, objective, count in zip(times, objectives, routed)
            ]
            grouped.setdefault(row["seed"], {})[method] = {
                "scene_hash": row["scene_hash"],
                "initial_objective": float(row["initial_objective"]),
                "initial_routed": int(row["initial_routed"]),
                "success": int(row["success"]),
                "total": int(row["total"]),
                "trace": trace_rows,
            }

    pairs = {method: [] for method in METHODS}
    for seed, methods in sorted(grouped.items(), key=lambda item: int(item[0])):
        if set(methods) != set(METHODS):
            raise ValueError(f"Unpaired method rows for seed {seed}")
        random_row, guided_row = (methods[name] for name in METHODS)
        for key in ("scene_hash", "initial_objective", "initial_routed", "total"):
            if random_row[key] != guided_row[key]:
                raise ValueError(f"Pair mismatch for seed {seed}: {key}")
        for method in METHODS:
            pairs[method].append(methods[method])
    if len(pairs["random"]) != 100:
        raise ValueError(f"Expected 100 matched scenes; found {len(pairs['random'])}")
    return pairs


def _routed_count(objective: float, total: int) -> int:
    """Recover routed count from the lexicographic 10,000-unit failure penalty."""
    failures = math.floor(objective / FAILURE_PENALTY)
    physical_cost = objective - failures * FAILURE_PENALTY
    if failures > total or physical_cost < -1e-6 or physical_cost >= FAILURE_PENALTY:
        raise ValueError(f"Objective cannot be decomposed: {objective}")
    return total - failures


def _profile(rows: list[dict[str, object]], axis: np.ndarray, by_time: bool) -> np.ndarray:
    """Return complete-scene success at each iteration or elapsed-time point."""
    values = np.zeros((len(rows), len(axis)), dtype=float)
    for row_index, row in enumerate(rows):
        trace = row["trace"]
        times = [point["t"] for point in trace]
        for point_index, coordinate in enumerate(axis):
            if by_time:
                trace_index = max(0, bisect.bisect_right(times, coordinate) - 1)
            else:
                trace_index = min(int(coordinate), len(trace) - 1)
            values[row_index, point_index] = float(
                trace[trace_index]["routed"] == row["total"]
            )
    return values


def _bootstrap_interval(values: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return pointwise percentile intervals from scene-level resampling."""
    rng = np.random.default_rng(seed)
    lower = np.empty(values.shape[1], dtype=float)
    upper = np.empty(values.shape[1], dtype=float)
    for column in range(values.shape[1]):
        samples = rng.integers(0, values.shape[0], size=(2000, values.shape[0]))
        means = values[samples, column].mean(axis=1)
        lower[column], upper[column] = np.quantile(means, [0.025, 0.975])
    return lower, upper


def create_figure(rows: dict[str, list[dict[str, object]]], output: Path) -> None:
    """Render repair-iteration and wall-clock traces with bootstrap bands."""
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 8, "axes.titlesize": 9,
        "axes.labelsize": 8, "axes.linewidth": 0.7, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "savefig.dpi": 600,
    })
    iterations = np.arange(21)
    times = np.linspace(0.0, 1.1, 23)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.20, top=0.80, wspace=0.22)
    for panel_index, (axis, by_time, seed) in enumerate(
        ((iterations, False, 20261024), (times, True, 20261025))
    ):
        ax = axes[panel_index]
        for method in METHODS:
            profile = _profile(rows[method], axis, by_time)
            mean = profile.mean(axis=0) * 100
            low, high = _bootstrap_interval(profile, seed)
            ax.plot(axis, mean, color=COLORS[method], lw=1.35, label=LABELS[method])
            ax.fill_between(axis, low * 100, high * 100,
                            color=COLORS[method], alpha=0.17, linewidth=0)
        ax.set_ylim(0, 30)
        ax.set_yticks(np.arange(0, 31, 5))
        ax.set_ylabel("Complete-scene success (%)")
        ax.grid(axis="y", color="#D9DEE3", lw=0.55)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_title("A  Repair iterations", loc="left")
    axes[0].set_xlabel("Iteration")
    axes[0].set_xticks([0, 5, 10, 15, 20])
    axes[1].set_title("B  Recorded repair time", loc="left")
    axes[1].set_xlabel("Elapsed time (s)")
    axes[1].set_xticks(np.arange(0, 1.01, 0.2))
    axes[1].axvline(1.0, color="#39434D", linestyle="--", lw=0.8)
    axes[1].text(0.98, 0.96, "1-s nominal cap", transform=axes[1].transAxes,
                 fontsize=7, color="#39434D", va="top", ha="right")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.98), fontsize=7.5)
    output.mkdir(parents=True, exist_ok=True)
    for suffix in (".tif", ".png", ".pdf"):
        fig.savefig(output / f"Figure_6{suffix}", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> None:
    """Validate input traces and write the convergence figure files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path,
                        default=Path("data/revision_20261023/high_stress_holdout_1000.csv"))
    parser.add_argument("--output", type=Path,
                        default=Path("figures/revision_20261024_convergence"))
    args = parser.parse_args()
    rows = read_matched_traces(args.data)
    create_figure(rows, args.output)
    successes = {method: sum(int(row["success"]) for row in rows[method])
                 for method in METHODS}
    print(f"Validated {len(rows['random'])} matched traces; final success: {successes}")


if __name__ == "__main__":
    main()
