# IFC source and checksum

The port-bearing IFC4 input used only for the geometry/port boundary audit is `Ifc4_Revit_MEP.ifc` from the Community Sample Test Files repository.

- Source collection: https://github.com/buildingsmart-community/Community-Sample-Test-Files
- File: `Ifc4_Revit_MEP.ifc`
- SHA-256: `829C08715D56256E04D04FA7BE40EC68928E0397631C3B846EFD72D003F96495`
- License stated by the source collection: CC BY 4.0. The collection notes these are community-created samples, not official buildingSMART examples.
- Access: download the file from the source collection; the 29 MB IFC is not mirrored in this repository. Verify the SHA-256 before using it.
- Audit-only caveat: this file does not provide accepted route targets, `IfcDistributionSystem` entities, or usable native service-dimension/maintenance-space properties. The audit is not routing validation.

## RWTH Digital Hub IFC-Bench

The public `digital_hub` project contains separate `arc.ifc`, `heating.ifc`, `plumbing.ifc`, and `ventilation.ifc` models. The four files identify the same project, site, and building, and share `EPSG:3857` map-conversion metadata. Model card and MIT license are archived under `data/revision_20261023/digital_hub/`.

| File | SHA-256 |
|---|---|
| `arc.ifc` | `19d7d02d53c2b88e86890ee236297b12bbb0f7748030cd32ff6a22762e9966bb` |
| `heating.ifc` | `a5603e8f6aa4cbf63aece92f92f503e9a578702d8fe96a6d4661490f1843710d` |
| `plumbing.ifc` | `0b1d6b0abd8d4cc3f5f798c7581bed2b39b40110ba6348d5470bbef646cfed79` |
| `ventilation.ifc` | `c0a1807875957c4154d45d14a3b5ed480dd3178a5bdc3262302a7eccf76d5cb1` |

- Dataset page: https://huggingface.co/datasets/sylvainHellin/ifc-bench/tree/main/projects/digital_hub
- Original project: https://github.com/RWTH-E3D/DigitalHub
- The IFC files are not mirrored in this repository. Download them from the dataset source and verify the hashes above.
- Audit scope: native systems, port connectivity, segment dimensions/slope fields, and bounded geometry sampling. It contains no accepted reroutes or coordinator-reviewed validation; do not cite it as routing-performance evidence.
- Corrected evidence archive: tag `v2.1.0`.

## buildingSMART Medical-Dental Clinic

The IFC2X3 clinic models were screened as a second candidate for a building-derived routing case. The source model card describes a real two-story clinic with identifying information redacted. The MEP and architectural files were obtained from the original buildingSMART Community Sample Test Files source; the model files are not mirrored in this repository.

| File | Size (bytes) | SHA-256 |
|---|---:|---|
| `Clinic_Architectural.ifc` | 13,003,205 | `2ac970ce065ecac4e0c9e5f453a257169e90d0067f419b7e33533a64ef837880` |
| `Clinic_HVAC.ifc` | 26,914,597 | `39c88a79f48fbe56da86afb0fb3ebd188f8930df3df7dbfbd9ecaa535aaeab9b` |
| `Clinic_Plumbing.ifc` | 55,834,520 | `e662a8d0273694b745a313fc18ee8d4916db03453caa8f9d00d4d80b62bb6e23` |

- Original source: [Medical-Dental Clinic, buildingSMART Community Sample-Test-Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files/tree/main/IFC%202.3.0.1%20%28IFC%202x3%29/Medical-Dental%20Clinic).
- License: CC BY 4.0, as stated in the source project and its IFC-Bench model card. Cite the original source when redistributing or presenting model-derived results.
- Reproduce the connectivity screen with `python code/audit_ifc_route_readiness.py --ifc Clinic_HVAC.ifc Clinic_Plumbing.ifc --output results/ifc_bench_dental_clinic_audit.json` after placing the two MEP files locally.
- Audit-only boundary: both MEP files contain thousands of ports, explicit connections, represented flow segments, fittings, and segment dimension properties, but the IFC2X3 export has no `IfcSystem` assignments. The owner-level connectivity graph is branched and supplies no project-approved independent point-to-point rerouting requests or accepted alternative routes. These data therefore support a readiness audit, not performance validation of the current unit-capacity point-to-point solver.
