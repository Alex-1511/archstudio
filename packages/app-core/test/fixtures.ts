import type { ApiState, MeshData, MeshElement, Project } from "../src/types.ts";

export function sampleProject(): Project {
  return {
    name: "Sample", units: "m",
    levels: [{ id: "lvl-1", name: "Ground", elevation: 0, height: 3 }],
    walls: [
      { id: "w1", level_id: "lvl-1", start: [0, 0], end: [10, 0], thickness: 0.23, height: 3, material: "brick", properties: {}, openings: [{ id: "o1", kind: "door", offset: 1, width: 0.9, height: 2.1, sill: 0 }] },
      { id: "w2", level_id: "lvl-1", start: [10, 0], end: [10, 8], thickness: 0.23, height: 3, material: "brick", properties: {}, openings: [] },
    ],
    rooms: [{ id: "r1", name: "Living", level_id: "lvl-1", boundary: [[0, 0], [10, 0], [10, 8], [0, 8]], target_area: 80 }],
  };
}

export function cube(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): { positions: number[]; indices: number[] } {
  const positions = [x0, y0, z0, x1, y0, z0, x1, y1, z0, x0, y1, z0, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1];
  const indices = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7];
  return { positions, indices };
}

export function meshFor(p: Project, revision: number): MeshData {
  const elements: MeshElement[] = [];
  p.walls.forEach((w, i) => {
    elements.push({ id: w.id, type: "wall", level_id: w.level_id, wall_id: null, kind: null, ...cube(i * 11, 0, 0, i * 11 + 10, w.thickness, w.height) });
    for (const o of w.openings) elements.push({ id: o.id, type: "opening", level_id: w.level_id, wall_id: w.id, kind: o.kind, ...cube(i * 11 + o.offset, 0, o.sill, i * 11 + o.offset + o.width, w.thickness, o.sill + o.height) });
  });
  return { revision, units: p.units, elements };
}

export const stateOf = (p: Project, revision: number, extra: Partial<ApiState> = {}): ApiState => ({ revision, project: p, label: null, result: null, ...extra });

/** The real wire format: the server omits wall_id/kind on walls instead of sending null (see contracts/api.v1.schema.json). */
export function wire(m: MeshData): unknown {
  return JSON.parse(JSON.stringify(m, (_k, v) => (v === null ? undefined : v)));
}
