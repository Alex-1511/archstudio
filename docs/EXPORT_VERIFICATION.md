# Export Verification Checklist (manual: needs real software)
Generate files: `python3 tools/make_export_samples.py`. Record result, app + version, date, in the table at the bottom. **Until a row is filled in, the export stays `validated_in_cad_app: false`.**

## sample.dxf (expected: 10 m x 8 m plan, 230 mm walls, 1 door, 1 window, room "Living 80.00 sqm")
1. Opens in AutoCAD / BricsCAD / LibreCAD / DraftSight **without an error or repair prompt** (AutoCAD: no AUDIT errors, run `AUDIT`).
2. Layers present: A-WALL, A-DOOR, A-GLAZ, A-ROOM, A-ANNO.
3. `ZOOM EXTENTS`; `DIST` between outer wall corners is 10.230 x 8.230 (walls are drawn as outlines).
4. Text "Living 80.00 sqm" present on A-ANNO.
Known limits: R12 ASCII, LINE entities only (no polylines/hatches/dimensions/blocks), no BIM data.
## sample.obj (expected: 4 walls as separate objects, openings cut out)
1. Imports in Blender / MeshLab / Rhino without errors. 2. Door and window openings visible, sill piece below window.
3. Blender 3D-Print Toolbox "Check All" (or MeshLab): per-piece meshes are closed/manifold (overlapping corners are expected, no joins yet).
4. Face normals point outward (Blender: Overlay > Face Orientation is blue outside).
5. Bounding box: X -0.115..10.115, Y -0.115..8.115, Z 0..3.
| Format | App + version | Date | Result | Notes |
|---|---|---|---|---|
| DXF | | | | |
| OBJ | | | | |
