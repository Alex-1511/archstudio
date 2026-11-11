"""Intelligent architectural objects. A wall is not a mesh: it carries height, thickness,
material, level, openings and metadata, and these survive save/load/export.

Validation architecture (single source of truth): the `_check_*` invariants below are applied
  1. when objects are created (add_*),
  2. when a project is imported (from_dict -> validate),
  3. after every History command (so direct attribute mutation inside a command is also caught).
Numbers must be real, finite and non-boolean; strings are never coerced to numbers."""
from __future__ import annotations
import json, math, uuid
from dataclasses import dataclass, field
from .geometry import Point, distance, polygon_area, validate_simple_polygon

OPENING_KINDS = ("door", "window")
UNITS = ("m", "cm", "mm", "ft", "in")
TOL = 1e-9
MAX_MAGNITUDE = 1e9  # finite is not enough: 1e308 overflows area/volume to inf. 1e9 units keeps products < 1e27.


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------- scalar guards
def _real(v, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(v).__name__}")
    if not math.isfinite(v):
        raise ValueError(f"{name} must be finite")
    if abs(v) > MAX_MAGNITUDE:
        raise ValueError(f"{name} magnitude exceeds {MAX_MAGNITUDE:g}")
    return float(v)


def _positive(v, name: str) -> float:
    v = _real(v, name)
    if v <= 0:
        raise ValueError(f"{name} must be positive")
    return v


def _nonneg(v, name: str) -> float:
    v = _real(v, name)
    if v < 0:
        raise ValueError(f"{name} must not be negative")
    return v


