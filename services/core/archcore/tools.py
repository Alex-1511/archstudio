"""Tool layer: the single seam used by AI agents, the UI command bar and (later) MCP.
LLMs choose tools and arguments; geometry is computed here, never by the model.
Every call is schema-validated, permission-checked, and (for writes) undoable."""
from __future__ import annotations
import math, re
from typing import Any
from .history import History
from .bim import OPENING_KINDS


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- argument schemas
def _num(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
def _pos(v): return _num(v) and v > 0
def _nonneg(v): return _num(v) and v >= 0
def _str(v): return isinstance(v, str) and bool(v.strip())
def _pt(v): return isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(c) for c in v)
def _pts(v): return isinstance(v, (list, tuple)) and len(v) >= 3 and all(_pt(p) for p in v)
def _kind(v): return v in OPENING_KINDS

# tool -> (required {arg: validator}, optional {arg: validator})
SCHEMAS = {
    "create_level": ({"name": _str, "elevation": _num, "height": _pos}, {}),
    "create_wall": ({"level_id": _str, "start": _pt, "end": _pt, "thickness": _pos}, {"height": _pos, "material": _str}),
    "add_opening": ({"wall_id": _str, "kind": _kind, "offset": _nonneg, "width": _pos, "height": _pos}, {"sill": _nonneg}),
    "create_room": ({"name": _str, "level_id": _str, "boundary": _pts}, {"target_area": _pos}),
    "modify_wall": ({"wall_id": _str}, {"thickness": _pos, "height": _pos, "material": _str}),
    "modify_level": ({"level_id": _str}, {"name": _str, "elevation": _num, "height": _pos}),
    "modify_opening": ({"opening_id": _str}, {"kind": _kind, "offset": _nonneg, "width": _pos, "height": _pos, "sill": _nonneg}),
    "modify_room": ({"room_id": _str}, {"name": _str, "target_area": _pos}),
    "delete_wall": ({"wall_id": _str}, {}),
    "delete_opening": ({"opening_id": _str}, {}),
    "calculate_room_area": ({"room_id": _str}, {}),
    "inspect_project": ({}, {}),
}


def validate_args(name: str, args: Any) -> None:
    if name not in SCHEMAS:
        raise ToolError(f"unknown tool {name!r}")
    if not isinstance(args, dict):
        raise ToolError(f"{name}: args must be an object")
    req, opt = SCHEMAS[name]
    missing = [k for k in req if k not in args]
    if missing:
        raise ToolError(f"{name}: missing required argument(s) {missing}")
    unknown = [k for k in args if k not in req and k not in opt]
    if unknown:
        raise ToolError(f"{name}: unknown argument(s) {unknown}")
    for k, v in args.items():
        if not (req.get(k) or opt[k])(v):
            raise ToolError(f"{name}: invalid value for {k!r}: {v!r}")


# ---------------------------------------------------------------- implementations
def _create_level(p, a): return vars(p.add_level(a["name"], a["elevation"], a["height"])).copy()
def _create_wall(p, a):
    w = p.add_wall(a["level_id"], a["start"], a["end"], a["thickness"], a.get("height"), a.get("material", "unspecified"))
    return {"id": w.id, "length": w.length}
def _add_opening(p, a):
    return {"id": p.add_opening(a["wall_id"], a["kind"], a["offset"], a["width"], a["height"], a.get("sill", 0.0)).id}
def _create_room(p, a):
    r = p.add_room(a["name"], a["level_id"], a["boundary"], a.get("target_area"))
    return {"id": r.id, "area": r.area}
def _room_area(p, a):
    if a["room_id"] not in p.rooms:
        raise ValueError(f"unknown room {a['room_id']}")
    return {"area": p.rooms[a["room_id"]].area}
def _inspect(p, a):
    return {"levels": [vars(l).copy() for l in p.levels.values()], "walls": list(p.walls),
            "rooms": list(p.rooms), "schedule": p.room_schedule()}
