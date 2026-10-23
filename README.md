# Congestion-Aware Routing for Multi-System MEP Coordination

Code and observation-level evidence for manuscript AUTCON-D-26-05125. This revision distinguishes synthetic spatial-routing evidence from temporal MAPF results and from construction-valid BIM routing.

## Corrected revision evidence

`data/revision_20261023/` contains the corrected 150-scene benchmark (750 method outputs), 990-observation sensitivity study, 100-scene/eight-method high-stress holdout (800 outputs), nested factor study (800 method-runs), matched-density scale stress (180 outputs), and full native IFC geometry/port audit. The original 150-scene paths were independently checked; all 750 outputs passed route validation and deterministic replay. Archived holdout and scale outputs also carry per-row validation flags.

Recheck the archived tables and regenerate figures:

```powershell
python -m pip install -r requirements.txt
python code/validate_revision_evidence.py --data data/revision_20261023
python code/plot_corrected_revision.py `
  --main data/revision_20261023/main_150_raw.csv `
  --sensitivity data/revision_20261023/sensitivity_990_raw.csv `
  --holdout data/revision_20261023/high_stress_holdout_800.csv `
  --factorial data/revision_20261023/factorial_nested_800.csv `
  --scaling data/revision_20261023/scale_matched_density_180.csv `
  --ifc-audit data/revision_20261023/ifc_full_geometry_audit.json `
  --output figures/revision_20261023
```

The validator checks row counts, per-scene/method balance, validation flags, both IFC audits, and Digital Hub identity/semantic/sample invariants. The plotting script regenerates Figures 1–4, 6–8, and Supplementary Figure S1 from the archived observations. TIFF, PNG, and PDF outputs are generated.

## What the added comparisons do and do not establish

- The high-stress comparison includes a bounded permanent-space priority-tree adaptation, conflict-blocker control, length-only and adaptive repair. It is not a faithful implementation of temporal MAPF-PBS or MAPF-LNS. No secondary method significantly outperformed random repair after Holm adjustment.
- The adaptive/multi-operator holdout tied random completion at 17/100; matched-density tests completed no scenes at 27 or 60 systems. This is negative evidence about the present prototype, not evidence of general scalability.
- The earlier IFC boundary audit covers 4,091 selected components, 4,054 extractable geometries, 8,460 placed ports and 4,050 explicit port relations. Those counts are not route evidence.
- The added RWTH Digital Hub audit covers four co-registered IFC4 files (architecture, heating, plumbing, ventilation), with 65 systems, 8,497 placed ports, 4,208 explicit port relations, native service dimensions, slope properties, and fitting geometry. The 287-MEP/162-architecture AABB sample is only broad-phase screening. No accepted reroute targets or engineer-reviewed outcomes exist, and the routing solver has not been run on this model.

Reproduce the Digital Hub audit after downloading the four IFC files listed in `data/IFC_SOURCE.md` into a local folder:

```powershell
python code/audit_digital_hub_ifc.py path/to/digital_hub_ifc data/revision_20261023/digital_hub --max-per-type 25
```

The script records source SHA-256 hashes, checks IFC model identity and coordinate metadata, extracts native port/system graphs and segment dimensions, and generates a deterministic geometry sample. AABB candidates are not exact clashes or route outcomes.

Legacy scripts and files outside `revision_20261023/` are retained for provenance. Some generate earlier exploratory protocols and do not reproduce the corrected holdout/factor/scale tables; do not cite them as the source of those corrected observations. The exact corrected observation tables and summaries are archived here for audit.

The old `v1.0.0` tag predates these corrections. This corrected archive is versioned as `v2.1.0`. No DOI is currently claimed.
