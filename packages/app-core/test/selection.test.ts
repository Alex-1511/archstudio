import test from "node:test";
import assert from "node:assert/strict";
import { hierarchy, reconcile, resolveElement, selectElement } from "../src/selection.ts";
import { sampleProject } from "./fixtures.ts";

test("click replaces, additive toggles, identical click keeps the same array", () => {
  const a = selectElement([], "w1", false);
  assert.deepEqual(a, ["w1"]);
  assert.equal(selectElement(a, "w1", false), a);
  assert.deepEqual(selectElement(a, "w2", true), ["w1", "w2"]);
  assert.deepEqual(selectElement(["w1", "w2"], "w1", true), ["w2"]);
  assert.deepEqual(selectElement(["w1", "w2"], "o1", false), ["o1"]);
});

test("resolve every element kind and unknown ids", () => {
  const p = sampleProject();
  assert.deepEqual(["lvl-1", "w1", "o1", "r1"].map((id) => resolveElement(p, id)?.type), ["level", "wall", "opening", "room"]);
  assert.equal(resolveElement(p, "ghost"), null);
});

test("reconcile drops vanished ids", () => {
  const p = sampleProject();
  assert.deepEqual(reconcile(["w1", "gone", "o1"], p), ["w1", "o1"]);
  const same = ["w1"]; assert.equal(reconcile(same, p), same);
});

test("hierarchy nests level > wall > opening, with rooms", () => {
  const [lvl] = hierarchy(sampleProject());
  assert.equal(lvl!.label, "Ground");
  assert.deepEqual(lvl!.children.map((c) => c.type), ["wall", "wall", "room"]);
  assert.equal(lvl!.children[0]!.children[0]!.label, "Door 0.9 × 2.1");
  assert.match(lvl!.children[0]!.label, /^Wall 10 m · brick$/);
});
