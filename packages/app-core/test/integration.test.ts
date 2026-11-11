// Cross-language contract test: real Python server (services/core/run_server.py) <-> real TypeScript client + store.
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { fileURLToPath } from "node:url";
import { ApiClient, ApiError } from "../src/client.ts";
import { Store } from "../src/store.ts";
import type { Scene } from "../src/scene.ts";
import type { Project } from "../src/types.ts";

const SERVER = fileURLToPath(new URL("../../../services/core/run_server.py", import.meta.url));
const TOKEN = "itest-token";
let proc: ChildProcessWithoutNullStreams;
let base = "";

before(async () => {
  proc = spawn("python3", [SERVER, "--port", "0"], { env: { ...process.env, ARCH_API_TOKEN: TOKEN } });
  base = await new Promise<string>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("server did not start")), 10000);
    let buf = "";
    proc.stdout.on("data", (d: Buffer) => {
      buf += d.toString();
      const line = buf.split("\n")[0];
      if (buf.includes("\n") && line) { clearTimeout(t); resolve(`http://127.0.0.1:${(JSON.parse(line) as { port: number }).port}`); }
    });
    proc.on("exit", (c) => reject(new Error(`server exited early (${c})`)));
  });
});
after(() => { proc.kill(); });

/** Independent of the engine: volume of triangle meshes via the divergence theorem. */
function wallVolume(scene: Scene): number {
  let v = 0;
  for (const el of scene.elements) {
    if (el.type !== "wall") continue;
    const p = el.positions, ix = el.indices;
    for (let i = 0; i < ix.length; i += 3) {
      const a = (ix[i] as number) * 3, b = (ix[i + 1] as number) * 3, c = (ix[i + 2] as number) * 3;
      const [x1, y1, z1, x2, y2, z2, x3, y3, z3] = [p[a], p[a + 1], p[a + 2], p[b], p[b + 1], p[b + 2], p[c], p[c + 1], p[c + 2]] as number[] as [number, number, number, number, number, number, number, number, number];
      v += (x1 * (y2 * z3 - z2 * y3) - y1 * (x2 * z3 - z2 * x3) + z1 * (x2 * y3 - y2 * x3)) / 6;
    }
  }
  return v;
}
/** Quantity formula computed here from the parsed project (not by the engine). */
function expectedVolume(p: Project): number {
  return p.walls.reduce((s, w) => s + (Math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1]) * w.height - w.openings.reduce((a, o) => a + o.width * o.height, 0)) * w.thickness, 0);
}
const close = (a: number, b: number, msg: string): void => assert.ok(Math.abs(a - b) < 1e-3 * Math.max(1, Math.abs(b)), `${msg}: ${a} vs ${b}`);

let api: ApiClient; let store: Store; let ids: { level: string; walls: string[]; door: string; window: string };

test("auth and network failures map to ApiError codes", async () => {
  api = new ApiClient(base, TOKEN);
  const wrong = new ApiClient(base, "nope");
  await assert.rejects(() => wrong.getProject(), (e: unknown) => e instanceof ApiError && e.status === 401 && e.code === "unauthorized");
  const dead = new ApiClient("http://127.0.0.1:1", TOKEN);
  await assert.rejects(() => dead.getProject(), (e: unknown) => e instanceof ApiError && e.code === "network");
  assert.ok((await api.tools()).some((t) => t.name === "modify_wall" && t.write));
});

test("build a project through the tool API and load it into the store", async () => {
  const lvl = (await api.callTool("create_level", { name: "Ground", elevation: 0, height: 3 })).result!.id as string;
  const pts: [number, number][] = [[0, 0], [10, 0], [10, 8], [0, 8]];
  const walls: string[] = [];
  for (let i = 0; i < 4; i++) walls.push((await api.callTool("create_wall", { level_id: lvl, start: pts[i], end: pts[(i + 1) % 4], thickness: 0.23, material: "brick" })).result!.id as string);
  const door = (await api.callTool("add_opening", { wall_id: walls[0], kind: "door", offset: 1, width: 0.9, height: 2.1 })).result!.id as string;
  const win = (await api.callTool("add_opening", { wall_id: walls[1], kind: "window", offset: 2, width: 1.5, height: 1.2, sill: 0.9 })).result!.id as string;
  await api.callTool("create_room", { name: "Living", level_id: lvl, boundary: pts, target_area: 80 });
  ids = { level: lvl, walls, door, window: win };

  store = new Store(api);
  assert.equal(await store.load(), true, store.getState().error ?? "");
  const s = store.getState();
  assert.equal(s.scene!.elements.filter((e) => e.type === "wall").length, 4);
  assert.equal(s.scene!.elements.filter((e) => e.type === "opening").length, 2);
  close(wallVolume(s.scene!), expectedVolume(s.project!), "engine mesh volume vs independently computed quantity");
  assert.equal(s.activeLevelId, lvl);
});

