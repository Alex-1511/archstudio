import test from "node:test";
import assert from "node:assert/strict";
import { buildEdit, deleteCommand, inspectorFor, parseNumberStrict } from "../src/inspector.ts";
import { sampleProject } from "./fixtures.ts";

test("strict number parsing", () => {
  for (const ok of ["0.25", " 3 ", "-1", "+2", ".5", "5.", "1e-3", "2E2"]) assert.notEqual(parseNumberStrict(ok), null, ok);
  for (const bad of ["", " ", "NaN", "Infinity", "-Infinity", "0x10", "1,5", "1_000", "0.2m", "1e400", "1e10", "--1", "1 2", "١٢"]) assert.equal(parseNumberStrict(bad), null, JSON.stringify(bad));
  assert.equal(parseNumberStrict("0.25"), 0.25);
});

test("inspector exposes editable and read-only fields per element type", () => {
  const p = sampleProject();
  const wall = inspectorFor(p, "w1")!;
  assert.equal(wall.title, "Wall"); assert.equal(wall.deletable, true);
  const byKey = Object.fromEntries(wall.fields.map((f) => [f.key, f]));
  assert.deepEqual([byKey.thickness!.value, byKey.thickness!.unit, byKey.thickness!.kind], ["0.23", "m", "number"]);
  assert.deepEqual([byKey.length!.value, byKey.length!.kind], ["10", "readonly"]);
  assert.equal(byKey.level!.value, "Ground");
  const door = inspectorFor(p, "o1")!;
  assert.equal(door.title, "Door"); assert.deepEqual(door.fields.find((f) => f.key === "kind")!.options, ["door", "window"]);
  assert.equal(inspectorFor(p, "r1")!.fields.find((f) => f.key === "area")!.value, "80");
  assert.equal(inspectorFor(p, "lvl-1")!.deletable, false);
  assert.equal(inspectorFor(p, "ghost"), null);
});

test("valid edits become the right tool calls", () => {
  const p = sampleProject();
  assert.deepEqual(buildEdit(p, "w1", "thickness", "0.3"), { ok: true, noop: false, tool: "modify_wall", args: { wall_id: "w1", thickness: 0.3 } });
  assert.deepEqual(buildEdit(p, "w1", "material", "  concrete "), { ok: true, noop: false, tool: "modify_wall", args: { wall_id: "w1", material: "concrete" } });
  assert.deepEqual(buildEdit(p, "o1", "width", "1"), { ok: true, noop: false, tool: "modify_opening", args: { opening_id: "o1", width: 1 } });
  assert.deepEqual(buildEdit(p, "o1", "kind", "window"), { ok: true, noop: false, tool: "modify_opening", args: { opening_id: "o1", kind: "window" } });
  assert.deepEqual(buildEdit(p, "lvl-1", "elevation", "-0.5"), { ok: true, noop: false, tool: "modify_level", args: { level_id: "lvl-1", elevation: -0.5 } });
  assert.deepEqual(buildEdit(p, "r1", "target_area", "75"), { ok: true, noop: false, tool: "modify_room", args: { room_id: "r1", target_area: 75 } });
  assert.deepEqual(buildEdit(p, "w1", "thickness", "0.23"), { ok: true, noop: true });
});

test("invalid edits are rejected locally with a message", () => {
  const p = sampleProject();
  const cases: [string, string, string][] = [
    ["w1", "thickness", ""], ["w1", "thickness", "abc"], ["w1", "thickness", "NaN"], ["w1", "thickness", "-1"], ["w1", "thickness", "0"],
    ["w1", "height", "0x10"], ["w1", "material", "   "], ["o1", "kind", "hatch"], ["o1", "sill", "-0.1"], ["o1", "offset", "-1"],
    ["lvl-1", "height", "0"], ["lvl-1", "elevation", "Infinity"], ["r1", "target_area", "0"],
    ["w1", "length", "5"], ["w1", "id", "x"], ["ghost", "thickness", "1"], ["w1", "nope", "1"],
  ];
  for (const [id, key, raw] of cases) {
    const r = buildEdit(p, id, key, raw);
    assert.equal(r.ok, false, `${id}.${key}=${JSON.stringify(raw)}`);
    if (!r.ok) assert.ok(r.error.length > 5);
  }
  assert.equal(buildEdit(p, "o1", "offset", "0").ok, true, "zero offset is legal");
});

test("delete commands only for walls and openings", () => {
  const p = sampleProject();
  assert.deepEqual(deleteCommand(p, "w2"), { tool: "delete_wall", args: { wall_id: "w2" } });
  assert.deepEqual(deleteCommand(p, "o1"), { tool: "delete_opening", args: { opening_id: "o1" } });
  assert.equal(deleteCommand(p, "lvl-1"), null); assert.equal(deleteCommand(p, "r1"), null); assert.equal(deleteCommand(p, "ghost"), null);
});
