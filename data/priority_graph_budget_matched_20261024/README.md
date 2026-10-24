# Equal-Budget Priority-Search Rerun

This archive reruns the 100-scene high-density comparison (seeds 320000-320099) against the current repository code at base commit `3c4570e`, preserving foreign-terminal avoidance and soft-occupancy behavior. Each method received a nominal 1.2-s per-scene wall-clock cap. A* checks deadlines cooperatively, so wall time can slightly exceed the cap.

MSPP-random restarts completed 22/100 scenes; bounded permanent-space priority search completed 20/100 (four candidate-only, six baseline-only; exact two-sided McNemar p=0.7539). Mean routed demand was 7.31 vs 7.20 systems. Mean runtimes were 1.051 vs 1.028 s; maxima were 1.233 vs 1.201 s. All 200 outputs passed independent path validation. The result is inconclusive and does not establish priority-search superiority or canonical temporal MAPF-PBS performance.

Reproduce from the repository root:

```powershell
python code/run_priority_graph_pilot.py --scenes 100 --first-seed 320000 --time-budget-s 1.2 --output results/priority_graph_budget_matched_replay
```

The command writes a raw CSV and summary JSON. SHA-256 hashes for this archive are listed in `SHA256SUMS.txt`.