def _text(v, name: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return v


def _pt(p, name: str = "point") -> Point:
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise ValueError(f"{name} must be an [x, y] pair")
    return (_real(p[0], f"{name}.x"), _real(p[1], f"{name}.y"))


def _json_safe(props, name: str) -> dict:
    if not isinstance(props, dict):
        raise ValueError(f"{name} must be an object")
    try:
        json.dumps(props, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be JSON-serialisable with finite numbers: {e}") from e
    return props


@dataclass
class Opening:
    id: str
    kind: str
    offset: float  # distance from wall start to opening start, along centreline
    width: float
    height: float
    sill: float = 0.0


@dataclass
class Wall:
    id: str
    level_id: str
    start: Point
    end: Point
    thickness: float
    height: float
    material: str = "unspecified"
    openings: list[Opening] = field(default_factory=list)
    properties: dict = field(default_factory=dict)

    @property
    def length(self) -> float:
        return distance(self.start, self.end)

    def gross_area(self) -> float:
        return self.length * self.height

    def net_area(self) -> float:
        return self.gross_area() - sum(o.width * o.height for o in self.openings)

    def volume(self) -> float:
        return self.net_area() * self.thickness


@dataclass
class Level:
    id: str
    name: str
    elevation: float
    height: float


@dataclass
class Room:
    id: str
    name: str
    level_id: str
    boundary: list[Point]
    target_area: float | None = None

    @property
    def area(self) -> float:
        return polygon_area(self.boundary)


_KEYS = {
    "project": {"name", "units", "levels", "walls", "rooms"},
    "level": {"id", "name", "elevation", "height"},
    "wall": {"id", "level_id", "start", "end", "thickness", "height", "material", "properties", "openings"},
    "opening": {"id", "kind", "offset", "width", "height", "sill"},
    "room": {"id", "name", "level_id", "boundary", "target_area"},
}


def _obj(d, what: str) -> dict:
    if not isinstance(d, dict) or set(d) != _KEYS[what]:
        got = sorted(d) if isinstance(d, dict) else type(d).__name__
        raise ValueError(f"{what}: expected exactly keys {sorted(_KEYS[what])}, got {got}")
    return d


def _list(v, name: str) -> list:
    if not isinstance(v, list):
        raise ValueError(f"{name} must be a list")
    return v


class Project:
    SCHEMA = 1

    def __init__(self, name: str, units: str = "m"):
        self.name = name
        self.units = units
        self.levels: dict[str, Level] = {}
        self.walls: dict[str, Wall] = {}
        self.rooms: dict[str, Room] = {}
        self._graveyard: dict[tuple[str, str], object] = {}  # removed objects, revived on redo

    # ================================================================ invariants
    @staticmethod
    def _check_level(l: Level) -> None:
        _text(l.id, "level.id"); _text(l.name, "level.name")
        _real(l.elevation, "level.elevation"); _positive(l.height, "level.height")

    @staticmethod
    def _check_opening(w: Wall, o: Opening) -> None:
        _text(o.id, "opening.id")
        if o.kind not in OPENING_KINDS:
            raise ValueError(f"opening kind must be one of {OPENING_KINDS}")
        _nonneg(o.offset, "opening.offset"); _positive(o.width, "opening.width")
        _positive(o.height, "opening.height"); _nonneg(o.sill, "opening.sill")
        if o.offset + o.width > w.length + TOL:
            raise ValueError(f"opening {o.id} exceeds wall length")
        if o.sill + o.height > w.height + TOL:
            raise ValueError(f"opening {o.id} exceeds wall height")

    def _check_wall(self, w: Wall) -> None:
        _text(w.id, "wall.id")
        if w.level_id not in self.levels:
            raise ValueError(f"wall {w.id}: unknown level {w.level_id!r}")
        s, e = _pt(w.start, "wall.start"), _pt(w.end, "wall.end")
        if distance(s, e) <= TOL:
            raise ValueError(f"wall {w.id} has zero length")
        _positive(w.thickness, "wall.thickness"); _positive(w.height, "wall.height")
        _text(w.material, "wall.material"); _json_safe(w.properties, "wall.properties")
        for o in w.openings:
            self._check_opening(w, o)
        ops = sorted(w.openings, key=lambda o: o.offset)
        for a, b in zip(ops, ops[1:]):
            if b.offset < a.offset + a.width - TOL:
                raise ValueError(f"opening {b.id} overlaps {a.id}")

    def _check_room(self, r: Room) -> None:
        _text(r.id, "room.id"); _text(r.name, "room.name")
        if r.level_id not in self.levels:
            raise ValueError(f"room {r.id}: unknown level {r.level_id!r}")
        validate_simple_polygon([_pt(p, "room.boundary point") for p in r.boundary])
        if r.target_area is not None:
            _positive(r.target_area, "room.target_area")

    def validate(self) -> None:
        """Check every invariant of the whole project. Raises ValueError listing the first problem."""
        _text(self.name, "project.name")
        if self.units not in UNITS:
            raise ValueError(f"units must be one of {UNITS}")
        for l in self.levels.values():
            self._check_level(l)
        for w in self.walls.values():
            self._check_wall(w)
        for r in self.rooms.values():
            self._check_room(r)
        for coll, name in ((self.levels, "level"), (self.walls, "wall"), (self.rooms, "room")):
            for k, v in coll.items():
                if k != v.id:
                    raise ValueError(f"{name} stored under key {k!r} but has id {v.id!r}")
        seen: set[str] = set()
        for w in self.walls.values():
            for o in w.openings:
                if o.id in seen:
                    raise ValueError(f"duplicate opening id {o.id}")
                seen.add(o.id)

    # ================================================================ authoring
    def _unique(self, coll: dict, id_: str, what: str) -> None:
        if id_ in coll:
            raise ValueError(f"duplicate {what} id {id_}")

    def add_level(self, name: str, elevation: float, height: float, id: str | None = None) -> Level:
        lv = Level(id or new_id("lvl"), name, elevation, height)
        self._check_level(lv)
        self._unique(self.levels, lv.id, "level")
        lv.elevation, lv.height = float(lv.elevation), float(lv.height)
        self.levels[lv.id] = lv
        return lv

    def add_wall(self, level_id: str, start, end, thickness: float, height: float | None = None,
                 material: str = "unspecified", properties: dict | None = None, id: str | None = None) -> Wall:
        if level_id not in self.levels:
            raise ValueError(f"unknown level {level_id}")
        h = self.levels[level_id].height if height is None else height
        w = Wall(id or new_id("wall"), level_id, _pt(start, "wall.start"), _pt(end, "wall.end"),
                 thickness, h, material, [], dict(properties or {}) if isinstance(properties or {}, dict) else properties)
        self._check_wall(w)
        self._unique(self.walls, w.id, "wall")
        w.thickness, w.height = float(w.thickness), float(w.height)
        self.walls[w.id] = w
        return w

    def add_opening(self, wall_id: str, kind: str, offset: float, width: float, height: float,
                    sill: float = 0.0, id: str | None = None) -> Opening:
        if wall_id not in self.walls:
            raise ValueError(f"unknown wall {wall_id}")
        w = self.walls[wall_id]
        op = Opening(id or new_id("op"), kind, offset, width, height, sill)
        self._check_opening(w, op)
        for o in w.openings:
            if op.offset < o.offset + o.width and o.offset < op.offset + op.width:
                raise ValueError(f"opening overlaps {o.id}")
        if any(op.id == o.id for x in self.walls.values() for o in x.openings):
            raise ValueError(f"duplicate opening id {op.id}")
        op.offset, op.width, op.height, op.sill = (float(op.offset), float(op.width), float(op.height), float(op.sill))
        w.openings.append(op)
        return op

    def add_room(self, name: str, level_id: str, boundary, target_area: float | None = None,
                 id: str | None = None) -> Room:
        if level_id not in self.levels:
            raise ValueError(f"unknown level {level_id}")
        if not isinstance(boundary, (list, tuple)):
            raise ValueError("room boundary must be a list of points")
        r = Room(id or new_id("room"), name, level_id, [_pt(p, "room.boundary point") for p in boundary], target_area)
        self._check_room(r)
        self._unique(self.rooms, r.id, "room")
        r.target_area = None if r.target_area is None else float(r.target_area)
        self.rooms[r.id] = r
        return r

    def find_opening(self, opening_id: str) -> tuple[Wall, Opening]:
        for w in self.walls.values():
            for o in w.openings:
                if o.id == opening_id:
                    return w, o
        raise ValueError(f"unknown opening {opening_id}")

    def remove_wall(self, wall_id: str) -> None:
        if wall_id not in self.walls:
            raise ValueError(f"unknown wall {wall_id}")
        self._graveyard[("walls", wall_id)] = self.walls.pop(wall_id)

    def remove_opening(self, opening_id: str) -> None:
        w, o = self.find_opening(opening_id)
        w.openings.remove(o)
        self._graveyard[("op", o.id)] = o

    # ================================================================ derived data
    def room_schedule(self) -> list[dict]:
        out = []
        for r in self.rooms.values():
            row = {"id": r.id, "name": r.name, "level": self.levels[r.level_id].name, "area": r.area}
            if r.target_area is not None:
                row["target_area"] = r.target_area
                row["delta"] = r.area - r.target_area
            out.append(row)
        return out

    def wall_quantities(self) -> list[dict]:
        return [{"id": w.id, "level": self.levels[w.level_id].name, "material": w.material,
                 "length": w.length, "gross_area": w.gross_area(), "net_area": w.net_area(),
                 "volume": w.volume()} for w in self.walls.values()]

    # ================================================================ serialisation
    def to_dict(self) -> dict:
        def wall(w: Wall) -> dict:
            return {"id": w.id, "level_id": w.level_id, "start": list(w.start), "end": list(w.end),
                    "thickness": w.thickness, "height": w.height, "material": w.material,
                    "properties": dict(w.properties),
                    "openings": [vars(o).copy() for o in w.openings]}
        return {
            "name": self.name, "units": self.units,
            "levels": [vars(l).copy() for l in self.levels.values()],
            "walls": [wall(w) for w in self.walls.values()],
            "rooms": [{"id": r.id, "name": r.name, "level_id": r.level_id,
                       "boundary": [list(p) for p in r.boundary], "target_area": r.target_area}
                      for r in self.rooms.values()],
        }

    def restore(self, d: dict) -> None:
        """Make this project equal to snapshot d *in place*, preserving object identity: an object
        that exists before and after keeps its Python identity, and one removed then restored
        (undo/redo) is the same object again. References held by callers therefore never detach."""
        fresh = Project.from_dict(d)
        self.name, self.units = fresh.name, fresh.units
        for attr in ("levels", "walls", "rooms"):
            cur, new = getattr(self, attr), getattr(fresh, attr)
            for i, obj in cur.items():
                if i not in new:
                    self._graveyard[(attr, i)] = obj
            merged = {}
            for i, nobj in new.items():
                old = cur.get(i)
                if old is None:
                    old = self._graveyard.pop((attr, i), None)
                if old is None:
                    merged[i] = nobj
                    continue
                if attr == "walls":
                    nobj.openings = self._reconcile_openings(old.openings, nobj.openings)
                old.__dict__.update(nobj.__dict__)
                merged[i] = old
            setattr(self, attr, merged)

    def _reconcile_openings(self, old: list, new: list) -> list:
        keep = {o.id: o for o in old}
        for o in old:
            if o.id not in {n.id for n in new}:
                self._graveyard[("op", o.id)] = o
        out = []
        for n in new:
            o = keep.get(n.id) or self._graveyard.pop(("op", n.id), None)
            if o is None:
                out.append(n)
            else:
                o.__dict__.update(n.__dict__)
                out.append(o)
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        """Strict import. Unknown/missing keys, wrong types, non-finite numbers, dangling references,
        duplicate ids and any violated invariant raise ValueError (never KeyError/TypeError)."""
        try:
            d = _obj(d, "project")
            p = cls(_text(d["name"], "project.name"), d["units"])
            for l in _list(d["levels"], "levels"):
                l = _obj(l, "level")
                cls._put(p.levels, Level(l["id"], l["name"], l["elevation"], l["height"]), "level")
            for w in _list(d["walls"], "walls"):
                w = _obj(w, "wall")
                ops = []
                for o in _list(w["openings"], "wall.openings"):
                    o = _obj(o, "opening")
                    ops.append(Opening(o["id"], o["kind"], o["offset"], o["width"], o["height"], o["sill"]))
                cls._put(p.walls, Wall(w["id"], w["level_id"], _pt(w["start"], "wall.start"), _pt(w["end"], "wall.end"),
                                       w["thickness"], w["height"], w["material"], ops, w["properties"]), "wall")
            for r in _list(d["rooms"], "rooms"):
                r = _obj(r, "room")
                cls._put(p.rooms, Room(r["id"], r["name"], r["level_id"],
                                       [_pt(x, "room.boundary point") for x in _list(r["boundary"], "room.boundary")],
                                       r["target_area"]), "room")
            p.validate()
            return p
        except (KeyError, TypeError, AttributeError, IndexError) as e:
            raise ValueError(f"malformed project data: {type(e).__name__}: {e}") from e

    @staticmethod
    def _put(coll: dict, obj, what: str) -> None:
        if not isinstance(obj.id, str) or obj.id in coll:
            raise ValueError(f"missing or duplicate {what} id {obj.id!r}")
        coll[obj.id] = obj
