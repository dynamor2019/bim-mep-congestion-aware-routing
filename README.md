# Congestion-Aware Routing for Multi-System MEP Coordination

Code and observation-level evidence for manuscript AUTCON-D-26-05125. This revision distinguishes synthetic spatial-routing evidence from temporal MAPF results and from construction-valid BIM routing.

## Corrected revision evidence

`data/revision_20261023/` contains the corrected 150-scene benchmark (750 method outputs), 990-observation sensitivity study, 100-scene/ten-method high-stress holdout (1,000 outputs), permanent-space CBS/PBS/LNS diagnostics, two matched binary multi-commodity-flow MILP diagnostics, a 2x2 system-count/obstacle-rate factorial (400 scenes; 800 method outputs), matched-density scale stress, a 90-scene/180-output adaptive-repair comparison, public IFC audits, and compatibility audits of the seven-case plant-room dataset and Samuel Macalister sample-house MEP IFC. The factorial cells use 100 seeds each; with 5/9 systems crossed with 4.5%/8.5% random obstacles, MSPP-random completion was 97%, 93%, 34%, and 9%, while guided repair completed 96%, 91%, 31%, and 12%. The spatial LNS2-style run is an explicit permanent-space adaptation, not a reproduction of temporal MAPF-LNS2. It completed 17/100 scenes, tied random repair, and had one paired gain and one paired loss (Holm-adjusted exact McNemar p=1.00). All heuristic and MILP route outputs passed independent validation.

Recheck the archived tables and regenerate figures:

```powershell
python -m pip install -r requirements.txt
python code/validate_revision_evidence.py --data data/revision_20261023
python code/plot_corrected_revision.py `
  --main data/revision_20261023/main_150_raw.csv `
  --sensitivity data/revision_20261023/sensitivity_990_raw.csv `
  --holdout data/revision_20261023/high_stress_holdout_1000.csv `
  --spatial-cbs data/revision_20261023/spatial_cbs_holdout_100.csv `
  --factorial data/revision_20261023/factorial_nested_800.csv `
  --scaling data/revision_20261023/scale_matched_density_180.csv `
  --ifc-audit data/revision_20261023/ifc_full_geometry_audit.json `
  --output figures/revision_20261023
```

The validator checks row counts, per-scene/method balance, factorial cell pairing and checksums, validation flags, IFC audits, Digital Hub identity/semantic/sample/topology invariants, and the paired adaptive, CBS-incumbent, and plant-room compatibility archives. The additional sample-house audit is reproduced with `python code/audit_public_ifc_model.py --ifc data/ifc_bench/samuel_macalister_sample_house/mep.ifc --source-url https://github.com/opensourceBIM/TestFiles --license "GNU GPL v3" --output data/revision_20261023/ifc_bench_house_audit.json`. The plotting script regenerates Figures 1–4, 6–8, and Supplementary Figure S1 from the archived observations. TIFF, PNG, and PDF outputs are generated.

## Re-run protocols

The archived tables are the evidence used in the manuscript. These commands rerun the corresponding protocols into a separate folder; stochastic wall-clock-limited runs can differ in runtime and completed repairs across machines. Do not overwrite archived tables without repeating the analysis and updating the manuscript.

```powershell
python code/run_routing_experiments.py --seeds 50 --output results/replay_main
python code/run_sensitivity_analysis.py --seeds 15 --output results/replay_sensitivity
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --methods random static_random guided guided_select_only length blocker conflict adaptive spatial_mapf_lns2 pbs_static --output results/replay_holdout
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort cbs_holdout --methods spatial_cbs --output results/replay_spatial_cbs
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --seconds 30 --nodes 10000 --methods pbs_static --output results/replay_pbs_30s
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --seconds 30 --iterations 5000 --nodes 10000 --methods random --output results/replay_random_30s
python code/run_exact_mcf_baseline.py --seeds 100 --start-seed 100000 --time-limit 1 --output results/replay_exact_mcf_1s
python code/run_exact_mcf_baseline.py --seeds 100 --start-seed 100000 --time-limit 30 --output results/replay_exact_mcf_30s
python code/run_factorial_density.py code/run_routing_experiments.py results/replay_factorial.csv --seeds 100
python code/run_scaling_matched_density.py --seeds 15 --seconds 1 --iterations 20 --nodes 256 --output results/replay_scaling.csv
python code/run_advanced_validation.py --seeds 5 --output results/replay_advanced_validation
python code/run_matched_adaptive_scale.py --seeds 30 --start-seed 50000 --output results/replay_matched_adaptive_scale.csv
python code/summarize_matched_adaptive_scale.py `
  data/revision_20261023/matched_adaptive_scale_90.csv `
  results/matched_adaptive_scale_summary.json
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --cohort cbs_incumbent_5s --seconds 5 --iterations 100 --nodes 10000 --methods random spatial_cbs --output results/cbs_incumbent_5s
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --cohort cbs_optional_matched_5s --seconds 5 --iterations 10000 --nodes 10000 --methods random spatial_cbs --output results/cbs_optional_matched_5s
python code/run_revision_benchmark.py --seeds 60 --start-seed 101000 --cohort cbs_total_matched_5s --seconds 4.8 --iterations 10000 --nodes 10000 --methods random spatial_cbs --output results/cbs_total_matched_60
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort holdout_random_5s --seconds 5 --iterations 100 --nodes 256 --methods random --output results/spatial_cbs_random_matched_100_5s
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort holdout_spatial_cbs_incumbent_5s --seconds 5 --iterations 100 --nodes 256 --methods spatial_cbs --output results/spatial_cbs_incumbent_matched_100_5s
python code/audit_public_plantroom_dataset.py `
  data/external/mep_plant_room_pipe_routing `
  results/public_plantroom_dataset_audit.json
```

