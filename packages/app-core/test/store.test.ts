import test from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../src/client.ts";
import type { ApiLike } from "../src/client.ts";
import { Store } from "../src/store.ts";
import type { ApiState, MeshData, Project } from "../src/types.ts";
import { meshFor, sampleProject, stateOf } from "./fixtures.ts";

/** In-memory stand-in for the server: supports modify_wall(thickness) + delete_wall, revisions, undo. */
class FakeApi implements ApiLike {
  project: Project = sampleProject();
  revision = 1;
  calls: string[] = [];
  nextError: ApiError | null = null;
  inFlight = 0; maxInFlight = 0;
  private past: Project[] = [];

  private async tick(): Promise<void> { this.inFlight++; this.maxInFlight = Math.max(this.maxInFlight, this.inFlight); await new Promise((r) => setTimeout(r, 3)); this.inFlight--; }
  async getProject(): Promise<ApiState> { this.calls.push("getProject"); await this.tick(); return stateOf(this.project, this.revision); }
  async putProject(p: unknown): Promise<ApiState> { this.calls.push("putProject"); this.project = p as Project; this.revision++; return stateOf(this.project, this.revision); }
  async getMesh(): Promise<MeshData> { this.calls.push("getMesh"); await this.tick(); return meshFor(this.project, this.revision); }
  async callTool(name: string, args: Record<string, unknown>, expected?: number): Promise<ApiState> {
    this.calls.push(`${name}@${expected}`); await this.tick();
    if (this.nextError) { const e = this.nextError; this.nextError = null; throw e; }
    if (expected !== undefined && expected !== this.revision) throw new ApiError(409, "revision_conflict", "stale");
    this.past.push(this.project);
    if (name === "modify_wall") this.project = { ...this.project, walls: this.project.walls.map((w) => (w.id === args.wall_id ? { ...w, ...(args as object) } : w)) };
    else if (name === "delete_wall") this.project = { ...this.project, walls: this.project.walls.filter((w) => w.id !== args.wall_id) };
    this.revision++;
    return stateOf(this.project, this.revision);
  }
  async undo(expected?: number): Promise<ApiState> { this.calls.push(`undo@${expected}`); this.project = this.past.pop() ?? this.project; this.revision++; return stateOf(this.project, this.revision); }
  async redo(): Promise<ApiState> { throw new Error("unused"); }
}

const loaded = async (): Promise<{ api: FakeApi; store: Store }> => { const api = new FakeApi(); const store = new Store(api); assert.equal(await store.load(), true); return { api, store }; };
const thick = (s: Store, id = "w1"): number => s.getState().project!.walls.find((w) => w.id === id)!.thickness;

test("load populates project, scene, revision and active level", async () => {
  const { store } = await loaded();
  const s = store.getState();
  assert.equal(s.revision, 1); assert.equal(s.activeLevelId, "lvl-1"); assert.equal(s.scene!.elements.length, 3); assert.equal(s.error, null); assert.equal(s.pending, 0);
});

test("valid edit sends the right call with the current revision and updates state", async () => {
  const { api, store } = await loaded();
  assert.equal(await store.edit("w1", "thickness", "0.3"), true);
  assert.ok(api.calls.includes("modify_wall@1"));
  assert.equal(thick(store), 0.3); assert.equal(store.getState().revision, 2);
});

test("invalid local input: no network call, state untouched, error shown, dismissible", async () => {
  const { api, store } = await loaded();
  const before = store.getState().project, n = api.calls.length;
  for (const raw of ["", "abc", "-1", "NaN"]) assert.equal(await store.edit("w1", "thickness", raw), false);
  assert.equal(api.calls.length, n); assert.equal(store.getState().project, before); assert.ok(store.getState().error);
  store.dismissError(); assert.equal(store.getState().error, null);
});

test("no-op edit makes no call", async () => {
  const { api, store } = await loaded(); const n = api.calls.length;
  assert.equal(await store.edit("w1", "thickness", "0.23"), true); assert.equal(api.calls.length, n);
});

test("server rejection leaves state identical and surfaces the engine message", async () => {
  const { api, store } = await loaded(); const before = store.getState().project;
  api.nextError = new ApiError(400, "invalid", "modify_wall: new height would cut through an existing opening");
  assert.equal(await store.edit("w1", "height", "1"), false);
  assert.equal(store.getState().project, before); assert.match(store.getState().error!, /cut through.*invalid/);
});

test("revision conflict reloads the server state and reports it", async () => {
  const { api, store } = await loaded();
  api.project = { ...api.project, walls: api.project.walls.map((w) => (w.id === "w1" ? { ...w, thickness: 0.5 } : w)) }; api.revision = 9; // changed elsewhere
  assert.equal(await store.edit("w1", "thickness", "0.3"), false);
  assert.equal(thick(store), 0.5); assert.equal(store.getState().revision, 9); assert.match(store.getState().error!, /changed elsewhere/);
});

test("operations are serialised: no overlapping requests, each uses the latest revision", async () => {
  const { api, store } = await loaded(); api.maxInFlight = 0;
  const results = await Promise.all([store.edit("w1", "thickness", "0.31"), store.edit("w1", "thickness", "0.32"), store.edit("w2", "thickness", "0.4")]);
  assert.deepEqual(results, [true, true, true]); assert.equal(api.maxInFlight, 1);
  assert.deepEqual(api.calls.filter((c) => c.startsWith("modify_wall")), ["modify_wall@1", "modify_wall@2", "modify_wall@3"]);
  assert.equal(thick(store), 0.32); assert.equal(thick(store, "w2"), 0.4);
});

test("delete drops the selection of vanished elements; undo restores", async () => {
  const { store } = await loaded();
  store.select("w2"); store.select("w1", true);
  assert.deepEqual(store.getState().selection, ["w2", "w1"]);
  assert.equal(await store.remove("w2"), true);
  assert.deepEqual(store.getState().selection, ["w1"]);
  assert.equal(await store.undo(), true);
  assert.equal(store.getState().project!.walls.length, 2);
  assert.equal(await store.remove("lvl-1"), false);
});

test("malformed import is rejected before any network call", async () => {
  const { api, store } = await loaded(); const n = api.calls.length;
  assert.equal(await store.importProject({ name: "x" }), false); assert.equal(api.calls.length, n); assert.ok(store.getState().error);
});

test("subscribers are notified and can unsubscribe", async () => {
  const { store } = await loaded(); let n = 0; const off = store.subscribe(() => { n++; });
  store.select("w1"); assert.ok(n > 0); const seen = n; off(); store.select("w2"); assert.equal(n, seen);
});

test("network failure becomes a readable error", async () => {
  const api = new FakeApi(); api.getProject = async () => { throw new ApiError(0, "network", "cannot reach API: ECONNREFUSED"); };
  const store = new Store(api); assert.equal(await store.load(), false); assert.match(store.getState().error!, /cannot reach API/);
});
