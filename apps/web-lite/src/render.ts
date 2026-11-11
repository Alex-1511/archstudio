// Canvas 2D software renderer: back-face culling + painter's algorithm, Lambert shading, ground grid.
// Deliberately simple and dependency-free; the Three.js viewport in apps/web replaces it, not the logic around it.
import { basis, project } from "../../../packages/app-core/src/camera.ts";
import type { Camera, Vec3 } from "../../../packages/app-core/src/camera.ts";
import type { Scene } from "../../../packages/app-core/src/scene.ts";

export interface Palette { readonly canvas: string; readonly grid: string; readonly wall: string; readonly door: string; readonly window: string; readonly accent: string }
type RGB = readonly [number, number, number];

const hex = (s: string): RGB => {
  const m = /^#([0-9a-f]{6})$/i.exec(s.trim());
  if (!m) return [128, 128, 128];
  const n = parseInt(m[1] as string, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const css = (c: RGB, alpha = 1): string => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${alpha})`;
const LIGHT: Vec3 = (() => { const v: Vec3 = [0.35, -0.45, 0.82]; const l = Math.hypot(...v); return [v[0] / l, v[1] / l, v[2] / l]; })();

export function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const g = (n: string): string => cs.getPropertyValue(n).trim();
  return { canvas: g("--canvas"), grid: g("--grid"), wall: g("--wall"), door: g("--door"), window: g("--window"), accent: g("--accent") };
}

interface Tri { readonly depth: number; readonly pts: readonly [number, number, number, number, number, number]; readonly fill: string; readonly stroke: string | null; readonly lw: number }

export function draw(ctx: CanvasRenderingContext2D, scene: Scene | null, cam: Camera, selected: ReadonlySet<string>, pal: Palette, w: number, h: number): void {
  ctx.fillStyle = pal.canvas; ctx.fillRect(0, 0, w, h);
  if (!scene) return;
  drawGrid(ctx, scene, cam, pal, w, h);
  const b = basis(cam);
  const tris: Tri[] = [];
  for (const el of scene.elements) {
    const sel = selected.has(el.id);
    const base = hex(el.type === "wall" ? pal.wall : el.kind === "door" ? pal.door : pal.window);
    const accent = hex(pal.accent);
    const p = el.positions, ix = el.indices;
    for (let i = 0; i < ix.length; i += 3) {
      const a = (ix[i] as number) * 3, bb = (ix[i + 1] as number) * 3, c = (ix[i + 2] as number) * 3;
      const v0: Vec3 = [p[a] as number, p[a + 1] as number, p[a + 2] as number], v1: Vec3 = [p[bb] as number, p[bb + 1] as number, p[bb + 2] as number], v2: Vec3 = [p[c] as number, p[c + 1] as number, p[c + 2] as number];
      const e1: Vec3 = [v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]], e2: Vec3 = [v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]];
      let n: Vec3 = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
      const nl = Math.hypot(...n); if (nl === 0) continue; n = [n[0] / nl, n[1] / nl, n[2] / nl];
      const toCam: Vec3 = cam.orthoHalfHeight !== undefined ? [-b.forward[0], -b.forward[1], -b.forward[2]] : [b.position[0] - v0[0], b.position[1] - v0[1], b.position[2] - v0[2]];
      if (n[0] * toCam[0] + n[1] * toCam[1] + n[2] * toCam[2] <= 0) continue;           // back face
      const s0 = project(cam, v0, w, h), s1 = project(cam, v1, w, h), s2 = project(cam, v2, w, h);
      if (!s0 || !s1 || !s2) continue;
      const lit = 0.42 + 0.58 * Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]);
      let col: RGB = [base[0] * lit, base[1] * lit, base[2] * lit];
      if (sel) col = mix(col, accent, 0.6);
      const alpha = el.type === "opening" ? (sel ? 0.75 : 0.35) : 1;
      tris.push({ depth: (s0.depth + s1.depth + s2.depth) / 3, pts: [s0.x, s0.y, s1.x, s1.y, s2.x, s2.y], fill: css(col, alpha), stroke: sel ? css(accent, 1) : el.type === "wall" ? css(col, 1) : null, lw: sel ? 1.2 : 0.6 });
    }
  }
  tris.sort((x, y) => y.depth - x.depth);   // far to near
  for (const t of tris) {
    ctx.beginPath(); ctx.moveTo(t.pts[0], t.pts[1]); ctx.lineTo(t.pts[2], t.pts[3]); ctx.lineTo(t.pts[4], t.pts[5]); ctx.closePath();
    ctx.fillStyle = t.fill; ctx.fill();
    if (t.stroke) { ctx.strokeStyle = t.stroke; ctx.lineWidth = t.lw; ctx.stroke(); }  // stroke hides seams between triangles
  }
}

function drawGrid(ctx: CanvasRenderingContext2D, scene: Scene, cam: Camera, pal: Palette, w: number, h: number): void {
  const bd = scene.bounds, z = bd.min[2];
  const step = Math.pow(10, Math.floor(Math.log10(Math.max(bd.radius, 1) / 3)));
  const x0 = Math.floor((bd.min[0] - bd.radius) / step) * step, x1 = bd.max[0] + bd.radius, y0 = Math.floor((bd.min[1] - bd.radius) / step) * step, y1 = bd.max[1] + bd.radius;
  ctx.strokeStyle = pal.grid; ctx.lineWidth = 1; ctx.beginPath();
  const seg = (a: Vec3, c: Vec3): void => { const p = project(cam, a, w, h), q = project(cam, c, w, h); if (p && q) { ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); } };
  for (let x = x0; x <= x1; x += step) seg([x, y0, z], [x, y1, z]);
  for (let y = y0; y <= y1; y += step) seg([x0, y, z], [x1, y, z]);
  ctx.stroke();
}