The holdout runner includes spatial PBS/CBS, conflict-graph neighborhoods, and an LNS2-style spatial destroy/repair adaptation. These use permanent occupancy and are not faithful temporal MAPF baselines. Spatial LNS2-style repair tied random completion at 17/100, with one paired gain and one loss (Holm-adjusted p=1.00); the conflict selector completed 13/100, equal to blocker repair and below random repair (17/100). An earlier CBS 5-s archive produced zero complete sets but did not retain the shared best-of-two incumbent; it is superseded by the corrected 100-scene common-incumbent comparison documented below. Run regression tests with `python -m unittest discover -s code -p 'test_*.py' -v`.

The optional-demand spatial CBS retains feasible paths when another demand is infeasible. An audit of the legacy 60-scene diagnostic found that a common initial route set was computed but not passed to the CBS routine. Its raw route outputs remain valid, but it is not a shared-initialization comparison; see the corrected manifest in `data/revision_20261023/spatial_cbs_total_matched_60.manifest.json`. The corrected 100-scene comparison passes the same best-of-two incumbent to both methods (CBS retains it as a fallback) and applies a 5-s cap, 100-iteration limit, and 256-node limit. Random repair completed 19/100 versus 9/100 for spatial CBS (10 random-only, no CBS-only; exact two-sided McNemar p=0.00195); mean routed counts were 7.10/9 and 6.71/9. Mean method runtimes were 2.95 s and 5.02 s, and all 200 outputs passed independent validation. CBS independently constructs its conflict-search root, so this is a common-incumbent/equal-cap diagnostic, not an identical search-start comparison or a result about mature temporal MAPF CBS. Raw observations and provenance are archived under `data/revision_20261023/spatial_cbs_incumbent_matched_100_5s/`.

The exact MILP diagnostic found 1/100 complete sets at a 1s cap and 24/100 at a 30s cap (16 optimal under its weighted objective, eight feasible incumbents returned at the time limit). The 30s run has a larger compute budget than the heuristic holdout and is descriptive only. The MILP minimizes a 10,000-unit penalty per unrouted commodity plus unit-edge and vertical-step proxy cost; bend penalties are omitted. This weighted objective does not guarantee strict lexicographic maximization of routed count, and optimality statements apply only to this proxy. Time-limit results do not prove infeasibility. Checksums and per-scene pairing are in `data/revision_20261023/exact_mcf/manifest.json`.

## What the added comparisons do and do not establish

