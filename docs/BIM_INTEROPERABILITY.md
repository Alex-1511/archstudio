# BIM Interoperability
| Format | Status | Fidelity (documented) |
|---|---|---|
| Native `.archproj` JSON | **Implemented, tested** | Full: parameters, openings, metadata |
| DXF (R12 ASCII) | **Implemented**, structure tested | 2D layered plan only; **not yet opened in a real CAD app** |
| OBJ | **Implemented**, structure + volume tested | **Mesh-only**, no metadata/materials |
| IFC | Planned (IfcOpenShell) | BIM objects with metadata (target) |
| DWG | Planned via licensed converter | DXF is the honest interchange meanwhile |
| RVT | Planned, C# Revit add-in | Needs Revit + Windows |
| 3DM / SKP / glTF / OBJ / STEP | Planned | 3DM geometry; glTF/OBJ **mesh-only**; STEP solids |
Verification status: both implemented exporters are re-parsed by independent test code, but **neither has been opened in real software yet**; see `EXPORT_VERIFICATION.md`.
Rule: mesh-only output is never described as an editable BIM project. `export_capabilities()` is the source of truth for the UI, so no button can promise an unimplemented export.
