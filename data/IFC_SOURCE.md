# IFC source and checksum

The port-bearing IFC4 input used only for the geometry/port boundary audit is `Ifc4_Revit_MEP.ifc` from the Community Sample Test Files repository.

- Source collection: https://github.com/buildingsmart-community/Community-Sample-Test-Files
- File: `Ifc4_Revit_MEP.ifc`
- SHA-256: `829C08715D56256E04D04FA7BE40EC68928E0397631C3B846EFD72D003F96495`
- License stated by the source collection: CC BY 4.0. The collection notes these are community-created samples, not official buildingSMART examples.
- Access: download the file from the source collection; the 29 MB IFC is not mirrored in this repository. Verify the SHA-256 before using it.
- Audit-only caveat: the file does not provide accepted route targets, `IfcDistributionSystem` entities, or usable native service-dimension/maintenance-space properties. The audit is not routing validation.
- Corrected evidence archive: tag `v2.0.1`.
