import test from "node:test";
import assert from "node:assert/strict";
import { basis, cameraPosition, clamp, frameBounds, orbit, pickElement, project, rayFromPixel, rayTriangle, zoom } from "../src/camera.ts";
import type { Camera, Vec3 } from "../src/camera.ts";
import { buildScene } from "../src/scene.ts";
import { cube, sampleProject, meshFor } from "./fixtures.ts";

const W = 800, H = 600;
const cam: Camera = { target: [0, 0, 0], yaw: Math.PI / 2 * -1, pitch: 0.4, distance: 20, fovDeg: 50 };
const near = (a: number, b: number, eps = 1e-6): void => assert.ok(Math.abs(a - b) <= eps, `${a} vs ${b}`);

test("camera basis is orthonormal and looks at the target", () => {
  const b = basis(cam);
  const d = (u: Vec3, v: Vec3): number => u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
  near(d(b.forward, b.right), 0); near(d(b.forward, b.up), 0); near(d(b.right, b.up), 0);
  near(Math.hypot(...b.forward), 1); near(Math.hypot(...b.right), 1); near(Math.hypot(...b.up), 1);
  near(d(b.up, [0, 0, 1]), Math.cos(cam.pitch), 1e-9);  // up stays upward
  const p = cameraPosition(cam);
  near(Math.hypot(p[0] - cam.target[0], p[1] - cam.target[1], p[2] - cam.target[2]), cam.distance);
});

test("target projects to the screen centre; behind-camera points are culled", () => {
  const s = project(cam, cam.target, W, H)!;
  near(s.x, W / 2); near(s.y, H / 2); near(s.depth, cam.distance);
  assert.equal(project(cam, mul(cameraPosition(cam), 2), W, H), null);
  const right = basis(cam).right;
  const r = project(cam, [right[0] * 2, right[1] * 2, right[2] * 2], W, H)!;
  assert.ok(r.x > W / 2, "points to the camera's right appear right of centre");
  const up = project(cam, [0, 0, 2], W, H)!;
  assert.ok(up.y < H / 2, "points above appear higher on screen");
});
const mul = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];

test("rayFromPixel inverts project: the ray through a point's pixel passes through the point", () => {
  for (const p of [[1, 2, 0.5], [-3, 1, 2], [0, 0, 0], [4, -4, 1]] as Vec3[]) {
    const s = project(cam, p, W, H)!;
    const r = rayFromPixel(cam, s.x, s.y, W, H);
    const t = (p[0] - r.origin[0]) * r.dir[0] + (p[1] - r.origin[1]) * r.dir[1] + (p[2] - r.origin[2]) * r.dir[2];
    const q: Vec3 = [r.origin[0] + r.dir[0] * t, r.origin[1] + r.dir[1] * t, r.origin[2] + r.dir[2] * t];
    near(Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]), 0, 1e-6);
  }
});

test("ray-triangle: hit, miss, parallel, behind", () => {
  const a: Vec3 = [0, 0, 0], b: Vec3 = [1, 0, 0], c: Vec3 = [0, 1, 0];
  near(rayTriangle({ origin: [0.25, 0.25, 5], dir: [0, 0, -1] }, a, b, c)!, 5);
  assert.equal(rayTriangle({ origin: [2, 2, 5], dir: [0, 0, -1] }, a, b, c), null);
  assert.equal(rayTriangle({ origin: [0.25, 0.25, 5], dir: [1, 0, 0] }, a, b, c), null);
  assert.equal(rayTriangle({ origin: [0.25, 0.25, -5], dir: [0, 0, -1] }, a, b, c), null);
  near(rayTriangle({ origin: [0.25, 0.25, -5], dir: [0, 0, 1] }, a, b, c)!, 5);   // two-sided
});

test("picking: nearest element wins, miss returns null, opening beats coincident wall", () => {
  const mk = (id: string, type: "wall" | "opening", c: ReturnType<typeof cube>) => ({ id, type, level_id: "l", wall_id: type === "opening" ? "near" : null, kind: type === "opening" ? ("door" as const) : null, ...c });
  const scene = buildScene({ revision: 1, units: "m", elements: [mk("far", "wall", cube(-1, 5, -1, 1, 7, 1)), mk("near", "wall", cube(-1, -1, -1, 1, 1, 1))] });
  const c: Camera = { target: [0, 0, 0], yaw: -Math.PI / 2, pitch: 0, distance: 15, fovDeg: 50 };
  assert.equal(pickElement(scene, c, W / 2, H / 2, W, H)!.id, "near");
  assert.equal(pickElement(scene, c, 5, 5, W, H), null);
  const tie = buildScene({ revision: 1, units: "m", elements: [mk("wall", "wall", cube(-1, -1, -1, 1, 1, 1)), mk("door", "opening", cube(-1, -1, -1, 1, 1, 1))] });
  assert.equal(pickElement(tie, c, W / 2, H / 2, W, H)!.id, "door");
});

