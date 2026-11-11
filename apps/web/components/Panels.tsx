"use client";
import { useState } from "react";
import { hierarchy, inspectorFor } from "@archstudio/app-core";
import type { Store, StoreState, TreeNode } from "@archstudio/app-core";

export function Tree({ store, state }: { store: Store; state: StoreState }) {
  if (!state.project) return null;
  const sel = new Set(state.selection);
  const node = (n: TreeNode): React.ReactNode => (
    <li key={n.id} role="none">
      <button role="treeitem" aria-current={sel.has(n.id)} title={n.label}
        onClick={(e) => { store.select(n.id, e.shiftKey || e.ctrlKey || e.metaKey); if (n.type === "level") store.setActiveLevel(n.id); }}>{n.label}</button>
      {n.children.length > 0 && <ul role="group">{n.children.map(node)}</ul>}
    </li>
  );
  return <ul role="tree" aria-label="Levels, walls, openings and rooms">{hierarchy(state.project).map(node)}</ul>;
}

export function Inspector({ store, state }: { store: Store; state: StoreState }) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  if (!state.project || state.selection.length === 0) return <p>Nothing selected.</p>;
  if (state.selection.length > 1) return <p>{state.selection.length} elements selected.</p>;
  const id = state.selection[0]!, model = inspectorFor(state.project, id);
  if (!model) return null;
  const commit = async (key: string, value: string) => { const ok = await store.edit(id, key, value); if (!ok) setDrafts((d) => { const { [`${id}.${key}`]: _gone, ...rest } = d; return rest; }); };
  return (
    <div>
      <h3>{model.title}</h3>
      <dl>
        {model.fields.map((f) => {
          const label = `${f.label}${f.unit ? ` (${f.unit})` : ""}`, k = `${id}.${f.key}`;
          if (f.kind === "readonly") return <div key={f.key}><dt>{label}</dt><dd>{f.value}</dd></div>;
          const value = drafts[k] ?? f.value;
          return (
            <div key={f.key}>
              <dt><label htmlFor={k}>{label}</label></dt>
              <dd>
                {f.kind === "enum"
                  ? <select id={k} value={value} onChange={(e) => void commit(f.key, e.target.value)}>{(f.options ?? []).map((o) => <option key={o}>{o}</option>)}</select>
                  : <input id={k} value={value} inputMode={f.kind === "number" ? "decimal" : undefined} autoComplete="off"
                      onChange={(e) => setDrafts((d) => ({ ...d, [k]: e.target.value }))}
                      onBlur={(e) => { if (e.target.value !== f.value) void commit(f.key, e.target.value); }}
                      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />}
              </dd>
            </div>
          );
        })}
      </dl>
      {model.deletable && <button onClick={() => void store.remove(id)}>Delete {model.title.toLowerCase()}</button>}
    </div>
  );
}
