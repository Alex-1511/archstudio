import { ApiClient, Store, buildScene, frameBounds, hierarchy, inspectorFor, orbit, pickElement, project as projectPoint, zoom } from "../../../packages/app-core/src/index.ts";
import type { Camera, StoreState, TreeNode, Vec3 } from "../../../packages/app-core/src/index.ts";
import { clear, h } from "./dom.ts";
import { draw, readPalette } from "./render.ts";

const root = document.getElementById("app") as HTMLElement;

function takeTokenFromUrl(): string | null {
  const m = /(?:^#|&)token=([^&]+)/.exec(location.hash);
  if (!m) return null;
  history.replaceState(null, "", location.pathname + location.search);   // keep the token out of history/screenshots/referrers
  return decodeURIComponent(m[1] as string);
}

function showConnect(message: string | null): void {
  clear(root);
  const input = h("input", { id: "token", type: "password", autocomplete: "off", "aria-label": "API token" });
  const go = (): void => { if (input.value.trim()) start(input.value.trim()); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  root.append(h("div", { class: "connect" },
    h("h1", null, "ArchStudio"),
    h("p", null, "Paste the API token printed by the server (kept in memory only)."),
    message ? h("p", { role: "alert", class: "empty" }, message) : null,
    h("label", { for: "token", class: "visually-hidden" }, "API token"), input,
    h("button", { type: "button", onclick: go }, "Connect")));
  input.focus();
}

function start(token: string): void {
  const api = new ApiClient(location.origin, token);
  const store = new Store(api);
  clear(root);

  // ---------------------------------------------------------------- skeleton
  const nameEl = h("strong", null, "–");
  const btn = (label: string, onclick: () => void, extra: Record<string, string> = {}): HTMLButtonElement => h("button", { type: "button", onclick, ...extra }, label);
  const undoBtn = btn("Undo", () => void store.undo(), { title: "Undo (Ctrl+Z)" });
  const redoBtn = btn("Redo", () => void store.redo(), { title: "Redo (Ctrl+Shift+Z)" });
  const view3d = btn("3D", () => setView("perspective"), { "aria-pressed": "true" });
  const viewPlan = btn("Plan", () => setView("plan"), { "aria-pressed": "false" });
  const fileInput = h("input", { type: "file", accept: ".json,.archproj,application/json", class: "visually-hidden", "aria-label": "Import project file" });
  const importBtn = btn("Import…", () => fileInput.click());
  const main = h("main", null);
  const banner = h("div", { class: "banner", role: "alert", hidden: true });
  const bannerText = h("span", null);
  banner.append(bannerText, btn("Dismiss", () => store.dismissError()));
  const status = h("footer", null);
  const header = h("header", null,
    h("h1", null, "ArchStudio"), nameEl, h("span", { class: "sep" }), importBtn, fileInput, undoBtn, redoBtn, h("span", { class: "sep" }),
    view3d, viewPlan, btn("Fit", () => { needsFit = true; schedule(); }), h("span", { class: "sep" }),
    btn("Export DXF", () => void doExport("dxf"), { title: "2D plan, layered (not BIM)" }), btn("Export OBJ", () => void doExport("obj"), { title: "Mesh only (not BIM)" }),
    h("span", { class: "spacer" }),
    btn("Tree", () => main.classList.toggle("collapse-left"), { title: "Toggle project tree" }), btn("Inspector", () => main.classList.toggle("collapse-right"), { title: "Toggle inspector" }));

  const treeBox = h("div", null);
  const inspectorBox = h("div", null);
  const canvas = h("canvas", { tabindex: "0", role: "img", "aria-label": "3D view of the building. Click an element to select it, drag to orbit, scroll to zoom." });
  const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
  main.append(
    h("aside", { class: "left", "aria-label": "Project tree" }, h("h2", null, "Project"), treeBox),
    h("div", { class: "viewport" }, canvas, h("div", { class: "hint" }, "Click to select · Shift-click adds · Drag to orbit · Scroll to zoom")),
    h("aside", { class: "right", "aria-label": "Inspector" }, h("h2", null, "Inspector"), inspectorBox));
  root.append(header, banner, main, status);

  // ---------------------------------------------------------------- viewport
  let cam: Camera | null = null, view: "perspective" | "plan" = "perspective", needsFit = true, raf = 0, palette = readPalette();
  const rect = (): DOMRect => canvas.getBoundingClientRect();
  function resize(): void {
    const r = rect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(r.width * dpr)); canvas.height = Math.max(1, Math.round(r.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); schedule();
  }
  function schedule(): void { if (!raf) raf = requestAnimationFrame(() => { raf = 0; paint(); }); }
  function paint(): void {
    const r = rect(), s = store.getState();
    if (r.width < 2 || r.height < 2) return;
    if (s.scene && (needsFit || cam === null)) { cam = frameBounds(s.scene.bounds, 50, r.width / r.height, view); needsFit = false; }
    if (cam) draw(ctx, s.scene, cam, new Set(s.selection), palette, r.width, r.height);
  }
  function setView(v: "perspective" | "plan"): void {
    view = v; view3d.setAttribute("aria-pressed", String(v === "perspective")); viewPlan.setAttribute("aria-pressed", String(v === "plan")); needsFit = true; schedule();
  }
  new ResizeObserver(resize).observe(canvas);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { palette = readPalette(); schedule(); });

  let drag: { x: number; y: number; moved: boolean } | null = null;
  canvas.addEventListener("pointerdown", (e) => { canvas.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, moved: false }; canvas.focus(); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag || !cam) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true; drag.x = e.clientX; drag.y = e.clientY;
    if (cam.orthoHalfHeight !== undefined) { view = "perspective"; view3d.setAttribute("aria-pressed", "true"); viewPlan.setAttribute("aria-pressed", "false"); }   // orbiting leaves the plan
    cam = orbit(cam, -dx * 0.006, dy * 0.006); schedule();
  });
  canvas.addEventListener("pointerup", (e) => {
    const d = drag; drag = null;
    const s = store.getState();
    if (!d || d.moved || !cam || !s.scene) return;
    const r = rect();
    const hit = pickElement(s.scene, cam, e.clientX - r.left, e.clientY - r.top, r.width, r.height);
    const additive = e.shiftKey || e.ctrlKey || e.metaKey;
    if (hit) store.select(hit.id, additive); else if (!additive) store.clearSelection();
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const s = store.getState();
    if (!cam || !s.scene) return;
    const rad = s.scene.bounds.radius;
    cam = zoom(cam, Math.exp(e.deltaY * 0.001), rad * 0.2, rad * 20); schedule();
  }, { passive: false });
  canvas.addEventListener("keydown", (e) => {
    if (!cam) return;
    const step = 0.08, k = e.key;
    if (k === "ArrowLeft") cam = orbit(cam, -step, 0); else if (k === "ArrowRight") cam = orbit(cam, step, 0);
    else if (k === "ArrowUp") cam = orbit(cam, 0, step); else if (k === "ArrowDown") cam = orbit(cam, 0, -step); else return;
    e.preventDefault(); schedule();
  });

  window.addEventListener("keydown", (e) => {
    const t = e.target as HTMLElement | null, typing = !!t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA");
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); void (e.shiftKey ? store.redo() : store.undo()); }
    else if (mod && e.key.toLowerCase() === "y" && !typing) { e.preventDefault(); void store.redo(); }
    else if ((e.key === "Delete" || e.key === "Backspace") && !typing) { for (const id of store.getState().selection) void store.remove(id); }
    else if (e.key === "Escape" && !typing) store.clearSelection();
  });

  // ---------------------------------------------------------------- import / export
  fileInput.addEventListener("change", async () => {
    const f = fileInput.files?.[0]; fileInput.value = "";
    if (!f) return;
    try {
      if (f.size > 5 * 1024 * 1024) throw new Error("file is larger than the 5 MB limit");
      const parsed: unknown = JSON.parse(await f.text());
      const body = typeof parsed === "object" && parsed !== null && "project" in parsed ? (parsed as { project: unknown }).project : parsed;
      needsFit = true;
      await store.importProject(body);
    } catch (e) { store.reportError(`Could not import ${f.name}: ${e instanceof Error ? e.message : String(e)}`); }
  });
  async function doExport(fmt: "dxf" | "obj"): Promise<void> {
    const s = store.getState(), lvl = s.project?.levels.find((l) => l.id === s.activeLevelId);
    if (!s.project || !lvl) { store.reportError("Nothing to export."); return; }
    try {
      const text = await api.exportText(fmt, lvl.id);
      const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "text/plain" })), download: `${s.project.name}-${lvl.name}.${fmt}`.replace(/[^\w.\- ]+/g, "_") });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) { store.reportError(e instanceof Error ? e.message : String(e)); }
  }

  // ---------------------------------------------------------------- tree
  let treeKey = "";
  function renderTree(s: StoreState): void {
    if (!s.project) { clear(treeBox); return; }
    const nodes = hierarchy(s.project), key = JSON.stringify(nodes);
    const sel = new Set(s.selection);
    if (key === treeKey) {
      for (const b of treeBox.querySelectorAll<HTMLButtonElement>("button[data-id]")) b.setAttribute("aria-current", String(sel.has(b.dataset.id as string)));
      return;
    }
    treeKey = key;
    const build = (n: TreeNode, depth: number): HTMLElement => h("li", { role: "none" },
      h("button", { type: "button", role: "treeitem", "data-id": n.id, "aria-level": String(depth), "aria-current": String(sel.has(n.id)), title: n.label,
        onclick: (e: Event) => { const ev = e as MouseEvent; store.select(n.id, ev.shiftKey || ev.ctrlKey || ev.metaKey); if (n.type === "level") store.setActiveLevel(n.id); } }, n.label),
      n.children.length ? h("ul", { role: "group", class: "tree" }, ...n.children.map((c) => build(c, depth + 1))) : null);
    clear(treeBox);
    treeBox.append(nodes.length ? h("ul", { role: "tree", class: "tree", "aria-label": "Levels, walls, openings and rooms" }, ...nodes.map((n) => build(n, 1))) : h("p", { class: "empty" }, "The project is empty."));
  }

  // ---------------------------------------------------------------- inspector
  let inspectorKey = "";
  function renderInspector(s: StoreState): void {
    if (!s.project || s.selection.length === 0) { inspectorKey = ""; clear(inspectorBox); inspectorBox.append(h("p", { class: "empty" }, s.project ? "Nothing selected. Click an element in the view or the tree." : "No project loaded.")); return; }
    if (s.selection.length > 1) { inspectorKey = ""; clear(inspectorBox); inspectorBox.append(h("p", null, `${s.selection.length} elements selected.`), h("p", { class: "empty" }, "Select a single element to edit it.")); return; }
    const id = s.selection[0] as string, model = inspectorFor(s.project, id);
    if (!model) { clear(inspectorBox); return; }
    const key = `${id}|${model.fields.map((f) => f.key).join(",")}`;
    if (key === inspectorKey) {       // same element: refresh values in place, never steal focus from a field being edited
      for (const f of model.fields) {
        const el = inspectorBox.querySelector<HTMLInputElement | HTMLSelectElement>(`[data-key="${f.key}"]`);
        if (el && el !== document.activeElement) el.value = f.value;
        const ro = inspectorBox.querySelector<HTMLElement>(`[data-ro="${f.key}"]`);
        if (ro) ro.textContent = f.value;
      }
      return;
    }
    inspectorKey = key;
    const dl = h("dl", { class: "fields" });
    for (const f of model.fields) {
      const label = `${f.label}${f.unit ? ` (${f.unit})` : ""}`;
      if (f.kind === "readonly") { dl.append(h("dt", null, label), h("dd", { "data-ro": f.key }, f.value)); continue; }
      const inputId = `f-${f.key}`;
      const control = f.kind === "enum"
        ? h("select", { id: inputId, "data-key": f.key }, ...(f.options ?? []).map((o) => h("option", { value: o }, o)))
        : h("input", { id: inputId, "data-key": f.key, type: "text", autocomplete: "off", ...(f.kind === "number" ? { inputmode: "decimal" } : {}) });
      control.value = f.value;
      control.addEventListener("input", () => control.setAttribute("aria-invalid", "false"));
      control.addEventListener("change", async () => {
        const ok = await store.edit(id, f.key, control.value);
        control.setAttribute("aria-invalid", String(!ok));
        if (!ok) { const m = store.getState().project && inspectorFor(store.getState().project!, id); const cur = m?.fields.find((x) => x.key === f.key); if (cur) control.value = cur.value; }
      });
      dl.append(h("dt", null, h("label", { for: inputId }, label)), h("dd", null, control));
    }
    clear(inspectorBox);
    inspectorBox.append(h("h3", null, model.title), dl);
    if (model.deletable) inspectorBox.append(h("button", { type: "button", onclick: () => void store.remove(id) }, `Delete ${model.title.toLowerCase()}`));
  }

  // ---------------------------------------------------------------- state -> UI
  function onState(): void {
    const s = store.getState();
    nameEl.textContent = s.project?.name ?? "–";
    banner.hidden = !s.error; bannerText.textContent = s.error ?? "";
    undoBtn.disabled = redoBtn.disabled = !s.project;
    renderTree(s); renderInspector(s);
    status.textContent = "";
    status.append(h("span", null, s.revision === null ? "Not loaded" : `Revision ${s.revision}`), h("span", null, s.project ? `Units: ${s.project.units}` : ""),
      h("span", null, s.scene ? `${s.scene.elements.filter((e) => e.type === "wall").length} walls · ${s.scene.elements.filter((e) => e.type === "opening").length} openings` : ""),
      h("span", null, s.pending > 0 ? "Working…" : ""));
    schedule();
  }
  store.subscribe(onState);
  onState(); resize();

  if (new URLSearchParams(location.search).has("debug")) {   // test hook: where does an element appear on screen?
    Object.assign(window, { __archstudio: {
      pickAt(pageX: number, pageY: number): string | null {
        const s = store.getState(), r = rect();
        return cam && s.scene ? (pickElement(s.scene, cam, pageX - r.left, pageY - r.top, r.width, r.height)?.id ?? null) : null;
      },
      camera: () => cam,
      /** A screen point (page coordinates) that really picks this element, nearest the viewport centre. */
      screenOf(id: string): { x: number; y: number } | null {
        const s = store.getState(), el = s.scene?.elements.find((e) => e.id === id), r = rect();
        if (!el || !cam || !s.scene) return null;
        let best: { x: number; y: number; d: number } | null = null;
        for (let i = 0; i < el.indices.length; i += 3) {
          let cx = 0, cy = 0, cz = 0;
          for (let k = 0; k < 3; k++) { const j = (el.indices[i + k] as number) * 3; cx += (el.positions[j] as number) / 3; cy += (el.positions[j + 1] as number) / 3; cz += (el.positions[j + 2] as number) / 3; }
          const p = projectPoint(cam, [cx, cy, cz] as unknown as Vec3, r.width, r.height);
          if (!p || p.x < 0 || p.x > r.width || p.y < 0 || p.y > r.height) continue;
          // skip edge-on triangles (e.g. vertical faces in plan view): they project to a line, so clicking them is ill-defined
          const corner = (k: number): { x: number; y: number } | null => { const j = (el.indices[i + k] as number) * 3; return projectPoint(cam as Camera, [el.positions[j], el.positions[j + 1], el.positions[j + 2]] as unknown as Vec3, r.width, r.height); };
          const q0 = corner(0), q1 = corner(1), q2 = corner(2);
          if (!q0 || !q1 || !q2) continue;
          if (Math.abs((q1.x - q0.x) * (q2.y - q0.y) - (q2.x - q0.x) * (q1.y - q0.y)) / 2 < 25) continue;
          if (pickElement(s.scene, cam, p.x, p.y, r.width, r.height)?.id !== id) continue;
          const d = Math.hypot(p.x - r.width / 2, p.y - r.height / 2);
          if (!best || d < best.d) best = { x: p.x, y: p.y, d };
        }
        return best ? { x: r.left + best.x, y: r.top + best.y } : null;
      },
    } });
  }

  void store.load().then((ok) => { if (!ok && /unauthorized/.test(store.getState().error ?? "")) showConnect("The server rejected that token."); });
}

const initial = takeTokenFromUrl();
if (initial) start(initial); else showConnect(null);