test("picking the sample building: clicking a projected wall centre selects that wall", () => {
  const p = sampleProject();
  const scene = buildScene(meshFor(p, 1));
  const c = frameBounds(scene.bounds, 50, W / H);
  const el = scene.elements.find((e) => e.id === "w2")!;   // second wall, away from the door proxy
  const m: Vec3 = [(el.positions[0]! + el.positions[18]!) / 2, (el.positions[1]! + el.positions[19]!) / 2, (el.positions[2]! + el.positions[20]!) / 2];
  const s = project(c, m, W, H)!;
  assert.equal(pickElement(scene, c, s.x, s.y, W, H)!.id, "w2");
});

test("orbit clamps pitch, zoom clamps distance, frameBounds contains the scene", () => {
  assert.equal(orbit(cam, 0, 10).pitch, 1.55); assert.equal(orbit(cam, 0, -10).pitch, -1.55);
  near(orbit(cam, 1, 0).yaw, cam.yaw + 1);
  assert.equal(zoom(cam, 100, 1, 50).distance, 50); assert.equal(zoom(cam, 0.001, 1, 50).distance, 1);
  const scene = buildScene(meshFor(sampleProject(), 1));
  for (const view of ["perspective", "plan"] as const) for (const aspect of [0.6, 1.33, 2.4]) {
    const f = frameBounds(scene.bounds, 50, aspect, view);
    for (const e of scene.elements) if (e.type === "wall") for (let i = 0; i < e.positions.length; i += 3) {
      const s = project(f, [e.positions[i]!, e.positions[i + 1]!, e.positions[i + 2]!], 1000 * aspect, 1000);
      assert.ok(s && s.x >= 0 && s.x <= 1000 * aspect && s.y >= 0 && s.y <= 1000, `${view}@${aspect}: vertex on screen`);
    }
  }
  near(clamp(5, 0, 3), 3);
});

test("orthographic: no perspective convergence, exact round-trip, plan framing and picking", () => {
  const scene = buildScene(meshFor(sampleProject(), 1));
  const plan = frameBounds(scene.bounds, 50, W / H, "plan");
  assert.equal(plan.pitch, Math.PI / 2); assert.ok(plan.orthoHalfHeight! > 0);
  const b = basis(plan);
  near(b.forward[2], -1); near(b.up[1], 1); near(b.right[0], 1);                    // looking down, +Y up the screen, +X right
  // equal-size ground segments at different heights project to equal screen lengths (parallel projection)
  const len = (z: number): number => { const p = project(plan, [0, 0, z], W, H)!, q = project(plan, [5, 0, z], W, H)!; return Math.hypot(q.x - p.x, q.y - p.y); };
  near(len(0), len(3), 1e-6);
  for (const p of [[1, 2, 0.5], [-3, 1, 2], [9, 7, 3]] as Vec3[]) {
    const s = project(plan, p, W, H)!, r = rayFromPixel(plan, s.x, s.y, W, H);
    const t = (p[0] - r.origin[0]) * r.dir[0] + (p[1] - r.origin[1]) * r.dir[1] + (p[2] - r.origin[2]) * r.dir[2];
    near(Math.hypot(r.origin[0] + r.dir[0] * t - p[0], r.origin[1] + r.dir[1] * t - p[1], r.origin[2] + r.dir[2] * t - p[2]), 0, 1e-6);
  }
  for (const e of scene.elements) if (e.type === "wall") for (let i = 0; i < e.positions.length; i += 3) {   // everything fits on screen
    const s = project(plan, [e.positions[i]!, e.positions[i + 1]!, e.positions[i + 2]!], W, H)!; assert.ok(s.x >= 0 && s.x <= W && s.y >= 0 && s.y <= H);
  }
  const s = project(plan, [16, 0.1, 3], W, H)!;                                        // top face of fixture cube "w2" (x 11..21, y 0..0.23)
  assert.equal(pickElement(scene, plan, s.x, s.y, W, H)!.id, "w2");
  const left = project(plan, [0, 0, 0], W, H)!, right = project(plan, [10, 0, 0], W, H)!, top = project(plan, [0, 8, 0], W, H)!;
  assert.ok(right.x > left.x && top.y < left.y, "x grows right, y grows up");
  assert.equal(zoom(plan, 0.5, 0.1, 1000).orthoHalfHeight, plan.orthoHalfHeight! * 0.5);
  const o = orbit(plan, 0.1, -0.2); assert.equal(o.orthoHalfHeight, undefined); assert.ok(o.distance > 0 && project(o, scene.bounds.center, W, H));
});
