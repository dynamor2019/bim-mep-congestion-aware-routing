# Congestion-Aware Routing for Multi-System MEP Coordination

Code and observation-level evidence for manuscript AUTCON-D-26-05125. This revision distinguishes synthetic spatial-routing evidence from temporal MAPF results and from construction-valid BIM routing.

## Corrected revision evidence

`data/revision_20261023/` contains the corrected 150-scene benchmark (750 method outputs), 990-observation sensitivity study, 100-scene/ten-method high-stress holdout (1,000 outputs), permanent-space CBS/PBS/LNS diagnostics, two matched binary multi-commodity-flow MILP diagnostics, a 2x2 system-count/obstacle-rate factorial (400 scenes; 800 method outputs), matched-density scale stress, and an expanded adaptive-repair comparison (270 paired scenes; 540 outputs across 9/12/15 systems). In the expanded equal-eight-iteration comparison, random/adaptive completion was 8/90 vs 6/90, 42/90 vs 47/90, and 72/90 vs 69/90; no paired difference was significant, and adaptive repair was slower at all three scales. The factorial cells use 100 seeds each; with 5/9 systems crossed with 4.5%/8.5% random obstacles, MSPP-random completion was 97%, 93%, 34%, and 9%, while guided repair completed 96%, 91%, 31%, and 12%. The spatial LNS2-style run is an explicit permanent-space adaptation, not a reproduction of temporal MAPF-LNS2. It completed 17/100 scenes, tied random repair, and had one paired gain and one paired loss (Holm-adjusted exact McNemar p=1.00). All heuristic and MILP route outputs passed independent validation.

`data/revision_20261024/hard_deadline_adaptive_90.csv` adds an independent 90-scene, 180-output comparison with a 1-s deadline checked inside A* node expansion. Random/adaptive completion was 3/30 vs 1/30, 10/30 vs 10/30, and 19/30 vs 21/30 at 9/12/15 systems; no paired difference was significant after Holm correction. Maximum observed runtime was 1.019 s. This is a strict-deadline synthetic comparison, not a BIM-scale result.

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

The validator checks row counts, per-scene/method balance, factorial cell pairing and checksums, validation flags, IFC audits, Digital Hub identity/semantic/sample/topology invariants, and the paired adaptive, CBS-incumbent, and plant-room compatibility archives. The expanded adaptive archive is regenerated from the existing and new seed blocks with `python code/run_matched_adaptive_scale.py --seeds 60 --start-seed 80000 --output results/matched_adaptive_scale_180_new.csv`; combine it with `data/revision_20261023/matched_adaptive_scale_90.csv` only when reproducing the 270-pair archive. The additional sample-house audit is reproduced with `python code/audit_public_ifc_model.py --ifc data/ifc_bench/samuel_macalister_sample_house/mep.ifc --source-url https://github.com/opensourceBIM/TestFiles --license "GNU GPL v3" --output data/revision_20261023/ifc_bench_house_audit.json`. The plotting script regenerates Figures 1–4, 6–8, and Supplementary Figure S1 from the archived observations. TIFF, PNG, and PDF outputs are generated.

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
python code/run_matched_adaptive_hard_deadline.py --seeds 30 --start-seed 140000 --budget-seconds 1 --output results/replay_hard_deadline_adaptive_90.csv
python code/summarize_matched_adaptive_scale.py `
  data/revision_20261023/matched_adaptive_scale_90.csv `
  results/matched_adaptive_scale_summary.json
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --cohort cbs_incumbent_5s --seconds 5 --iterations 100 --nodes 10000 --methods random spatial_cbs --output results/cbs_incumbent_5s
python code/run_revision_benchmark.py --seeds 10 --start-seed 100000 --cohort cbs_optional_matched_5s --seconds 5 --iterations 10000 --nodes 10000 --methods random spatial_cbs --output results/cbs_optional_matched_5s
python code/run_revision_benchmark.py --seeds 60 --start-seed 101000 --cohort cbs_total_matched_5s --seconds 4.8 --iterations 10000 --nodes 10000 --methods random spatial_cbs --output results/cbs_total_matched_60
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort holdout_random_5s --seconds 5 --iterations 100 --nodes 256 --methods random --output results/spatial_cbs_random_matched_100_5s
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort holdout_spatial_cbs_incumbent_5s --seconds 5 --iterations 100 --nodes 256 --methods spatial_cbs --output results/spatial_cbs_incumbent_matched_100_5s
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort pbs_matched_5s_100 --seconds 5 --iterations 100 --nodes 256 --methods random pbs_static --output results/pbs_matched_5s_100
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
- The expanded paired adaptive comparison covers 90 seeds per scale at 9/12/15 systems and uses identical scenes, initial routes, and eight iterations: random/adaptive completion was 8/90 vs 6/90, 42/90 vs 47/90, and 72/90 vs 69/90 (all exact paired p-values >=0.332). Adaptive median runtime was higher at every scale. Equal iterations are not equal wall-clock effort, and the design does not isolate scale from system count.
- A separate independent 90-scene adaptive cohort checks the deadline inside A* rather than only between iterations. It produced 3/30 vs 1/30, 10/30 vs 10/30, and 19/30 vs 21/30 random/adaptive completions at 9/12/15 systems; all Holm-adjusted exact McNemar tests were non-significant. Maximum observed runtime was 1.019 s, including small interpreter/return overhead. This does not establish adaptive benefit or general scalability.
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

