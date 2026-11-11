"""Exporters with documented fidelity. Only formats that are actually implemented are marked so."""
from __future__ import annotations
from .bim import Project
from .geometry import wall_footprint, point_along
from .solids import wall_solids

CAPABILITIES = {
    "dxf": {"status": "implemented", "fidelity": "2D layered geometry (R12 ASCII). No BIM metadata, no 3D.",
            "validated_in_cad_app": False},
    "obj": {"status": "implemented", "fidelity": "MESH-ONLY triangles per wall piece (openings cut). Not editable BIM; no materials/metadata.",
            "validated_in_cad_app": False},
    "ifc": {"status": "not_implemented", "fidelity": "planned: BIM objects with metadata via IfcOpenShell"},
    "dwg": {"status": "not_implemented", "fidelity": "planned: via licensed converter; DXF is the interchange today"},
    "rvt": {"status": "not_implemented", "fidelity": "planned: Revit add-in (C#), needs Revit installed"},
    "3dm": {"status": "not_implemented", "fidelity": "planned: RhinoCommon / rhino3dm"},
    "gltf": {"status": "not_implemented", "fidelity": "planned: mesh-only"},
}


def export_capabilities() -> dict:
    return {k: dict(v) for k, v in CAPABILITIES.items()}


def _pairs(*items) -> str:
    return "".join(f"{c}\n{v}\n" for c, v in items)


def export_dxf(project: Project, level_id: str) -> str:
    """Plan view of one level: walls (outline), openings (centreline span), rooms (outline + label)."""
    if level_id not in project.levels:
        raise ValueError(f"unknown level {level_id}")
    layers = ["A-WALL", "A-DOOR", "A-GLAZ", "A-ROOM", "A-ANNO"]
    out = [_pairs((0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, "AC1009"), (0, "ENDSEC"))]
    out.append(_pairs((0, "SECTION"), (2, "TABLES"),
                      (0, "TABLE"), (2, "LTYPE"), (70, 1),
                      (0, "LTYPE"), (2, "CONTINUOUS"), (70, 0), (3, "Solid line"), (72, 65), (73, 0), (40, 0.0),
                      (0, "ENDTAB"),
                      (0, "TABLE"), (2, "LAYER"), (70, len(layers))))
    for name in layers:
        out.append(_pairs((0, "LAYER"), (2, name), (70, 0), (62, 7), (6, "CONTINUOUS")))
    out.append(_pairs((0, "ENDTAB"), (0, "ENDSEC"), (0, "SECTION"), (2, "ENTITIES")))

    def line(layer, a, b):
        return _pairs((0, "LINE"), (8, layer), (10, a[0]), (20, a[1]), (30, 0.0), (11, b[0]), (21, b[1]), (31, 0.0))

    def closed(layer, pts):
        return "".join(line(layer, pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))

    for w in project.walls.values():
        if w.level_id != level_id:
            continue
        out.append(closed("A-WALL", wall_footprint(w.start, w.end, w.thickness)))
        for o in w.openings:
            a = point_along(w.start, w.end, o.offset)
            b = point_along(w.start, w.end, o.offset + o.width)
            out.append(line("A-DOOR" if o.kind == "door" else "A-GLAZ", a, b))
    for r in project.rooms.values():
        if r.level_id != level_id:
            continue
        out.append(closed("A-ROOM", r.boundary))
        cx = sum(p[0] for p in r.boundary) / len(r.boundary)
        cy = sum(p[1] for p in r.boundary) / len(r.boundary)
        out.append(_pairs((0, "TEXT"), (8, "A-ANNO"), (10, cx), (20, cy), (30, 0.0), (40, 0.25),
                          (1, f"{r.name} {r.area:.2f} sq{project.units}")))
    out.append(_pairs((0, "ENDSEC"), (0, "EOF")))
    return "".join(out)


def export_obj(project: Project, level_id: str) -> str:
    """Mesh-only Wavefront OBJ of one level's walls. Each wall is an object; metadata is NOT preserved."""
    if level_id not in project.levels:
        raise ValueError(f"unknown level {level_id}")
    lv = project.levels[level_id]
    out, base = [f"# ArchStudio mesh-only export, level {lv.name}, units {project.units}"], 0
    for w in project.walls.values():
        if w.level_id != level_id:
            continue
        out.append(f"o {w.id}")
        for verts, tris in wall_solids(w, lv):
            out += [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in verts]
            out += [f"f {a + base + 1} {b + base + 1} {c + base + 1}" for a, b, c in tris]
            base += len(verts)
    return "\n".join(out) + "\n"
