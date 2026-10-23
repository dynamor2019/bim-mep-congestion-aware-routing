# Congestion-Aware Routing for Multi-System MEP Coordination

Reproducibility bundle for manuscript AUTCON-D-26-05125.

## Contents

- `code/`: deterministic experiment scripts.
- `data/`: observation-level results, IFC-derived graph artifacts, geometry-envelope diagnostics, and source metadata for the public port-bearing IFC input.
- `requirements.txt`: tested Python package versions.
- `CITATION.cff` and `zenodo.json`: metadata for GitHub release and Zenodo DOI minting.

## Reproduce

From the repository root, create a Python 3.11 environment and install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the primary benchmark and sensitivity study:

```powershell
python code/run_routing_experiments.py --seeds 50 --output results/main_150
python code/run_sensitivity_analysis.py --seeds 30 --output results/sensitivity_990
```

Run the additional revision checks:

```powershell
python code/run_envelope_stress.py code/run_routing_experiments.py results/envelope_stress/envelope_stress_raw.csv --seeds 30
python code/run_factorial_density.py code/run_routing_experiments.py results/factorial_density/factorial_density_raw.csv --seeds 20
python code/build_port_derived_ifc_graph.py data/Ifc4_Revit_MEP.ifc results/ifc_public_mep/port_derived_graph.json --pairs 20
python code/run_ifc_graph_adapter.py results/ifc_public_mep/port_derived_graph.json --seeds 10 --output results/ifc_public_mep/adapter_runs
python code/run_ifc_geometry_envelope.py data/Ifc4_Revit_MEP.ifc data/port_derived_graph.json results/ifc_public_mep/geometry_envelope --seeds 10 --max-elements-per-type 100
```

The synthetic benchmark is unit-resolution evidence. The envelope and IFC runs are boundary checks; the geometry check uses a deterministic 100-element-per-type sample and explicit isotropic clearances of 0, 0.05, 0.15, and 0.30 m. They do not claim construction-valid pipe/duct sizing, maintenance space, clearance semantics, or IFC write-back.

## Version and DOI

The local source is tagged `v1.0.0`. Create a public GitHub repository, push this tag, then connect the repository to Zenodo and archive the `v1.0.0` release to mint the DOI recorded by Zenodo.
