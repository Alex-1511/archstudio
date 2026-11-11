# Feature Completion Matrix  (v0.4.0)
Tests: Python 67 · TypeScript 44 (incl. 9 cross-language integration) · browser E2E 14. Test counts are a safety signal, not a measure of product completeness.
Legend: P planned · I implemented · T tested · R production-ready · B blocked
| Feature | State | Notes / known limits |
|---|---|---|
| 2D geometry helpers | T | metre-scale absolute tolerance `1e-9` |
| Numeric/type validation in the BIM objects themselves (finite, non-bool, never string-coerced, magnitude ≤ 1e9) | T | one set of invariants used by creation, import and every history command; direct mutation inside a command is caught and rolled back; save refuses invalid models |
| Strict import (exact keys, types, referential integrity, duplicate ids, opening bounds/overlap, size cap, NaN literals) | T | a correct checksum no longer implies a valid model; fuzzed over every leaf of a project file (550+ corruptions): always `ValueError` or a model that passes `validate()` |
| Room/polygon validation (self-intersection, spikes, duplicates, zero area, NaN/inf) | T | fixes review #1; concave rooms accepted |
| BIM objects: level, wall, opening, room | T | no wall joins, no roofs/floors/stairs/columns yet |
| Quantities, room schedule | T | per-wall; corner overlaps double-counted until joins exist |
| Save/load: atomic + SHA-256 checksum | T | **corruption detection only, not security** |
| Optional HMAC signature | T | tamper detection needs a secret key; key management is the caller's job (review #3) |
| Undo/redo, atomic rollback, versions, diff | T | **object identity now preserved**, held references stay valid (review #2); diff is data-level, not geometric |
| Tool layer: schemas, permissions, atomic batch with `$N.id` refs | T | strict arg validation, unknown keys rejected |
| AI planner + clarification loop | T (fake model) | still a thin planner, no architectural reasoning, no multimodal input (review #4) |
| Gemini client | I (untested) | B: no key/network in build env |
| 3D mesh foundation (walls → closed oriented triangle boxes, openings cut) | T | volume cross-checked against quantities; **mesh only, not a solid kernel** (review #5, partial) |
| OBJ export | T (re-parsed independently: indices valid, volume = quantities) | mesh-only; **not opened in 3D software** |
| DXF export | T (structure + re-parsed wall extents) | **not opened in a real CAD app**; checklist in `EXPORT_VERIFICATION.md`, results table still empty |
| Open CASCADE kernel (booleans, sweeps, lofts, B-rep) | P | B: needs networked build env |
| IFC / DWG / RVT / 3DM / glTF export | P | |
| HTTP API v1 (contract schema, auth, Host/CORS/body limits, revisions, strict import, static serving with CSP) | T | single in-memory project, single shared token; see API_CONTRACT.md |
| Edit/delete tools: modify_level/wall/opening/room, delete_wall/opening | T | undo restores the same objects |
| TS app-core: client + guards, scene, orthographic/perspective camera, picking, selection, inspector, store | T | 44 tests incl. real-server integration |
| Web client (apps/web-lite): tree, 3D + plan viewport, picking, inspector editing, undo/redo, import/export, shortcuts, dark mode | T (browser) | software renderer; plan is ortho top view without a section cut; no creation tools yet |
| Next.js + Three.js app (apps/web) | I (untested) | never built or run; syntax-checked only; B: needs npm install |
| Desktop app (Tauri), auth/users, cloud persistence | P | |
| Drawing interpretation, Floor Plan Designer, Enhancer, facades, Architect Inspire, RAG, render, MCP, integrations | P | |
