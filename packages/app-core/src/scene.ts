import type { MeshData, MeshElement } from "./types.ts";

export interface SceneElement {
  readonly id: string; readonly type: "wall" | "opening"; readonly levelId: string;
  readonly wallId: string | null; readonly kind: "door" | "window" | null;
  readonly positions: Float32Array; readonly indices: Uint32Array;
}
export interface Bounds { readonly min: readonly [number, number, number]; readonly max: readonly [number, number, number]; readonly center: readonly [number, number, number]; readonly radius: number }
export interface Scene { readonly revision: number; readonly elements: readonly SceneElement[]; readonly bounds: Bounds }

function toElement(e: MeshElement): SceneElement {
  const vertexCount = e.positions.length / 3;
  for (const i of e.indices) if (i < 0 || i >= vertexCount) throw new Error(`element ${e.id}: index ${i} out of range (${vertexCount} vertices)`);
  return { id: e.id, type: e.type, levelId: e.level_id, wallId: e.wall_id, kind: e.kind, positions: Float32Array.from(e.positions), indices: Uint32Array.from(e.indices) };
}

export function computeBounds(elements: readonly SceneElement[]): Bounds {
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  let any = false;
  for (const el of elements) {
    for (let i = 0; i < el.positions.length; i += 3) {
      any = true;
      for (let k = 0; k < 3; k++) {
        const v = el.positions[i + k] as number;
        if (v < (min[k] as number)) min[k] = v;
        if (v > (max[k] as number)) max[k] = v;
      }
    }
  }
  if (!any) return { min: [0, 0, 0], max: [0, 0, 0], center: [0, 0, 0], radius: 1 };
  const center: [number, number, number] = [0, 1, 2].map((k) => ((min[k] as number) + (max[k] as number)) / 2) as [number, number, number];
  const radius = Math.max(0.5 * Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]), 1e-6);
  return { min, max, center, radius };
}

export function buildScene(mesh: MeshData): Scene {
  const elements = mesh.elements.map(toElement);
  const ids = new Set<string>();
  for (const e of elements) {
    if (ids.has(e.id)) throw new Error(`duplicate scene element ${e.id}`);
    ids.add(e.id);
  }
  // Opening proxies are selection volumes, not geometry of the building: keep them out of the framing.
  return { revision: mesh.revision, elements, bounds: computeBounds(elements.filter((e) => e.type === "wall")) };
}

/** Camera placement for a Z-up scene, looking at the bounds from a 3/4 view. */
export function fitCamera(b: Bounds, fovDegrees: number, aspect: number): { target: readonly [number, number, number]; position: readonly [number, number, number] } {
  const vFov = (fovDegrees * Math.PI) / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(aspect, 0.1));
  const dist = (b.radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.1;
  const dir = [0.6, -0.8, 0.55];
  const n = Math.hypot(dir[0] as number, dir[1] as number, dir[2] as number);
  return { target: b.center, position: [b.center[0] + ((dir[0] as number) / n) * dist, b.center[1] + ((dir[1] as number) / n) * dist, b.center[2] + ((dir[2] as number) / n) * dist] };
}
