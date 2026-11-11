// Orbit camera, projection and ray picking for a Z-up scene. Pure math: no DOM, no WebGL.
import type { Bounds, Scene } from "./scene.ts";

export type Vec3 = readonly [number, number, number];
/** `orthoHalfHeight` set => orthographic projection (half the visible height in model units); unset => perspective. */
export interface Camera { readonly target: Vec3; readonly yaw: number; readonly pitch: number; readonly distance: number; readonly fovDeg: number; readonly orthoHalfHeight?: number }

const MAX_PITCH = 1.55; // just short of straight down/up so the basis never degenerates
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: Vec3): Vec3 => { const l = Math.hypot(a[0], a[1], a[2]); return l === 0 ? [0, 0, 0] : mul(a, 1 / l); };
export const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

export function cameraPosition(c: Camera): Vec3 {
  return add(c.target, [c.distance * Math.cos(c.pitch) * Math.cos(c.yaw), c.distance * Math.cos(c.pitch) * Math.sin(c.yaw), c.distance * Math.sin(c.pitch)]);
}
export interface Basis { readonly position: Vec3; readonly forward: Vec3; readonly right: Vec3; readonly up: Vec3 }
export function basis(c: Camera): Basis {
  const position = cameraPosition(c);
  const forward = norm(sub(c.target, position));
  const right: Vec3 = [-Math.sin(c.yaw), Math.cos(c.yaw), 0];   // horizontal and exact, so straight-down (pitch = 90°) is not degenerate
  return { position, forward, right, up: cross(right, forward) };
}

/** Frame bounds from a 3/4 view (or straight-down "plan" view). */
export function frameBounds(b: Bounds, fovDeg: number, aspect: number, view: "perspective" | "plan" = "perspective"): Camera {
  const vFov = (fovDeg * Math.PI) / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(aspect, 0.1));
  const distance = (b.radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.15;
  if (view === "plan") {   // true orthographic top view, +Y up the screen
    const halfHeight = (aspect >= 1 ? b.radius : b.radius / Math.max(aspect, 0.1)) * 1.12;
    return { target: b.center, yaw: -Math.PI / 2, pitch: Math.PI / 2, distance: b.radius * 4, fovDeg, orthoHalfHeight: halfHeight };
  }
  return { target: b.center, yaw: Math.atan2(-0.8, 0.6), pitch: 0.55, distance, fovDeg };
}

/** Orbiting leaves orthographic mode (back to perspective at a sensible distance for the same framing). */
export function orbit(c: Camera, dYaw: number, dPitch: number): Camera {
  const { orthoHalfHeight, ...rest } = c;
  const distance = orthoHalfHeight === undefined ? c.distance : orthoHalfHeight / Math.tan((c.fovDeg * Math.PI) / 360);
  return { ...rest, distance, yaw: c.yaw + dYaw, pitch: clamp(c.pitch + dPitch, -MAX_PITCH, MAX_PITCH) };
}
export function zoom(c: Camera, factor: number, minD: number, maxD: number): Camera {
  return c.orthoHalfHeight === undefined ? { ...c, distance: clamp(c.distance * factor, minD, maxD) } : { ...c, orthoHalfHeight: clamp(c.orthoHalfHeight * factor, minD, maxD) };
}

export interface Projected { readonly x: number; readonly y: number; readonly depth: number }
const NEAR = 1e-3;

export function project(c: Camera, p: Vec3, width: number, height: number): Projected | null {
  const b = basis(c);
  const v = sub(p, b.position);
  const zc = dot(v, b.forward);
  const aspect = width / height;
  let nx: number, ny: number;
  if (c.orthoHalfHeight !== undefined) {
    nx = dot(v, b.right) / (c.orthoHalfHeight * aspect);
    ny = dot(v, b.up) / c.orthoHalfHeight;
  } else {
    if (zc <= NEAR) return null;
    const f = 1 / Math.tan((c.fovDeg * Math.PI) / 360);
    nx = ((dot(v, b.right) / zc) * f) / aspect;
    ny = (dot(v, b.up) / zc) * f;
  }
  return { x: (nx * 0.5 + 0.5) * width, y: (1 - (ny * 0.5 + 0.5)) * height, depth: zc };
}

export interface Ray { readonly origin: Vec3; readonly dir: Vec3 }
export function rayFromPixel(c: Camera, px: number, py: number, width: number, height: number): Ray {
  const b = basis(c);
  const nx = (px / width) * 2 - 1, ny = 1 - (py / height) * 2;
  if (c.orthoHalfHeight !== undefined) {   // parallel rays, origin slides across the image plane
    const hh = c.orthoHalfHeight, origin = add(add(b.position, mul(b.right, nx * hh * (width / height))), mul(b.up, ny * hh));
    return { origin, dir: b.forward };
  }
  const t = Math.tan((c.fovDeg * Math.PI) / 360);
  return { origin: b.position, dir: norm(add(add(b.forward, mul(b.right, nx * t * (width / height))), mul(b.up, ny * t))) };
}

/** Möller–Trumbore, two-sided. Returns distance along the ray, or null. */
export function rayTriangle(r: Ray, a: Vec3, b: Vec3, c: Vec3): number | null {
  const e1 = sub(b, a), e2 = sub(c, a);
  const h = cross(r.dir, e2);
  const det = dot(e1, h);
  if (Math.abs(det) < 1e-12) return null;
  const inv = 1 / det;
  const s = sub(r.origin, a);
  const u = dot(s, h) * inv;
  if (u < 0 || u > 1) return null;
  const q = cross(s, e1);
  const v = dot(r.dir, q) * inv;
  if (v < 0 || u + v > 1) return null;
  const t = dot(e2, q) * inv;
  return t > NEAR ? t : null;
}

export interface Pick { readonly id: string; readonly distance: number }
/** Nearest hit wins; on a near-tie (coincident faces) an opening beats the wall around it so doors and windows stay selectable. */
export function pickElement(scene: Scene, c: Camera, px: number, py: number, width: number, height: number): Pick | null {
  const ray = rayFromPixel(c, px, py, width, height);
  let best: (Pick & { readonly rank: number }) | null = null;
  for (const el of scene.elements) {
    const rank = el.type === "opening" ? 1 : 0;
    for (let i = 0; i < el.indices.length; i += 3) {
      const v = (k: number): Vec3 => { const j = (el.indices[i + k] as number) * 3; return [el.positions[j] as number, el.positions[j + 1] as number, el.positions[j + 2] as number]; };
      const t = rayTriangle(ray, v(0), v(1), v(2));
      if (t === null) continue;
      if (best === null || t < best.distance - 1e-6 || (Math.abs(t - best.distance) <= 1e-6 && rank > best.rank)) best = { id: el.id, distance: t, rank };
    }
  }
  return best ? { id: best.id, distance: best.distance } : null;
}
