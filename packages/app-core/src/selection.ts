import type { Level, Opening, Project, Room, Wall } from "./types.ts";

export type ElementRef =
  | { readonly type: "level"; readonly level: Level }
  | { readonly type: "wall"; readonly wall: Wall }
  | { readonly type: "opening"; readonly wall: Wall; readonly opening: Opening }
  | { readonly type: "room"; readonly room: Room };

export function resolveElement(project: Project, id: string): ElementRef | null {
  const level = project.levels.find((l) => l.id === id);
  if (level) return { type: "level", level };
  for (const wall of project.walls) {
    if (wall.id === id) return { type: "wall", wall };
    const opening = wall.openings.find((o) => o.id === id);
    if (opening) return { type: "opening", wall, opening };
  }
  const room = project.rooms.find((r) => r.id === id);
  return room ? { type: "room", room } : null;
}

/** Plain click replaces the selection; additive (shift/ctrl) toggles membership. Returns the same array when nothing changes. */
export function selectElement(sel: readonly string[], id: string, additive: boolean): readonly string[] {
  if (!additive) return sel.length === 1 && sel[0] === id ? sel : [id];
  return sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id];
}

/** Drop ids that no longer exist (after undo, delete or import). */
export function reconcile(sel: readonly string[], project: Project): readonly string[] {
  const kept = sel.filter((id) => resolveElement(project, id) !== null);
  return kept.length === sel.length ? sel : kept;
}

export interface TreeNode { readonly id: string; readonly type: ElementRef["type"]; readonly label: string; readonly children: readonly TreeNode[] }

const round = (n: number): string => String(Number(n.toFixed(3)));

export function hierarchy(project: Project): readonly TreeNode[] {
  return project.levels.map((level): TreeNode => ({
    id: level.id, type: "level", label: level.name,
    children: [
      ...project.walls.filter((w) => w.level_id === level.id).map((w): TreeNode => ({
        id: w.id, type: "wall", label: `Wall ${round(Math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1]))} ${project.units} · ${w.material}`,
        children: w.openings.map((o): TreeNode => ({ id: o.id, type: "opening", label: `${o.kind === "door" ? "Door" : "Window"} ${round(o.width)} × ${round(o.height)}`, children: [] })),
      })),
      ...project.rooms.filter((r) => r.level_id === level.id).map((r): TreeNode => ({ id: r.id, type: "room", label: r.name, children: [] })),
    ],
  }));
}