test("selecting and editing a wall through the store changes engine geometry", async () => {
  const w0 = ids.walls[0] as string;
  store.select(w0);
  const v0 = wallVolume(store.getState().scene!), r0 = store.getState().revision!;
  assert.equal(await store.edit(w0, "thickness", "0.3"), true, store.getState().error ?? "");
  const s = store.getState();
  assert.equal(s.revision, r0 + 1);
  assert.equal(s.project!.walls.find((w) => w.id === w0)!.thickness, 0.3);
  close(wallVolume(s.scene!), expectedVolume(s.project!), "after edit");
  assert.ok(wallVolume(s.scene!) > v0);
  assert.deepEqual(s.selection, [w0], "selection survives an edit");
});

test("local rejection never reaches the server; engine rejection leaves state unchanged", async () => {
  const w0 = ids.walls[0] as string;
  const r = store.getState().revision;
  assert.equal(await store.edit(w0, "thickness", "-1"), false);
  assert.equal(store.getState().revision, r);
  const before = store.getState().project;
  assert.equal(await store.edit(ids.window, "width", "50"), false);          // locally valid, engine says it exceeds the wall
  assert.match(store.getState().error!, /exceeds wall length/);
  assert.equal(store.getState().project, before, "state object untouched");
  assert.equal(await store.edit(ids.walls[1] as string, "height", "1"), false); // would cut through the window
  assert.match(store.getState().error!, /cut through|exceeds wall height/);
  assert.equal((await api.getProject()).revision, r, "server revision unchanged by rejected edits");
});

test("undo / redo round-trips through the engine", async () => {
  const w0 = ids.walls[0] as string;
  assert.equal(await store.undo(), true);
  assert.equal(store.getState().project!.walls.find((w) => w.id === w0)!.thickness, 0.23);
  close(wallVolume(store.getState().scene!), expectedVolume(store.getState().project!), "after undo");
  assert.equal(await store.redo(), true);
  assert.equal(store.getState().project!.walls.find((w) => w.id === w0)!.thickness, 0.3);
});

test("a concurrent edit by another client yields a conflict, a reload and no lost update", async () => {
  const w0 = ids.walls[0] as string;
  const other = new ApiClient(base, TOKEN);
  await other.callTool("modify_wall", { wall_id: w0, thickness: 0.5 });
  assert.equal(await store.edit(w0, "thickness", "0.4"), false);
  assert.match(store.getState().error!, /changed elsewhere/);
  assert.equal(store.getState().project!.walls.find((w) => w.id === w0)!.thickness, 0.5, "view reloaded to the other client's value");
  assert.equal(await store.edit(w0, "thickness", "0.4"), true, "retry on fresh revision succeeds");
});

test("delete opening / undo changes the scene and keeps selection consistent", async () => {
  store.select(ids.door);
  assert.equal(await store.remove(ids.door), true);
  assert.equal(store.getState().scene!.elements.some((e) => e.id === ids.door), false);
  assert.deepEqual(store.getState().selection, []);
  assert.equal(await store.undo(), true);
  assert.equal(store.getState().scene!.elements.some((e) => e.id === ids.door), true);
});

test("import: engine-invalid project is rejected and state is kept; valid project replaces it", async () => {
  const cur = store.getState().project!;
  const bad: Project = { ...cur, walls: cur.walls.map((w, i) => (i === 0 ? { ...w, thickness: -1 } : w)) }; // passes TS guards, fails engine invariants
  const before = store.getState().project;
  assert.equal(await store.importProject(bad), false);
  assert.match(store.getState().error!, /thickness must be positive/);
  assert.equal(store.getState().project, before);
  const good: Project = { name: "Imported", units: "m", levels: [{ id: "L", name: "L1", elevation: 0, height: 3 }], walls: [{ id: "W", level_id: "L", start: [0, 0], end: [4, 0], thickness: 0.2, height: 3, material: "concrete", properties: {}, openings: [] }], rooms: [] };
  store.select(ids.walls[0] as string);
  assert.equal(await store.importProject(good), true, store.getState().error ?? "");
  const s = store.getState();
  assert.equal(s.project!.name, "Imported"); assert.deepEqual(s.selection, []); assert.equal(s.scene!.elements.length, 1);
  close(wallVolume(s.scene!), 4 * 3 * 0.2, "imported wall volume");
});

test("exports are served only for implemented formats", async () => {
  const dxf = await api.exportText("dxf", "L");
  assert.ok(dxf.includes("A-WALL") && dxf.trimEnd().endsWith("EOF"));
  assert.ok((await api.exportText("obj", "L")).includes("\nf "));
  await assert.rejects(() => api.exportText("dxf", "ghost"), (e: unknown) => e instanceof ApiError && e.status === 404);
});