The additional 100-scene, 5-s-per-method PBS-adaptation comparison is archived under `data/revision_20261023/pbs_matched_5s_100/`. It found 20/100 complete scenes for spatial PBS versus 19/100 for random repair, with one PBS-only and no random-only completion (exact two-sided McNemar p=1.00); mean routed demands were 7.05/9 and 7.10/9. All 200 route sets passed independent validation. This is a bounded permanent-occupancy priority-tree adaptation, not a faithful temporal MAPF PBS implementation, and does not establish a performance advantage.

## IFC4X3 PCERT readiness audit

The CC BY 4.0 buildingSMART IFC4X3_ADD2 PCERT samples were screened with `code/audit_ifc_route_readiness.py`; the archived result and model SHA-256 values are in `data/revision_20261023/ifc4x3_pcert_audit.json`. HVAC contains one system, one represented duct segment, and two terminals; plumbing contains one system and 24 represented pipe segments. Neither file provides explicit ports, port connections, fittings, or native segment-dimension property sets. Reproduce the audit after downloading the two IFC files from the [buildingSMART Community Sample-Test-Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) repository:

```powershell
python code/audit_ifc_route_readiness.py --ifc path/to/Building-Hvac.ifc path/to/Infra-Plumbing.ifc --output data/revision_20261023/ifc4x3_pcert_audit.json
```

This is a data-readiness screen only. Tessellated geometry does not supply a connected graph or approved rerouting request, so it is not routing-performance or construction-validity evidence.

## West Riverside Hospital IFC schema audit

The IFC-Bench release provides the West Riverside Hospital mechanical model in IFC2X3 and IFC4 under CC BY 3.0. Our matched audit found 39,532 owned ports, 19,766 explicit port connections, 8,732 flow segments, and 8,230 fittings in both files. IFC2X3 contains 1,064 typed flow terminals (923 with ports), whereas its IFC4 counterpart contains none; both have the same 181-component owner graph and no exactly-two-terminal component with complementary `SOURCE`/`SINK` directions. Swept profiles expose circle and rectangle parameters, but outlying values and missing installation-clearance semantics prevent treating them as validated service envelopes. These are installed-network and schema-readiness observations, not approved reroute tasks or route-performance evidence. The raw IFCs are not redistributed here; download them from IFC-Bench. The machine-readable counts, source hashes, and attribution are in `results/ifc_bench_west_riverside_schema_comparison.json`.

