// Turns a selected element into editable fields, and raw user input into a validated engine tool call.
// Local validation is for fast feedback only; the Python engine remains the authority.
import { resolveElement } from "./selection.ts";
import type { ElementRef } from "./selection.ts";
import type { Project } from "./types.ts";

export type FieldKind = "number" | "text" | "enum" | "readonly";
export interface Field { readonly key: string; readonly label: string; readonly kind: FieldKind; readonly value: string; readonly unit: string | null; readonly options: readonly string[] | null }
export interface InspectorModel { readonly id: string; readonly type: ElementRef["type"]; readonly title: string; readonly fields: readonly Field[]; readonly deletable: boolean }
export type EditResult =
  | { readonly ok: true; readonly noop: false; readonly tool: string; readonly args: Readonly<Record<string, unknown>> }
  | { readonly ok: true; readonly noop: true }
  | { readonly ok: false; readonly error: string };

export const MAX_MAGNITUDE = 1e9;
const NUMBER_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

/** Strict: rejects "", " ", "0x10", "1,5", "NaN", "Infinity", "1_000"; Number() alone accepts several of these. */
export function parseNumberStrict(raw: string): number | null {
  const s = raw.trim();
  if (!NUMBER_RE.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) && Math.abs(n) <= MAX_MAGNITUDE ? n : null;
}

export const fmt = (n: number): string => String(Number(n.toFixed(4)));

type Rule = "any" | "positive" | "nonneg";
interface Spec { readonly key: string; readonly label: string; readonly kind: "number" | "text" | "enum"; readonly rule?: Rule; readonly lengthUnit?: boolean; readonly options?: readonly string[] }

const SPECS = {
  level: [{ key: "name", label: "Name", kind: "text" }, { key: "elevation", label: "Elevation", kind: "number", rule: "any", lengthUnit: true }, { key: "height", label: "Height", kind: "number", rule: "positive", lengthUnit: true }],
  wall: [{ key: "material", label: "Material", kind: "text" }, { key: "thickness", label: "Thickness", kind: "number", rule: "positive", lengthUnit: true }, { key: "height", label: "Height", kind: "number", rule: "positive", lengthUnit: true }],
  opening: [{ key: "kind", label: "Type", kind: "enum", options: ["door", "window"] }, { key: "offset", label: "Offset along wall", kind: "number", rule: "nonneg", lengthUnit: true }, { key: "width", label: "Width", kind: "number", rule: "positive", lengthUnit: true }, { key: "height", label: "Height", kind: "number", rule: "positive", lengthUnit: true }, { key: "sill", label: "Sill height", kind: "number", rule: "nonneg", lengthUnit: true }],
  room: [{ key: "name", label: "Name", kind: "text" }, { key: "target_area", label: "Target area", kind: "number", rule: "positive" }],
} as const satisfies Record<string, readonly Spec[]>;

const TOOL: Record<ElementRef["type"], { tool: string; idArg: string }> = {
  level: { tool: "modify_level", idArg: "level_id" }, wall: { tool: "modify_wall", idArg: "wall_id" },
  opening: { tool: "modify_opening", idArg: "opening_id" }, room: { tool: "modify_room", idArg: "room_id" },
};

function currentValues(ref: ElementRef): Readonly<Record<string, unknown>> {
  switch (ref.type) {
    case "level": return { ...ref.level };
    case "wall": return { ...ref.wall };
    case "opening": return { ...ref.opening };
    case "room": return { ...ref.room };
  }
}

function shoelace(pts: readonly (readonly [number, number])[]): number {
  let s = 0;
  pts.forEach((p, i) => { const q = pts[(i + 1) % pts.length] as readonly [number, number]; s += p[0] * q[1] - q[0] * p[1]; });
  return Math.abs(s) / 2;
}

export function inspectorFor(project: Project, id: string): InspectorModel | null {
  const ref = resolveElement(project, id);
  if (!ref) return null;
  const u = project.units;
  const vals = currentValues(ref);
  const editable = SPECS[ref.type].map((s: Spec): Field => ({
    key: s.key, label: s.label, kind: s.kind,
    value: vals[s.key] === null || vals[s.key] === undefined ? "" : typeof vals[s.key] === "number" ? fmt(vals[s.key] as number) : String(vals[s.key]),
    unit: s.lengthUnit ? u : s.key === "target_area" ? `${u}²` : null, options: s.options ?? null,
  }));
  const ro = (key: string, label: string, value: string, unit: string | null = null): Field => ({ key, label, kind: "readonly", value, unit, options: null });
  const extra: Field[] = [ro("id", "ID", id)];
  let title: string;
  if (ref.type === "wall") {
    const w = ref.wall;
    title = "Wall";
    extra.push(ro("length", "Length", fmt(Math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1])), u), ro("start", "Start", `${fmt(w.start[0])}, ${fmt(w.start[1])}`, u), ro("end", "End", `${fmt(w.end[0])}, ${fmt(w.end[1])}`, u), ro("openings", "Openings", String(w.openings.length)), ro("level", "Level", project.levels.find((l) => l.id === w.level_id)?.name ?? w.level_id));
  } else if (ref.type === "opening") {
    title = ref.opening.kind === "door" ? "Door" : "Window";
    extra.push(ro("wall", "Host wall", ref.wall.id));
  } else if (ref.type === "room") {
    title = "Room";
    extra.push(ro("area", "Area (display only)", fmt(shoelace(ref.room.boundary)), `${u}²`));
  } else {
    title = "Level";
    extra.push(ro("walls", "Walls", String(project.walls.filter((w) => w.level_id === ref.level.id).length)));
  }
  return { id, type: ref.type, title, fields: [...editable, ...extra], deletable: ref.type === "wall" || ref.type === "opening" };
}

export function buildEdit(project: Project, id: string, key: string, raw: string): EditResult {
  const ref = resolveElement(project, id);
  if (!ref) return { ok: false, error: `element ${id} no longer exists` };
  const specs: readonly Spec[] = SPECS[ref.type];
  const spec = specs.find((s) => s.key === key);
  if (!spec) return { ok: false, error: `${key} is not editable` };
  const current = currentValues(ref)[key];
  let value: string | number;
  if (spec.kind === "number") {
    const n = parseNumberStrict(raw);
    if (n === null) return { ok: false, error: `${spec.label}: enter a plain number (no commas, units or hex)` };
    if (spec.rule === "positive" && n <= 0) return { ok: false, error: `${spec.label} must be greater than 0` };
    if (spec.rule === "nonneg" && n < 0) return { ok: false, error: `${spec.label} must not be negative` };
    value = n;
  } else if (spec.kind === "enum") {
    const v = raw.trim();
    if (!(spec.options ?? []).includes(v)) return { ok: false, error: `${spec.label} must be one of ${(spec.options ?? []).join(", ")}` };
    value = v;
  } else {
    const v = raw.trim();
    if (v === "") return { ok: false, error: `${spec.label} must not be empty` };
    value = v;
  }
  if (value === current) return { ok: true, noop: true };
  const t = TOOL[ref.type];
  return { ok: true, noop: false, tool: t.tool, args: { [t.idArg]: id, [key]: value } };
}

export function deleteCommand(project: Project, id: string): { readonly tool: string; readonly args: Readonly<Record<string, unknown>> } | null {
  const ref = resolveElement(project, id);
  if (ref?.type === "wall") return { tool: "delete_wall", args: { wall_id: id } };
  if (ref?.type === "opening") return { tool: "delete_opening", args: { opening_id: id } };
  return null;
}
