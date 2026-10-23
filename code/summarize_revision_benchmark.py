"""Paired estimates and uncertainty for the independently validated benchmark."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, rankdata, wilcoxon

from run_sensitivity_analysis import wilson_interval


def paired_result(baseline, comparison):
    """Report two-sided exact feasibility inference and paired bootstrap CI."""
    seeds = sorted(set(baseline) & set(comparison))
    base = np.asarray([int(baseline[s]["success"]) for s in seeds])
    other = np.asarray([int(comparison[s]["success"]) for s in seeds])
    gain = int(((base == 0) & (other == 1)).sum())
    loss = int(((base == 1) & (other == 0)).sum())
    delta = other - base
    gain_ci = binomtest(gain, len(seeds)).proportion_ci(confidence_level=.975, method="exact")
    loss_ci = binomtest(loss, len(seeds)).proportion_ci(confidence_level=.975, method="exact")
    rng = np.random.default_rng(718)
    resampled = delta[rng.integers(0, len(delta), (20000, len(delta)))].mean(axis=1)
    cost_diff = np.asarray([float(baseline[s]["objective"]) - float(comparison[s]["objective"]) for s in seeds])
    nonzero = cost_diff[np.abs(cost_diff) > 1e-8]
    if len(nonzero):
        ranks = rankdata(np.abs(nonzero))
        rank_biserial = float((ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum()) / ranks.sum())
        cost_p = float(wilcoxon(nonzero, alternative="two-sided").pvalue)
    else:
        rank_biserial, cost_p = 0.0, 1.0
    joint = [s for s in seeds if int(baseline[s]["success"]) and int(comparison[s]["success"])]
    return {"n": len(seeds), "both_success": int(((base == 1) & (other == 1)).sum()),
            "both_failure": int(((base == 0) & (other == 0)).sum()),
            "gain": gain, "loss": loss, "success_difference": float(delta.mean()),
            "paired_bootstrap_ci95": np.quantile(resampled, [.025, .975]).tolist(),
            "conservative_difference_ci95": [float(gain_ci.low - loss_ci.high), float(gain_ci.high - loss_ci.low)],
            "exact_mcnemar_two_sided": float(binomtest(gain, gain + loss).pvalue) if gain + loss else 1.0,
            "cost_ties": len(seeds) - len(nonzero), "cost_wilcoxon_two_sided": cost_p,
            "cost_rank_biserial": rank_biserial, "joint_feasible_n": len(joint),
            "joint_feasible_cost_delta_mean": float(np.mean([float(comparison[s]["physical_cost"]) - float(baseline[s]["physical_cost"]) for s in joint])) if joint else None}


def summarize(rows):
    """Check pairing and aggregate estimates without dropping failed scenes."""
    grouped = {}
    for row in rows:
        key = row["method"]
        if int(row["validated"]) != 1:
            raise ValueError("Unvalidated route row")
        seed = int(row["seed"])
        if seed in grouped.setdefault(key, {}):
            raise ValueError("Duplicate method/seed")
        grouped[key][seed] = row
    summary = []
    expected = set(grouped["random"])
    for method, data in sorted(grouped.items()):
        if set(data) != expected:
            raise ValueError("Unpaired experiment")
        if any(data[s]["scene_hash"] != grouped["random"][s]["scene_hash"] for s in expected):
            raise ValueError("Scene mismatch")
        n = len(data)
        successes = sum(int(r["success"]) for r in data.values())
        summary.append({"method": method, "n": n, "successes": successes,
                        "success_rate": successes / n, "wilson_ci95": wilson_interval(successes, n),
                        "routed_mean": float(np.mean([int(r["routed"]) for r in data.values()])),
                        "runtime_mean_s": float(np.mean([float(r["runtime_s"]) for r in data.values()])),
                        "runtime_max_s": max(float(r["runtime_s"]) for r in data.values()),
                        "status_counts": {status: sum(r["status"] == status for r in data.values()) for status in sorted({r["status"] for r in data.values()})}})
    pairs = {method: paired_result(grouped["random"], data) for method, data in grouped.items() if method != "random"}
    ordered = sorted(pairs, key=lambda m: pairs[m]["exact_mcnemar_two_sided"])
    adjusted = 0.0
    for index, method in enumerate(ordered):
        adjusted = max(adjusted, min(1.0, (len(ordered) - index) * pairs[method]["exact_mcnemar_two_sided"]))
        pairs[method]["mcnemar_holm_adjusted"] = adjusted
    return {"summary": summary, "paired_against_random": pairs,
            "inference": f"two-sided exact paired feasibility; Holm correction across {len(pairs)} comparisons; difference CI uses Bonferroni-combined 97.5% Clopper-Pearson intervals for paired gain/loss probabilities; bootstrap also archived, but zero discordances do not prove equivalence; exploratory on same synthetic generator"}


def main():
    """Summarize one complete cohort CSV."""
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8", newline="") as handle:
        payload = summarize(list(csv.DictReader(handle)))
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
