// Framework-agnostic state container (useSyncExternalStore-compatible). All network operations are
// serialised, failed edits never change state, and revision conflicts trigger a reload.
import { ApiError } from "./client.ts";
import type { ApiLike } from "./client.ts";
import { buildEdit, deleteCommand } from "./inspector.ts";
import { parseProject } from "./parse.ts";
import { reconcile, selectElement } from "./selection.ts";
import { buildScene } from "./scene.ts";
import type { Scene } from "./scene.ts";
import type { ApiState, Project } from "./types.ts";

export interface StoreState {
  readonly project: Project | null; readonly revision: number | null; readonly scene: Scene | null;
  readonly selection: readonly string[]; readonly activeLevelId: string | null;
  readonly error: string | null; readonly pending: number;
}

const INITIAL: StoreState = { project: null, revision: null, scene: null, selection: [], activeLevelId: null, error: null, pending: 0 };

export class Store {
  private state: StoreState = INITIAL;
  private readonly listeners = new Set<() => void>();
  private tail: Promise<unknown> = Promise.resolve();
  private readonly api: ApiLike;

  constructor(api: ApiLike) { this.api = api; }

  getState = (): StoreState => this.state;
  subscribe = (fn: () => void): (() => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };

  private set(patch: Partial<StoreState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of [...this.listeners]) l();
  }

  /** Serialise operations so two edits can never interleave their request/response pairs. */
  private enqueue<T>(fn: () => Promise<T>): Promise<T> {
    this.set({ pending: this.state.pending + 1 });
    const run = this.tail.then(fn, fn);
    this.tail = run.then(() => undefined, () => undefined);
    return run.finally(() => this.set({ pending: this.state.pending - 1 }));
  }

  private async adopt(st: ApiState): Promise<void> {
    let state = st;
    let mesh = await this.api.getMesh();
    if (mesh.revision !== state.revision) { // someone edited between the two reads: take a consistent pair
      state = await this.api.getProject();
      mesh = await this.api.getMesh();
    }
    const active = this.state.activeLevelId && state.project.levels.some((l) => l.id === this.state.activeLevelId) ? this.state.activeLevelId : (state.project.levels[0]?.id ?? null);
    this.set({ project: state.project, revision: state.revision, scene: buildScene(mesh), selection: reconcile(this.state.selection, state.project), activeLevelId: active, error: null });
  }

  private fail(e: unknown): false {
    this.set({ error: e instanceof ApiError ? `${e.message} (${e.code})` : e instanceof Error ? e.message : String(e) });
    return false;
  }

  private async guarded(fn: () => Promise<void>): Promise<boolean> {
    try { await fn(); return true; } catch (e) {
      if (e instanceof ApiError && e.code === "revision_conflict") {
        try { await this.adopt(await this.api.getProject()); } catch { /* keep the conflict message below */ }
        this.set({ error: "The project changed elsewhere; your edit was not applied and the view was reloaded." });
        return false;
      }
      return this.fail(e);
    }
  }

  load(): Promise<boolean> { return this.enqueue(() => this.guarded(async () => this.adopt(await this.api.getProject()))); }

  importProject(raw: unknown): Promise<boolean> {
    return this.enqueue(() => this.guarded(async () => {
      this.set({ selection: [] });
      await this.adopt(await this.api.putProject(parseProject(raw)));
    }));
  }

  edit(id: string, key: string, raw: string): Promise<boolean> {
    return this.enqueue(() => this.guarded(async () => {
      const project = this.state.project;
      if (!project || this.state.revision === null) throw new Error("no project loaded");
      const cmd = buildEdit(project, id, key, raw);
      if (!cmd.ok) throw new Error(cmd.error);       // local rejection: no network call, no state change
      if (cmd.noop) return;
      await this.adopt(await this.api.callTool(cmd.tool, cmd.args, this.state.revision));
    }));
  }

  remove(id: string): Promise<boolean> {
    return this.enqueue(() => this.guarded(async () => {
      const project = this.state.project;
      if (!project || this.state.revision === null) throw new Error("no project loaded");
      const cmd = deleteCommand(project, id);
      if (!cmd) throw new Error("this element cannot be deleted");
      await this.adopt(await this.api.callTool(cmd.tool, cmd.args, this.state.revision));
    }));
  }

  undo(): Promise<boolean> { return this.enqueue(() => this.guarded(async () => this.adopt(await this.api.undo(this.state.revision ?? undefined)))); }
  redo(): Promise<boolean> { return this.enqueue(() => this.guarded(async () => this.adopt(await this.api.redo(this.state.revision ?? undefined)))); }

  select(id: string, additive = false): void { this.set({ selection: selectElement(this.state.selection, id, additive) }); }
  clearSelection(): void { if (this.state.selection.length) this.set({ selection: [] }); }
  setActiveLevel(id: string): void { this.set({ activeLevelId: id }); }
  reportError(message: string): void { this.set({ error: message }); }
  dismissError(): void { if (this.state.error) this.set({ error: null }); }
}
