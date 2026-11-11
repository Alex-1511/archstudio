"""HTTP API v1 (stdlib only). Contract: contracts/api.v1.schema.json, docs/API_CONTRACT.md.

Security defaults for a local dev server: binds 127.0.0.1; every request needs a bearer token;
Host header must be loopback (DNS-rebinding defence); CORS limited to one configured origin;
JSON bodies only, capped in size. All writes go through the tool layer (validated, undoable) and
carry optimistic-concurrency revisions. One in-memory project per process: persistence, multi-project
and per-user permissions belong to the later project service."""
from __future__ import annotations
import hmac, json, mimetypes, os, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from .bim import Project
from .history import History
from .tools import TOOLS, SCHEMAS, apply_tool_call, ToolError
from .export import export_capabilities, export_dxf, export_obj
from .solids import wall_pieces, opening_proxy

MAX_BODY = 5 * 1024 * 1024
RW = frozenset({"read", "write"})
LOOPBACK = {"localhost", "127.0.0.1", "[::1]"}
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml", ".ico": "image/x-icon"}
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Session:
    def __init__(self, project: Project | None = None):
        self.lock = threading.RLock()
        self.history = History(project or Project("Untitled"))

    def replace(self, project: Project) -> None:
        self.history = History(project, revision=self.history.revision + 1)


def _flat(verts, tris, positions, indices):
    base = len(positions) // 3
    for v in verts:
        positions.extend(v)
    for t in tris:
        indices.extend(i + base for i in t)


def build_mesh(project: Project, level_id: str | None) -> list[dict]:
    """Per-element render data computed by the engine. Walls (merged pieces) and opening proxies."""
    elements = []
    for w in project.walls.values():
        if level_id and w.level_id != level_id:
            continue
        lv = project.levels[w.level_id]
        pos, idx = [], []
        for p in wall_pieces(w, lv):
            _flat(p["vertices"], p["triangles"], pos, idx)
        elements.append({"id": w.id, "type": "wall", "level_id": w.level_id, "positions": pos, "indices": idx})
        for o in w.openings:
            pos, idx = [], []
            _flat(*opening_proxy(w, lv, o), pos, idx)
            elements.append({"id": o.id, "type": "opening", "level_id": w.level_id, "wall_id": w.id,
                             "kind": o.kind, "positions": pos, "indices": idx})
    return elements


