import { parseMesh, parseProject, parseState, parseTools } from "./parse.ts";
import type { ApiState, MeshData, Project, ToolInfo } from "./types.ts";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** What the Store needs. Tests substitute a fake; the real implementation is ApiClient. */
export interface ApiLike {
  getProject(): Promise<ApiState>;
  putProject(project: unknown): Promise<ApiState>;
  getMesh(levelId?: string): Promise<MeshData>;
  callTool(name: string, args: Record<string, unknown>, expectedRevision?: number): Promise<ApiState>;
  undo(expectedRevision?: number): Promise<ApiState>;
  redo(expectedRevision?: number): Promise<ApiState>;
}

export class ApiClient implements ApiLike {
  private readonly base: string;
  private readonly token: string;
  private readonly doFetch: FetchLike;

  constructor(baseUrl: string, token: string, fetchImpl: FetchLike = (u, i) => fetch(u, i)) {
    this.base = baseUrl.replace(/\/+$/, "");
    this.token = token;
    this.doFetch = fetchImpl;
  }

  private async raw(method: string, path: string, body?: unknown): Promise<string> {
    let res: Response;
    try {
      res = await this.doFetch(`${this.base}${path}`, {
        method,
        headers: { Authorization: `Bearer ${this.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
    } catch (e) {
      throw new ApiError(0, "network", `cannot reach API: ${e instanceof Error ? e.message : String(e)}`);
    }
    const text = await res.text();
    if (!res.ok) {
      let code = "http_error";
      let message = `HTTP ${res.status}`;
      try {
        const js: unknown = JSON.parse(text);
        const err = (js as { error?: { code?: unknown; message?: unknown } }).error;
        if (typeof err?.code === "string") code = err.code;
        if (typeof err?.message === "string") message = err.message;
      } catch { /* non-JSON error body: keep defaults */ }
      throw new ApiError(res.status, code, message);
    }
    return text;
  }

  private async json(method: string, path: string, body?: unknown): Promise<unknown> {
    return JSON.parse(await this.raw(method, path, body));
  }

  async getProject(): Promise<ApiState> { return parseState(await this.json("GET", "/api/v1/project")); }
  async putProject(project: unknown): Promise<ApiState> { return parseState(await this.json("PUT", "/api/v1/project", { project })); }
  async getMesh(levelId?: string): Promise<MeshData> {
    return parseMesh(await this.json("GET", `/api/v1/mesh${levelId ? `?level=${encodeURIComponent(levelId)}` : ""}`));
  }
  async callTool(name: string, args: Record<string, unknown>, expectedRevision?: number): Promise<ApiState> {
    return parseState(await this.json("POST", `/api/v1/tools/${encodeURIComponent(name)}`, { args, ...(expectedRevision !== undefined ? { expected_revision: expectedRevision } : {}) }));
  }
  async undo(expectedRevision?: number): Promise<ApiState> { return parseState(await this.json("POST", "/api/v1/undo", expectedRevision !== undefined ? { expected_revision: expectedRevision } : {})); }
  async redo(expectedRevision?: number): Promise<ApiState> { return parseState(await this.json("POST", "/api/v1/redo", expectedRevision !== undefined ? { expected_revision: expectedRevision } : {})); }
  async tools(): Promise<readonly ToolInfo[]> { return parseTools(await this.json("GET", "/api/v1/tools")); }
  async exportText(format: "dxf" | "obj", levelId: string): Promise<string> { return this.raw("GET", `/api/v1/export/${format}?level=${encodeURIComponent(levelId)}`); }
  /** Validates a locally parsed file against the guards before sending (fail fast; the server stays authoritative). */
  static checkProjectShape(x: unknown): Project { return parseProject(x); }
}
