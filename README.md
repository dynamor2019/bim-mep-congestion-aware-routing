# Congestion-Aware Routing for Multi-System MEP Coordination

Code and observation-level evidence for manuscript AUTCON-D-26-05125. This revision distinguishes synthetic spatial-routing evidence from temporal MAPF results and from construction-valid BIM routing.

## Corrected revision evidence

`data/revision_20261023/` contains the corrected 150-scene benchmark (750 method outputs), 990-observation sensitivity study, 100-scene/nine-method high-stress holdout (900 outputs, including a conflict-graph neighborhood control), a same-scene permanent-space CBS diagnostic (100 outputs), nested factor study (800 method-runs), matched-density scale stress (180 outputs), and full native IFC geometry/port audit. The original 150-scene paths were independently checked; all 750 outputs passed route validation and deterministic replay. Archived holdout, CBS and scale outputs carry per-row validation flags.

Recheck the archived tables and regenerate figures:

```powershell
python -m pip install -r requirements.txt
python code/validate_revision_evidence.py --data data/revision_20261023
python code/plot_corrected_revision.py `
  --main data/revision_20261023/main_150_raw.csv `
  --sensitivity data/revision_20261023/sensitivity_990_raw.csv `
  --holdout data/revision_20261023/high_stress_holdout_800.csv `
  --conflict-neighborhood data/revision_20261023/conflict_neighborhood_holdout_100.csv `
  --spatial-cbs data/revision_20261023/spatial_cbs_holdout_100.csv `
  --factorial data/revision_20261023/factorial_nested_800.csv `
  --scaling data/revision_20261023/scale_matched_density_180.csv `
  --ifc-audit data/revision_20261023/ifc_full_geometry_audit.json `
  --output figures/revision_20261023
```

The validator checks row counts, per-scene/method balance, validation flags, both IFC audits, and Digital Hub identity/semantic/sample/topology invariants. The plotting script regenerates Figures 1–4, 6–8, and Supplementary Figure S1 from the archived observations. TIFF, PNG, and PDF outputs are generated.

## Re-run protocols

The archived tables are the evidence used in the manuscript. These commands rerun the corresponding protocols into a separate folder; stochastic wall-clock-limited runs can differ in runtime and completed repairs across machines. Do not overwrite archived tables without repeating the analysis and updating the manuscript.

```powershell
python code/run_routing_experiments.py --seeds 50 --output results/replay_main
python code/run_sensitivity_analysis.py --seeds 15 --output results/replay_sensitivity
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --methods random static_random guided guided_select_only length blocker conflict adaptive pbs_static --output results/replay_holdout
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort cbs_holdout --methods spatial_cbs --output results/replay_spatial_cbs
python code/run_factorial_density.py code/run_routing_experiments.py results/replay_factorial.csv --seeds 100
python code/run_scaling_matched_density.py --seeds 15 --seconds 1 --iterations 20 --nodes 256 --output results/replay_scaling.csv
```

The holdout runner includes spatial PBS/CBS and conflict-graph neighborhood adaptations. These use permanent occupancy and are not faithful temporal MAPF baselines. The conflict selector completed 13/100 scenes, equal to blocker repair and below random repair (17/100); the CBS diagnostic completed 0/100 under its one-second cap (94 budget terminations; six individually infeasible). Run regression tests with `python -m unittest discover -s code -v`.

## What the added comparisons do and do not establish

- The high-stress comparison includes a bounded permanent-space priority-tree adaptation, failed-route blocker and conflict-graph neighborhood controls, length-only and adaptive repair. A separate same-scene CBS adaptation returned no complete sets under the one-second cap. These are not faithful implementations of temporal MAPF-PBS/CBS or MAPF-LNS. No secondary method significantly outperformed random repair after Holm adjustment.
- The adaptive/multi-operator holdout tied random completion at 17/100; matched-density tests completed no scenes at 27 or 60 systems. This is negative evidence about the present prototype, not evidence of general scalability.
- The earlier IFC boundary audit covers 4,091 selected components, 4,054 extractable geometries, 8,460 placed ports and 4,050 explicit port relations. Those counts are not route evidence.
- The added RWTH Digital Hub audit covers four co-registered IFC4 files (architecture, heating, plumbing, ventilation), with 65 systems, 8,497 placed ports, 4,208 explicit port relations, native service dimensions, slope properties, and fitting geometry. The 287-MEP/162-architecture AABB sample is only broad-phase screening. No accepted reroute targets or engineer-reviewed outcomes exist, and the routing solver has not been run on this model.

Reproduce the Digital Hub audit after downloading the four IFC files listed in `data/IFC_SOURCE.md` into a local folder:

```powershell
python code/audit_digital_hub_ifc.py path/to/digital_hub_ifc data/revision_20261023/digital_hub --max-per-type 25
```

The script records source SHA-256 hashes, checks IFC model identity and coordinate metadata, extracts native port/system graphs and segment dimensions, and generates a deterministic geometry sample. AABB candidates are not exact clashes or route outcomes.

Recalculate the system-level topology diagnostic from the cached native port graphs without rerunning geometry extraction:

```powershell
python code/summarize_digital_hub_topology.py `
  data/revision_20261023/digital_hub `
  data/revision_20261023/digital_hub/digital_hub_native_topology.json
```

The reported component counts describe the extracted graph under explicit port relations plus stated within-segment/fitting assumptions. Multiple components do not prove physical disconnection and do not establish accepted alternative routes. The current point-to-point solver cannot be applied to arbitrary pairs from a multi-terminal system as if these were project-approved reroutes.

Legacy scripts and files outside `revision_20261023/` are retained for provenance. The current scale table was regenerated from the published `run_scaling_matched_density.py` generator after the earlier table's source was found missing; the withdrawn earlier file remains only in the local revision audit history. Replay commands write new outputs, and time-limited runtimes or outcomes can vary across machines. The archived tables remain the authoritative evidence for the current manuscript.

The old `v1.0.0` tag predates these corrections. This corrected archive, including the native topology diagnostic, is versioned as `v2.2.0`. No DOI is currently claimed.