Reproduce the audit after downloading the two mechanical IFC files from the [IFC-Bench dataset](https://huggingface.co/datasets/sylvainHellin/ifc-bench):

```powershell
python code/audit_west_riverside_ifc.py `
  --ifc path/to/mech_ifc2x3.ifc path/to/mech_ifc4.ifc `
  --output results/ifc_bench_west_riverside_schema_comparison.json
```

The model attribution is Solihin, W., *West Riverside Hospital IFC Models*, OpenIFC Model Repository, University of Auckland, CC BY 3.0. The audit does not reconstruct project-approved endpoints or accepted alternatives.

## Wall-clock-capped adaptive repair comparison

`data/revision_20261023/matched_adaptive_wallclock_90.csv` contains 90 paired synthetic scenes (30 at each of 9, 12, and 15 systems; 180 independently validated outputs). Both repair methods start from the same scene and incumbent and receive a 1-s repair-time cap. The cap is checked only between complete iterations; observed runtimes may exceed it by one iteration, so this is not exact CPU-time matching. Random versus adaptive completion was 4/30 versus 3/30, 14/30 versus 7/30, and 20/30 versus 15/30. The 12-system stratum favored random repair (7 random-only, zero adaptive-only; exact McNemar p=0.0156, Holm-adjusted across three strata p=0.0469); the other strata were inconclusive. This single exploratory cohort does not establish a general random-repair advantage, especially because one-iteration overshoot varies with runtime and differs by operator. The 270-scene equal-iteration cohort remains separately archived; its result is not pooled with this budget-capped comparison.

Reproduce the budget-capped experiment and summarize the archived raw results with:

```powershell
python code/run_matched_adaptive_wallclock.py --seeds 30 --start-seed 110000 --budget-seconds 1.0 --output results/matched_adaptive_wallclock_90.csv
python code/summarize_adaptive_wallclock.py results/matched_adaptive_wallclock_90.csv results/matched_adaptive_wallclock_90_summary.json --run-source code/run_matched_adaptive_wallclock.py --implementation-source code/run_routing_experiments.py code/run_advanced_validation.py
python code/validate_revision_evidence.py --data data/revision_20261023
```

## Independent adaptive-repair cohort

`data/revision_20261024/adaptive_wallclock_independent_300.csv` contains 300 new paired scenes, using seeds 120000-120099 at each of 9, 12, and 15 systems (600 independently validated outputs). It is an independent seed cohort, not another repeat of the earlier 90-scene sample. Both methods use the same initial routes and a nominal 1-s repair cap; because the cap is checked between complete iterations, observed runtimes can exceed 1 s. Random versus adaptive completion was 21/100 versus 12/100 at 9 systems (11 random-only, 2 adaptive-only; exact McNemar `p=0.0225`, Holm-adjusted `p=0.0225`), 45/100 versus 31/100 at 12 systems (17 versus 3 discordant; `p=0.00258`, Holm-adjusted `p=0.00586`), and 73/100 versus 63/100 at 15 systems (10 versus 0 discordant; `p=0.00195`, Holm-adjusted `p=0.00586`). The adaptive portfolio had a longer median observed runtime at every scale (1.031 vs 1.014 s; 1.153 vs 1.050 s; 1.284 vs 1.142 s). Within this generator and nominal budget, this independent cohort favors random repair; it does not establish universal superiority because the iteration-boundary timer can overshoot and scale is confounded with grid size and system count.

Reproduce the new cohort and its Holm-adjusted summary with:

```powershell
python code/run_matched_adaptive_wallclock.py --seeds 100 --start-seed 120000 --budget-seconds 1.0 --output data/revision_20261024/adaptive_wallclock_independent_300.csv
python code/summarize_adaptive_wallclock.py data/revision_20261024/adaptive_wallclock_independent_300.csv data/revision_20261024/adaptive_wallclock_independent_300_summary.json --run-source code/run_matched_adaptive_wallclock.py --implementation-source code/run_routing_experiments.py code/run_advanced_validation.py
python code/validate_revision_evidence.py --data data/revision_20261023
```

## Adaptive-repair factor-separation cohort

`data/revision_20261024/adaptive_factor_separation_150.csv` contains 150 paired scenes (300 independently validated outputs) in five cells. Three cells hold demand count at nine while using 16x12x3, 24x18x4, and 32x24x5 grids; two additional cells hold the 32x24x5 geometry fixed and increase the nested demand set from 9 to 12 and 15 systems. Environment and terminal-prefix hashes verify the fixed-geometry and nested-demand design. Random versus adaptive completion was 5/30 vs 3/30, 26/30 vs 22/30, and 27/30 vs 27/30 in the fixed-nine-system cells, and 27/30 vs 26/30 vs 21/30 for random repair and 27/30 vs 25/30 vs 20/30 for adaptive repair in the fixed-grid 9/12/15-system cells. Each within-cell exact McNemar test was inconclusive after Holm correction (all adjusted p=1.00). The nominal 1-s cap was checked between full iterations; all measured runs exceeded 1 s and the maximum was 1.86 s. Grid-size cells also differ in generator topology, so they are not a pure causal estimate of geometric scale. This synthetic factor-separation test does not establish BIM or general scalability.

Reproduce and validate it with:

```powershell
python code/run_adaptive_factor_separation.py --seeds 30 --start-seed 130000 --budget-seconds 1.0 --output data/revision_20261024/adaptive_factor_separation_150.csv
python code/validate_revision_evidence.py --data data/revision_20261023
```

## Shared-incumbent permanent-space CBS diagnostic

`data/revision_20261023/spatial_cbs_shared_incumbent_100_5s/` contains a new 100-scene paired comparison. The CBS root contains the same best-of-two partial incumbent passed to random repair; it adds independently shortest paths for unserved demands and branches on permanent-vertex conflicts. With the same 5-s cap, 100-iteration limit, 256-node limit, scene seeds, and independent validator, random repair completed 19/100 scenes and routed 7.10/9 demands on average; spatial CBS completed 9/100 and routed 6.71/9. Ten discordant pairs favored random repair and none favored CBS (exact two-sided McNemar $p=0.001953$). Mean observed runtimes were 3.00 s and 4.56 s. All 200 route sets passed validation. This is an equal-scene, common-incumbent permanent-space diagnostic, not a faithful temporal MAPF CBS implementation and not evidence about unrestricted CBS.

Reproduce and summarize it with:

```powershell
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort shared_incumbent_cbs_100_5s --seconds 5 --iterations 100 --nodes 256 --methods random spatial_cbs --output results/shared_incumbent_cbs_100_5s
python code/summarize_revision_benchmark.py results/shared_incumbent_cbs_100_5s/raw.csv results/shared_incumbent_cbs_100_5s/summary.json
```

## Matched four-way permanent-space baseline comparison

`data/revision_20261023/matched_permanent_baselines_100_5s/` combines random repair, spatial PBS, spatial CBS, and spatial MAPF-LNS2-style repair on the same 100 high-stress scenes, the same best-of-two initial objectives, and a 5-s/100-iteration/256-node budget. Completion was 19/100, 20/100, 9/100, and 20/100, respectively. Relative to random repair, exact McNemar tests were inconclusive for PBS (one gain, no loss; `p=1.00`) and LNS2-style repair (two gains, one loss; `p=1.00`); CBS had ten losses and no gains (`p=0.00195`, Holm-adjusted `p=0.00586`). Mean routed demands were 7.10, 7.05, 6.71, and 6.82 of nine, and mean observed runtimes were 3.00, 3.66, 4.56, and 4.48 s. All 400 outputs passed independent route validation. These are permanent-occupancy adaptations sharing the same low-level planner, not faithful temporal MAPF implementations or independent solver implementations.

Reproduce the LNS2-style cohort and rebuild the merged archive from the archived CBS/PBS runs with:

```powershell
python code/run_revision_benchmark.py --seeds 100 --start-seed 100000 --cohort spatial_mapf_lns2_matched_5s --seconds 5 --iterations 100 --nodes 256 --methods spatial_mapf_lns2 --output results/spatial_mapf_lns2_matched_5s_100
python code/merge_matched_baselines.py --cbs data/revision_20261023/spatial_cbs_shared_incumbent_100_5s --pbs data/revision_20261023/pbs_matched_5s_100 --lns results/spatial_mapf_lns2_matched_5s_100 --output results/matched_permanent_baselines_100_5s
python code/summarize_revision_benchmark.py results/matched_permanent_baselines_100_5s/raw.csv results/matched_permanent_baselines_100_5s/summary.json
```

## Repair convergence figure

`code/plot_repair_convergence.py` validates the matched traces in `data/revision_20261023/high_stress_holdout_1000.csv` and rebuilds Figure 6 as iteration- and elapsed-time complete-scene success curves with pointwise paired-scene bootstrap intervals. Both policies share the same best-of-two initial routes. The nominal 1-s cap is checked between A* calls; maximum observed runtime was 1.09 s. The single-cohort result (17/100 random vs 11/100 guided; exact McNemar `p=0.0313`, Holm-adjusted `p=0.25` across nine selectors) is exploratory, not confirmatory.

```powershell
python code/plot_repair_convergence.py --data data/revision_20261023/high_stress_holdout_1000.csv --output figures/revision_20261024_convergence
```

## Equal-budget permanent-space priority-search cohort

`data/priority_graph_budget_matched_20261024/` archives a rerun of the 100-scene paired comparison (seeds 320000–320099; 200 independently validated outputs) against the current repository code. MSPP-random restarts completed 22/100 scenes and bounded permanent-space priority search 20/100 (four candidate-only, six baseline-only; exact two-sided McNemar `p=0.7539`). Both used a nominal 1.2-s per-scene cap; A* checks the deadline cooperatively, so maximum observed runtimes were 1.233 s and 1.201 s. This exploratory result is inconclusive and is not a canonical temporal MAPF-PBS comparison. The earlier local-runner archive remains separate at `data/priority_graph_budget_matched/`.

Reproduce and check the archived checksums with:

```powershell
python code/run_priority_graph_pilot.py --scenes 100 --first-seed 320000 --time-budget-s 1.2 --output results/priority_graph_budget_matched_replay
```

The runner writes paired raw observations and a JSON summary. `data/priority_graph_budget_matched_20261024/SHA256SUMS.txt` records hashes for the archived raw data, summary, and provenance note.