- The high-stress comparison includes a bounded permanent-space priority-tree adaptation, LNS2-style destroy/repair under static occupancy, failed-route blocker and conflict-graph neighborhood controls, length-only and adaptive repair. The spatial LNS2-style adaptation ties random on complete-scene success and shows no significant paired advantage. A corrected 100-scene common-incumbent CBS diagnostic found 9 complete sets versus 19 for random repair under the same 5-s cap. This is a bounded permanent-space adaptation, not faithful temporal MAPF CBS, and its search root differs from the shared incumbent. On a fixed 10-scene exploratory subset with 30-second caps, spatial PBS completed 3/10 and random repair 2/10 (one PBS-only success, exact two-sided McNemar p=1.00); CBS completed 0/10, and one 120-second CBS run also found no complete set. These small diagnostics are not general performance claims and do not prove infeasibility. No secondary method significantly outperformed random repair after Holm adjustment.
- The exact MILP is a global optimization diagnostic for the simplified vertex-disjoint model, not a reproduction of PBS, CBS, or MAPF-LNS. Its finite failure penalty is weighted rather than strictly lexicographic; the 30s run is not compute-matched to the 1s heuristic holdout, and the objective excludes bend penalties.
- The adaptive/multi-operator holdout tied random completion at 17/100; matched-density tests completed no scenes at 27 or 60 systems. This is negative evidence about the present prototype, not evidence of general scalability.
- The separate 5-seed adaptive pilot found no completion advantage over random repair at 12- and 15-system scales (both methods completed 4/5 at each scale); at 15 systems, median runtime was 4.942 s for adaptive repair and 2.855 s for random repair. It is too small for inference and is not compute-matched (8 versus 5 iterations).
- A new paired 30-seed-per-scale comparison at 9/12/15 systems used the same scenes, initial routes, and eight iterations: random/adaptive completion was 3/30 vs 3/30, 13/30 vs 15/30, and 25/30 vs 26/30 (all exact paired p-values >=0.754). Adaptive median runtime was higher at every scale. Equal iterations are not equal wall-clock effort, and the design does not isolate scale from system count.
- Corrected spatial CBS now retains a conflict-free partial incumbent at cutoff. In a separate 10-scene 5-s-cap diagnostic it completed 0/10 and routed a mean 4.3/9 systems, versus 2/10 complete scenes and 7.0/9 mean routed for random repair. Nine CBS runs hit the cap; one root had an individually infeasible demand. This is small, not compute-matched, and not an infeasibility proof.
- The earlier IFC boundary audit covers 4,091 selected components, 4,054 extractable geometries, 8,460 placed ports and 4,050 explicit port relations. Those counts are not route evidence.
- The added RWTH Digital Hub audit covers four co-registered IFC4 files (architecture, heating, plumbing, ventilation), with 65 systems, 8,497 placed ports, 4,208 explicit port relations, native service dimensions, slope properties, and fitting geometry. A schema-level endpoint screen groups ports by owning IFC object and found zero connected components containing exactly two distinct recognized terminal objects with complementary source/sink directions. This does not replace engineering interpretation of IFC terminal semantics, but it confirms the public model does not directly yield a defensible point-to-point rerouting request. The 287-MEP/162-architecture AABB sample is only broad-phase screening. No accepted reroute targets or engineer-reviewed outcomes exist, and the routing solver has not been run on this model.
- The buildingSMART Medical-Dental Clinic audit adds two redacted IFC2X3 MEP files with 7,390 HVAC and 13,058 plumbing ports, represented segments, fittings, and native segment dimensions. Their graphs are already-connected multi-terminal branches, without `IfcSystem` assignments or project-approved independent rerouting requests; no route performance is claimed. Reproduce the screen after downloading the source files listed in `data/IFC_SOURCE.md`:

```powershell
python code/audit_ifc_route_readiness.py --ifc path/to/Clinic_HVAC.ifc path/to/Clinic_Plumbing.ifc --output data/revision_20261023/ifc_bench_dental_clinic_audit.json
```

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

## External field-validated plant-room dataset

The public [MEP Plant Room Pipe Routing Dataset](https://huggingface.co/datasets/IHNF/mep-plant-room-pipe-routing) is licensed CC BY 4.0 and accompanies a field-study paper (DOI: 10.1016/j.autcon.2026.107201). A local schema audit of its seven JSON cases found 48 pipe networks and 216 terminal points; all 48 networks are multi-terminal and the cases use an internal 2D plan coordinate system without a declared length unit in the case metadata. The layouts encode shared headers, transitions, and multiple risers. These are valuable engineering-design data, but they are not valid independent point-to-point requests for this paper's unit-capacity solver. Pairwise conversion would misclassify intended within-system trunk sharing as a collision. No solver performance is claimed. Reproduce the compatibility audit with:

```powershell
python code/audit_public_plantroom_dataset.py `
  data/external/mep_plant_room_pipe_routing `
  results/public_plantroom_dataset_audit.json
```

Legacy scripts and files outside `revision_20261023/` are retained for provenance. The current scale table was regenerated from the published `run_scaling_matched_density.py` generator after the earlier table's source was found missing; the withdrawn earlier file remains only in the local revision audit history. Replay commands write new outputs, and time-limited runtimes or outcomes can vary across machines. The archived tables remain the authoritative evidence for the current manuscript.

The matched adaptive comparison, corrected CBS incumbent logic, 10- and 60-scene CBS diagnostics, and plant-room dataset audit are included in the current source tree. No DOI is currently claimed; check the release page before citing the repository version.
