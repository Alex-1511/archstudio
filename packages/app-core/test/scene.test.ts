import test from "node:test";
import assert from "node:assert/strict";
import { buildScene, fitCamera } from "../src/scene.ts";
import { meshFor, sampleProject } from "./fixtures.ts";

test("scene buffers and bounds exclude opening proxies from framing", () => {
  const s = buildScene(meshFor(sampleProject(), 7));
  assert.equal(s.revision, 7);
  assert.equal(s.elements.length, 3);
  assert.ok(s.elements[0]!.positions instanceof Float32Array && s.elements[0]!.indices instanceof Uint32Array);
  assert.deepEqual([s.bounds.min[0], s.bounds.max[0]], [0, 21]);       // two 10 m walls placed 11 m apart
  assert.deepEqual([s.bounds.min[2], s.bounds.max[2]], [0, 3]);
  assert.ok(s.bounds.radius > 10);
});

test("out-of-range index and duplicate ids are rejected", () => {
  const m = meshFor(sampleProject(), 1);
  const bad = { ...m, elements: [{ ...m.elements[0]!, indices: [0, 1, 99] }] };
  assert.throws(() => buildScene(bad), /out of range/);
  assert.throws(() => buildScene({ ...m, elements: [m.elements[0]!, m.elements[0]!] }), /duplicate/);
});

test("empty scene has safe bounds; camera fits the bounds", () => {
  const empty = buildScene({ revision: 0, units: "m", elements: [] });
  assert.equal(empty.bounds.radius, 1);
  const s = buildScene(meshFor(sampleProject(), 1));
  for (const aspect of [0.5, 1, 2]) {
    const cam = fitCamera(s.bounds, 50, aspect);
    const d = Math.hypot(cam.position[0] - cam.target[0], cam.position[1] - cam.target[1], cam.position[2] - cam.target[2]);
    assert.ok(d > s.bounds.radius, `camera outside the bounding sphere at aspect ${aspect}`);
    assert.ok(cam.position.every(Number.isFinite));
  }
});
