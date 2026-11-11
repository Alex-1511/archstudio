# Product Architecture
One product, one project model. Every module (Floor Plan, CAD, BIM, Facade, Render, AI) reads and writes the **same Project model** through the **same command/tool layer**. No module owns private geometry.

```
UI (TS: web + Tauri)  ──┐
AI agents (Py)        ──┼─> Tool layer (validated, permissioned, undoable) ─> Project model ─> exporters / renderers
MCP external agents   ──┘                                                        │
                                                          geometry kernel (OCCT, later) · IfcOpenShell · persistence
```
**Separation of concerns (prompt §2.12):** AI reasoning chooses tools and arguments → geometry is computed by deterministic code → rendering consumes model data → file conversion is isolated in exporters.
**Invariants (enforced in code today):** user-supplied dimensions are stored exactly; all mutations are atomic and undoable; files are checksummed; exporters declare fidelity; unimplemented formats are reported as `not_implemented`.
**Audiences:** student (guided defaults, explanations), professional (precision input, shortcuts), firm (permissions, versions, collaboration).
