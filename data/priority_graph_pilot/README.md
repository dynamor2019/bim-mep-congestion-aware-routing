# Permanent Priority-Graph Pilot

Exploratory paired pilot on 100 independently generated high-density scenes (nine systems per scene), seeds 300000-300099. Each scene has outputs from MSPP-random repair and bounded permanent-space priority-graph search (16-node cap).

The priority-graph method is a static permanent-occupancy adaptation. It is not canonical temporal MAPF-PBS, and its compute budget is not matched to the repair baseline.

Reproduce from the repository root:

```powershell
python code/run_priority_graph_pilot.py --scenes 100 --first-seed 300000 --max-nodes 16 --output data/priority_graph_pilot
```

The runner saves paired raw observations and a summary. Its independent validator checks endpoints, grid bounds, adjacency, blocked cells, foreign terminals, drainage direction, and shared internal vertices. Current result: 12/100 versus 10/100 complete scenes; 3 candidate-only and 1 baseline-only completion; exact two-sided McNemar p=0.625. This is inconclusive, exploratory evidence.
