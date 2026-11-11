"""Dependency-free 3D foundation: walls -> closed, consistently oriented triangle meshes.

Each wall becomes axis-aligned-to-the-wall boxes: solid segments between openings, plus a sill piece
below windows and a head piece above every opening. Volumes therefore match Wall.volume() exactly.
This is MESH geometry for viewport/quantity checks. It is NOT a B-rep/solid-modelling kernel: no
booleans, no wall joins/corner cleanup (overlapping corner volume is counted per wall), no curved
walls. That work is planned on top of Open CASCADE behind the same function signatures."""
from __future__ import annotations
from .bim import Wall, Level
from .geometry import distance

Vec = tuple[float, float, float]
Tri = tuple[int, int, int]


def mesh_volume(verts: list[Vec], tris: list[Tri]) -> float:
    """Signed volume via the divergence theorem (positive when faces are outward-oriented)."""
    v = 0.0
    for a, b, c in tris:
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = verts[a], verts[b], verts[c]
        v += x1 * (y2 * z3 - z2 * y3) - y1 * (x2 * z3 - z2 * x3) + z1 * (x2 * y3 - y2 * x3)
    return v / 6.0


def is_closed_oriented(tris: list[Tri]) -> bool:
    """Every directed edge occurs exactly once and its reverse occurs exactly once (closed 2-manifold)."""
    edges: dict[tuple[int, int], int] = {}
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            edges[e] = edges.get(e, 0) + 1
    return all(n == 1 and edges.get((e[1], e[0])) == 1 for e, n in edges.items())


def _box(start, end, a, b, thickness, z0, z1) -> tuple[list[Vec], list[Tri]]:
    L = distance(start, end)
    ux, uy = (end[0] - start[0]) / L, (end[1] - start[1]) / L
    nx, ny, h = -uy, ux, thickness / 2.0
    verts = [(start[0] + ux * da + nx * s, start[1] + uy * da + ny * s, z)
             for da in (a, b) for s in (-h, h) for z in (z0, z1)]
    v = lambda i, j, k: i * 4 + j * 2 + k
    quads = [(v(0, 0, 0), v(0, 1, 0), v(0, 1, 1), v(0, 0, 1)), (v(1, 0, 0), v(1, 0, 1), v(1, 1, 1), v(1, 1, 0)),
             (v(0, 0, 0), v(0, 0, 1), v(1, 0, 1), v(1, 0, 0)), (v(0, 1, 0), v(1, 1, 0), v(1, 1, 1), v(0, 1, 1)),
             (v(0, 0, 0), v(1, 0, 0), v(1, 1, 0), v(0, 1, 0)), (v(0, 0, 1), v(0, 1, 1), v(1, 1, 1), v(1, 0, 1))]
    tris = [t for q in quads for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
    if mesh_volume(verts, tris) < 0:
        tris = [(a_, c_, b_) for a_, b_, c_ in tris]
    return verts, tris


def wall_pieces(wall: Wall, level: Level) -> list[dict]:
    """Wall mesh pieces tagged by role: 'solid' (full height), 'sill' / 'head' (below / above an opening)."""
    z0, H, L, t = level.elevation, wall.height, wall.length, wall.thickness
    out, cursor, tiny = [], 0.0, 1e-12

    def add(kind, oid, a, b, za, zb):
        v, tr = _box(wall.start, wall.end, a, b, t, za, zb)
        out.append({"kind": kind, "opening_id": oid, "vertices": v, "triangles": tr})

    for o in sorted(wall.openings, key=lambda o: o.offset):
        if o.offset - cursor > tiny:
            add("solid", None, cursor, o.offset, z0, z0 + H)
        if o.sill > tiny:
            add("sill", o.id, o.offset, o.offset + o.width, z0, z0 + o.sill)
        if H - (o.sill + o.height) > tiny:
            add("head", o.id, o.offset, o.offset + o.width, z0 + o.sill + o.height, z0 + H)
        cursor = o.offset + o.width
    if L - cursor > tiny:
        add("solid", None, cursor, L, z0, z0 + H)
    return out


def opening_proxy(wall: Wall, level: Level, o) -> tuple[list[Vec], list[Tri]]:
    """The void an opening occupies, as a box (for selection/highlighting; not part of the wall solid)."""
    z0 = level.elevation + o.sill
    return _box(wall.start, wall.end, o.offset, o.offset + o.width, wall.thickness, z0, z0 + o.height)


def wall_solids(wall: Wall, level: Level) -> list[tuple[list[Vec], list[Tri]]]:
    return [(p["vertices"], p["triangles"]) for p in wall_pieces(wall, level)]