def make_server(host: str = "127.0.0.1", port: int = 0, token: str | None = None,
                allowed_origin: str = "http://localhost:3000", session: Session | None = None,
                static_dir: str | None = None) -> ThreadingHTTPServer:
    token = token or secrets.token_urlsafe(24)
    session = session or Session()
    static_root = os.path.realpath(static_dir) if static_dir else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "ArchStudioAPI/1"

        def log_message(self, *a):  # quiet by default
            pass

        # ------------------------------------------------------------ plumbing
        def _send(self, status: int, body: bytes, ctype: str = "application/json", extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", PAGE_CSP if ctype.startswith("text/html") else "default-src 'none'")
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj, allow_nan=False).encode())

        def _fail(self, e: ApiError):
            self._json(e.status, {"ok": False, "error": {"code": e.code, "message": e.message}})

        def _check_host(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") \
                else (self.headers.get("Host") or "").split("]")[0] + "]"
            if host not in LOOPBACK:
                raise ApiError(403, "bad_host", "Host header must be loopback")

        def _check_auth(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], token):
                raise ApiError(401, "unauthorized", "missing or invalid bearer token")

        def _body(self) -> dict:
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json")
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ApiError(400, "bad_request", "invalid Content-Length")
            if n > MAX_BODY:
                raise ApiError(413, "too_large", f"body exceeds {MAX_BODY} bytes")
            try:
                data = json.loads(self.rfile.read(n) or b"{}", parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
            except ValueError as e:
                raise ApiError(400, "bad_json", f"invalid JSON: {e}")
            if not isinstance(data, dict):
                raise ApiError(400, "bad_request", "body must be a JSON object")
            return data

        def _dispatch(self, method: str):
            try:
                if method == "OPTIONS":  # CORS preflight carries no credentials
                    return self._send(204, b"", "text/plain", {
                        "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Max-Age": "600"})
                self._check_host()
                url = urlparse(self.path)
                if static_root and method == "GET" and not url.path.startswith("/api/"):
                    return self._static(url.path)  # static assets carry no secrets; the API below needs the token
                self._check_auth()
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                with session.lock:
                    self._route(method, url.path, q)
            except ApiError as e:
                self._fail(e)
            except (ToolError, ValueError) as e:
                self._fail(ApiError(400, "invalid", str(e)))
            except Exception as e:  # noqa: BLE001  never leak internals/tracebacks
                self._fail(ApiError(500, "internal", "internal error"))

        def do_GET(self): self._dispatch("GET")
        def do_POST(self): self._dispatch("POST")
        def do_PUT(self): self._dispatch("PUT")
        def do_OPTIONS(self): self._dispatch("OPTIONS")

        def _static(self, raw_path: str):
            rel = unquote(raw_path)
            if rel in ("", "/"):
                rel = "/index.html"
            if "\0" in rel or "\\" in rel or ".." in rel.split("/") or not rel.startswith("/") or rel.startswith("//") or rel.endswith("/"):
                raise ApiError(404, "not_found", "not found")
            full = os.path.realpath(os.path.join(static_root, rel.lstrip("/")))
            ext = os.path.splitext(full)[1].lower()
            if os.path.commonpath([static_root, full]) != static_root or ext not in STATIC_TYPES or not os.path.isfile(full):
                raise ApiError(404, "not_found", "not found")
            with open(full, "rb") as fh:
                self._send(200, fh.read(), STATIC_TYPES[ext])

        # ------------------------------------------------------------ routes
        def _state(self, **extra):
            h = session.history
            return {"ok": True, "revision": h.revision, "project": h.project.to_dict(), **extra}

        def _route(self, method: str, path: str, q: dict):
            h = session.history
            if method == "GET" and path == "/api/v1/health":
                return self._json(200, {"ok": True, "version": "1", "revision": h.revision})
            if method == "GET" and path == "/api/v1/project":
                return self._json(200, self._state())
            if method == "PUT" and path == "/api/v1/project":
                body = self._body()
                if set(body) != {"project"}:
                    raise ApiError(400, "bad_request", 'body must be {"project": {...}}')
                session.replace(Project.from_dict(body["project"]))  # strict: raises ValueError on any violation
                return self._json(200, self._state())
            if method == "GET" and path == "/api/v1/mesh":
                lvl = q.get("level")
                if lvl and lvl not in h.project.levels:
                    raise ApiError(404, "not_found", f"unknown level {lvl}")
                return self._json(200, {"ok": True, "revision": h.revision, "units": h.project.units,
                                        "elements": build_mesh(h.project, lvl)})
            if method == "GET" and path == "/api/v1/tools":
                return self._json(200, {"ok": True, "tools": [
                    {"name": n, "write": TOOLS[n][1], "required": sorted(SCHEMAS[n][0]), "optional": sorted(SCHEMAS[n][1])}
                    for n in TOOLS]})
            if method == "GET" and path == "/api/v1/capabilities":
                return self._json(200, {"ok": True, "exports": export_capabilities()})
            if method == "POST" and path.startswith("/api/v1/tools/"):
                name = unquote(path[len("/api/v1/tools/"):])
                if name not in TOOLS:
                    raise ApiError(404, "not_found", f"unknown tool {name!r}")
                body = self._body()
                if not set(body) <= {"args", "expected_revision"}:
                    raise ApiError(400, "bad_request", "body keys must be 'args' and optionally 'expected_revision'")
                exp = body.get("expected_revision")
                if exp is not None and (isinstance(exp, bool) or not isinstance(exp, int)):
                    raise ApiError(400, "bad_request", "expected_revision must be an integer")
                if exp is not None and exp != h.revision:
                    raise ApiError(409, "revision_conflict", f"project is at revision {h.revision}, request expected {exp}")
                result = apply_tool_call(h, name, body.get("args", {}), RW)
                return self._json(200, self._state(result=result))
            if method == "POST" and path in ("/api/v1/undo", "/api/v1/redo"):
                body = self._body()
                exp = body.get("expected_revision")
                if exp is not None and exp != h.revision:
                    raise ApiError(409, "revision_conflict", f"project is at revision {h.revision}, request expected {exp}")
                label = h.undo() if path.endswith("undo") else h.redo()
                return self._json(200, self._state(label=label))
            if method == "GET" and path.startswith("/api/v1/export/"):
                fmt = path.rsplit("/", 1)[1]
                lvl = q.get("level")
                if fmt not in ("dxf", "obj") or not lvl or lvl not in h.project.levels:
                    raise ApiError(404, "not_found", "export needs format dxf|obj and a valid ?level=")
                text = export_dxf(h.project, lvl) if fmt == "dxf" else export_obj(h.project, lvl)
                return self._send(200, text.encode(), "text/plain; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="level.{fmt}"'})
            raise ApiError(404, "not_found", f"no route {method} {path}")

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.token, srv.session = token, session  # type: ignore[attr-defined]
    return srv
