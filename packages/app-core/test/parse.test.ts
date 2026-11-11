import test from "node:test";
import assert from "node:assert/strict";
import { ProtocolError, parseMesh, parseProject, parseState } from "../src/parse.ts";
import { meshFor, sampleProject, wire } from "./fixtures.ts";

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

test("valid project and state parse", () => {
  assert.equal(parseProject(clone(sampleProject())).walls.length, 2);
  const st = parseState({ ok: true, revision: 3, project: sampleProject(), result: { id: "x" }, label: "undo" });
  assert.deepEqual([st.revision, st.label, st.result], [3, "undo", { id: "x" }]);
});

test("malformed projects are rejected with a path, never half-parsed", () => {
  const mutations: Record<string, (p: any) => void> = {
    "wall thickness string": (p) => { p.walls[0].thickness = "0.2"; },
    "wall thickness null": (p) => { p.walls[0].thickness = null; },
    "missing level name": (p) => { delete p.levels[0].name; },
    "bad point": (p) => { p.walls[0].start = [1]; },
    "bad opening kind": (p) => { p.walls[0].openings[0].kind = "hatch"; },
    "bad units": (p) => { p.units = "furlongs"; },
    "walls not array": (p) => { p.walls = {}; },
    "room target string": (p) => { p.rooms[0].target_area = "80"; },
  };
  for (const [label, m] of Object.entries(mutations)) {
    const p = clone(sampleProject()); m(p);
    assert.throws(() => parseProject(p), ProtocolError, label);
  }
  for (const junk of [null, 5, "x", [], undefined]) assert.throws(() => parseProject(junk), ProtocolError);
});

test("non-finite numbers cannot sneak through", () => {
  const p: any = clone(sampleProject()); p.walls[0].height = Number.NaN;
  assert.throws(() => parseProject(p), ProtocolError);
  p.walls[0].height = Infinity;
  assert.throws(() => parseProject(p), ProtocolError);
});

test("mesh guards", () => {
  assert.equal(parseMesh(wire(meshFor(sampleProject(), 1))).elements.length, 3);
  const m: any = wire(meshFor(sampleProject(), 1));
  m.elements[0].positions.pop(); assert.throws(() => parseMesh(m), ProtocolError, "positions not multiple of 3");
  const m2: any = wire(meshFor(sampleProject(), 1)); m2.elements[0].type = "roof";
  assert.throws(() => parseMesh(m2), ProtocolError);
  assert.throws(() => parseState({ revision: 1.5, project: sampleProject() }), ProtocolError);
  const m3: any = wire(meshFor(sampleProject(), 1)); m3.elements[0].wall_id = null;
  assert.throws(() => parseMesh(m3), ProtocolError, "null wall_id violates the contract");
});