def _modify_wall(p, a):
    w = p.walls.get(a["wall_id"])
    if w is None:
        raise ValueError(f"unknown wall {a['wall_id']}")
    if "height" in a and any(o.sill + o.height > a["height"] for o in w.openings):
        raise ValueError("new height would cut through an existing opening")
    if "thickness" in a: w.thickness = float(a["thickness"])
    if "height" in a: w.height = float(a["height"])
    if "material" in a: w.material = a["material"]
    return {"id": w.id}

def _modify_level(p, a):
    l = p.levels.get(a["level_id"])
    if l is None:
        raise ValueError(f"unknown level {a['level_id']}")
    for k in ("name", "elevation", "height"):
        if k in a: setattr(l, k, a[k])
    return {"id": l.id}
def _modify_opening(p, a):
    _, o = p.find_opening(a["opening_id"])
    for k in ("kind", "offset", "width", "height", "sill"):
        if k in a: setattr(o, k, a[k])
    return {"id": o.id}
def _modify_room(p, a):
    r = p.rooms.get(a["room_id"])
    if r is None:
        raise ValueError(f"unknown room {a['room_id']}")
    if "name" in a: r.name = a["name"]
    if "target_area" in a: r.target_area = a["target_area"]
    return {"id": r.id}
def _delete_wall(p, a): p.remove_wall(a["wall_id"]); return {"deleted": a["wall_id"]}
def _delete_opening(p, a): p.remove_opening(a["opening_id"]); return {"deleted": a["opening_id"]}

TOOLS = {  # name -> (function, is_write)
    "modify_level": (_modify_level, True), "modify_opening": (_modify_opening, True),
    "modify_room": (_modify_room, True), "delete_wall": (_delete_wall, True),
    "delete_opening": (_delete_opening, True),
    "create_level": (_create_level, True), "create_wall": (_create_wall, True),
    "add_opening": (_add_opening, True), "create_room": (_create_room, True),
    "modify_wall": (_modify_wall, True),
    "calculate_room_area": (_room_area, False), "inspect_project": (_inspect, False),
}


def apply_tool_call(history: History, name: str, args: dict, permissions: frozenset = frozenset({"read"})) -> Any:
    if name not in TOOLS:
        raise ToolError(f"unknown tool {name!r}")
    validate_args(name, args)
    fn, is_write = TOOLS[name]
    needed = "write" if is_write else "read"
    if needed not in permissions:
        raise ToolError(f"tool {name!r} requires {needed!r} permission")
    try:
        if is_write:
            return history.apply(f"{name}({args})", lambda p: fn(p, args))  # reversible via undo
        return fn(history.project, args)
    except (ValueError, KeyError, TypeError) as e:
        raise ToolError(f"{name}: {type(e).__name__}: {e}") from e


_REF = re.compile(r"^\$(\d+)\.(\w+)$")


def _resolve(value, results):
    if isinstance(value, str):
        m = _REF.match(value)
        if m:
            i, key = int(m.group(1)), m.group(2)
            if i >= len(results) or not isinstance(results[i], dict) or key not in results[i]:
                raise ToolError(f"unresolvable reference {value!r}")
            return results[i][key]
        return value
    if isinstance(value, list):
        return [_resolve(v, results) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, results) for k, v in value.items()}
    return value


def apply_batch(history: History, calls: list[dict], permissions: frozenset = frozenset({"read"})) -> list:
    """Run calls in order as one all-or-nothing unit. Args may reference earlier results as "$0.id"."""
    results, applied_writes = [], 0
    try:
        for c in calls:
            args = _resolve(c.get("args", {}), results)
            is_write = c["tool"] in TOOLS and TOOLS[c["tool"]][1]
            results.append(apply_tool_call(history, c["tool"], args, permissions))
            applied_writes += is_write
    except ToolError as e:
        for _ in range(applied_writes):
            history.undo()
        raise ToolError(f"batch aborted at call {len(results)} and rolled back: {e}") from e
    return results
