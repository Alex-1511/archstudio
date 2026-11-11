// Runtime guards for server data. Types are not evidence: every response is checked before use.
import type { ApiState, MeshData, MeshElement, Opening, OpeningKind, Point, Project, Room, ToolInfo, Units, Wall, Level } from "./types.ts";

export class ProtocolError extends Error {}

type Rec = Record<string, unknown>;
const bad = (path: string, want: string): never => { throw new ProtocolError(`${path}: expected ${want}`); };
const rec = (x: unknown, p: string): Rec => (typeof x === "object" && x !== null && !Array.isArray(x) ? (x as Rec) : bad(p, "object"));
const arr = (x: unknown, p: string): unknown[] => (Array.isArray(x) ? x : bad(p, "array"));
const str = (x: unknown, p: string): string => (typeof x === "string" ? x : bad(p, "string"));
const num = (x: unknown, p: string): number => (typeof x === "number" && Number.isFinite(x) ? x : bad(p, "finite number"));
const int = (x: unknown, p: string): number => (Number.isInteger(x) ? (x as number) : bad(p, "integer"));
const UNITS: readonly string[] = ["m", "cm", "mm", "ft", "in"];
const KINDS: readonly string[] = ["door", "window"];
const kind = (x: unknown, p: string): OpeningKind => (typeof x === "string" && KINDS.includes(x) ? (x as OpeningKind) : bad(p, "door|window"));
const point = (x: unknown, p: string): Point => {
  const a = arr(x, p);
  return a.length === 2 ? [num(a[0], `${p}[0]`), num(a[1], `${p}[1]`)] : bad(p, "[x, y]");
};

function opening(x: unknown, p: string): Opening {
  const o = rec(x, p);
  return { id: str(o.id, `${p}.id`), kind: kind(o.kind, `${p}.kind`), offset: num(o.offset, `${p}.offset`), width: num(o.width, `${p}.width`), height: num(o.height, `${p}.height`), sill: num(o.sill, `${p}.sill`) };
}
function wall(x: unknown, p: string): Wall {
  const w = rec(x, p);
  return {
    id: str(w.id, `${p}.id`), level_id: str(w.level_id, `${p}.level_id`), start: point(w.start, `${p}.start`), end: point(w.end, `${p}.end`),
    thickness: num(w.thickness, `${p}.thickness`), height: num(w.height, `${p}.height`), material: str(w.material, `${p}.material`),
    properties: rec(w.properties, `${p}.properties`), openings: arr(w.openings, `${p}.openings`).map((o, i) => opening(o, `${p}.openings[${i}]`)),
  };
}
function level(x: unknown, p: string): Level {
  const l = rec(x, p);
  return { id: str(l.id, `${p}.id`), name: str(l.name, `${p}.name`), elevation: num(l.elevation, `${p}.elevation`), height: num(l.height, `${p}.height`) };
}
function room(x: unknown, p: string): Room {
  const r = rec(x, p);
  return {
    id: str(r.id, `${p}.id`), name: str(r.name, `${p}.name`), level_id: str(r.level_id, `${p}.level_id`),
    boundary: arr(r.boundary, `${p}.boundary`).map((q, i) => point(q, `${p}.boundary[${i}]`)),
    target_area: r.target_area === null ? null : num(r.target_area, `${p}.target_area`),
  };
}

export function parseProject(x: unknown, p = "project"): Project {
  const o = rec(x, p);
  const units = str(o.units, `${p}.units`);
  if (!UNITS.includes(units)) bad(`${p}.units`, UNITS.join("|"));
  return {
    name: str(o.name, `${p}.name`), units: units as Units,
    levels: arr(o.levels, `${p}.levels`).map((l, i) => level(l, `${p}.levels[${i}]`)),
    walls: arr(o.walls, `${p}.walls`).map((w, i) => wall(w, `${p}.walls[${i}]`)),
    rooms: arr(o.rooms, `${p}.rooms`).map((r, i) => room(r, `${p}.rooms[${i}]`)),
  };
}

export function parseState(x: unknown): ApiState {
  const o = rec(x, "response");
  const result = o.result === undefined ? null : rec(o.result, "response.result");
  const label = o.label === undefined || o.label === null ? null : str(o.label, "response.label");
  return { revision: int(o.revision, "response.revision"), project: parseProject(o.project, "response.project"), label, result };
}

function meshElement(x: unknown, p: string): MeshElement {
  const e = rec(x, p);
  const type = e.type === "wall" || e.type === "opening" ? e.type : bad(`${p}.type`, "wall|opening");
  const positions = arr(e.positions, `${p}.positions`).map((v, i) => num(v, `${p}.positions[${i}]`));
  const indices = arr(e.indices, `${p}.indices`).map((v, i) => int(v, `${p}.indices[${i}]`));
  if (positions.length % 3 !== 0 || indices.length % 3 !== 0) bad(p, "positions/indices in multiples of 3");
  return {
    id: str(e.id, `${p}.id`), type, level_id: str(e.level_id, `${p}.level_id`),
    wall_id: e.wall_id === undefined ? null : str(e.wall_id, `${p}.wall_id`), kind: e.kind === undefined ? null : kind(e.kind, `${p}.kind`),
    positions, indices,
  };
}

export function parseMesh(x: unknown): MeshData {
  const o = rec(x, "mesh");
  return { revision: int(o.revision, "mesh.revision"), units: str(o.units, "mesh.units"), elements: arr(o.elements, "mesh.elements").map((e, i) => meshElement(e, `mesh.elements[${i}]`)) };
}

export function parseTools(x: unknown): readonly ToolInfo[] {
  const o = rec(x, "tools");
  return arr(o.tools, "tools.tools").map((t, i): ToolInfo => {
    const r = rec(t, `tools[${i}]`);
    return {
      name: str(r.name, `tools[${i}].name`), write: typeof r.write === "boolean" ? r.write : bad(`tools[${i}].write`, "boolean"),
      required: arr(r.required, "required").map((s) => str(s, "required[]")), optional: arr(r.optional, "optional").map((s) => str(s, "optional[]")),
    };
  });
}
