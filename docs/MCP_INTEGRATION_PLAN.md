# MCP Integration Plan (Phase 8)
The tool layer is the MCP seam: `TOOLS` already maps 1:1 to MCP tool definitions (name, args, read/write). MCP server will expose these (plus `export_*`, `render_scene`, `retrieve_project_memory` as they exist); MCP client connects to external servers via a connection manager.
**Already true:** permissions per call, reversible writes, structured errors, unknown tools rejected.
**To build:** JSON-Schema per tool, auth tokens, per-project grants, execution log, status UI. Antigravity / Claude Code / Codex: verify each one's current MCP support before building adapters; use a local bridge where unsupported.
