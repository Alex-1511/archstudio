# API Contract v1
Machine-readable source of truth: `contracts/api.v1.schema.json`. Python tests validate live responses against it (`tests/test_api.py`, `tests/schema_check.py`); the TypeScript client re-checks every response with runtime guards (`packages/app-core/src/parse.ts`) because static types are not evidence; the cross-language test (`packages/app-core/test/integration.test.ts`) runs the real client against the real server.

| Method & path | Purpose | Notes |
|---|---|---|
| GET `/api/v1/health` | liveness + revision | |
| GET/PUT `/api/v1/project` | read / replace (import) | PUT body `{"project": …}`; strict validation, 400 on any violation, state unchanged |
| GET `/api/v1/mesh[?level=id]` | engine-computed render data | per element: `positions`, `indices`; walls (merged pieces) and opening proxies. The viewport draws, it never computes building geometry |
| GET `/api/v1/tools` | tool catalogue | name, write flag, required/optional args |
| POST `/api/v1/tools/{name}` | run a tool | body `{"args": {…}, "expected_revision"?: n}`; atomic, undoable; 409 `revision_conflict` if stale |
| POST `/api/v1/undo` / `/redo` | history | optional `expected_revision` |
| GET `/api/v1/export/{dxf\|obj}?level=id` | download | only implemented formats; others 404 |
| GET `/api/v1/capabilities` | export fidelity table | |
Tools: create_level, create_wall, add_opening, create_room, modify_level / wall / opening / room, delete_wall, delete_opening, calculate_room_area, inspect_project. Each has a strict argument schema (`archcore/tools.py`).
**Errors:** `{"ok": false, "error": {"code", "message"}}`. Codes: unauthorized 401, bad_host 403, not_found 404, revision_conflict 409, too_large 413, unsupported_media_type 415, invalid / bad_json / bad_request 400, internal 500 (never leaks details).
**Security (implemented, tested):** loopback bind; bearer token on every `/api` request; Host header must be loopback (DNS-rebinding defence); CORS limited to one configured origin; JSON only; 5 MB body cap checked before reading; strict CSP on served pages (no inline script/style, `frame-ancestors 'none'`); static serving is allow-listed by extension with traversal/symlink escapes refused; token travels in the URL *fragment* and is removed from the address bar.
**Known limits:** one in-memory project per server process; single shared token (no users/roles); no persistence service yet; whole-project payloads on every write (fine for now, needs deltas at scale); `revision` is per-process.
