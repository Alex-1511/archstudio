# Tech Stack and Decisions
| Layer | Choice | Reason | Status |
|---|---|---|---|
| Model core, AI orchestration, services | Python 3.12 | Mandated; IfcOpenShell/OCCT/Gemini/Qdrant ecosystem | **Core built, stdlib only** |
| Web + desktop UI | TypeScript, React, Next.js, Three.js | Mandated; shared design system | Planned (Phase 1) |
| Desktop shell | Tauri 2 (Rust) | Small, secure FS access, native updater | Planned; Rust not installed in build env |
| Geometry kernel | **Integrate Open CASCADE** (via pythonocc/C++ wrapper) | Policy: do not write a CAD kernel from scratch | Planned (Phase 2) |
| BIM/IFC | IfcOpenShell | Mature OpenBIM | Planned (Phase 4) |
| Revit / AutoCAD | C# add-ins | Official APIs are .NET only | Phase 7; needs Windows + licences |
| Rhino | RhinoCommon / rhino3dm / Rhino.Compute | Official | Phase 7 |
| Blender/SketchUp | Python / Ruby APIs | Official | Phase 7 |
| DB / cache / vectors | PostgreSQL, Redis, Qdrant | Mandated direction; hybrid retrieval | Phase 1/5 |
| API framework | FastAPI | Typed contracts (OpenAPI) between TS and Py | Phase 1 (not installable offline here) |
| Primary LLM | Gemini behind `LLMProvider` | Mandated; abstraction allows others | Client written, **untested** (no key/network) |
**Language policy:** TS + Python first. C++ only when profiling shows a kernel/render hotspot. C# only for Revit/AutoCAD. Rust only for the desktop shell/native services. Cross-language contracts: OpenAPI + JSON Schema generated from the Project schema (`schema_version` already in files).
**Why stdlib-only core now:** the build sandbox has no network/package access, and a dependency-free core is portable into FastAPI, Tauri sidecars and tests unchanged.
