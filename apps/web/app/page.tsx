"use client";
import { useEffect, useMemo, useState } from "react";
import { ApiClient, Store } from "@archstudio/app-core";
import { Viewport } from "../components/Viewport";
import { Inspector, Tree } from "../components/Panels";
import { useStore } from "../lib/useStore";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8765";

export default function Page() {
  const [token, setToken] = useState<string | null>(null);   // memory only: never localStorage
  useEffect(() => {
    const m = /(?:^#|&)token=([^&]+)/.exec(window.location.hash);
    if (m) { setToken(decodeURIComponent(m[1]!)); history.replaceState(null, "", window.location.pathname); }
  }, []);
  if (!token) return <TokenForm onToken={setToken} />;
  return <Workspace token={token} />;
}

function TokenForm({ onToken }: { onToken: (t: string) => void }) {
  const [v, setV] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (v.trim()) onToken(v.trim()); }} style={{ maxWidth: 420, margin: "12vh auto", display: "grid", gap: 8 }}>
      <h1>ArchStudio</h1>
      <label htmlFor="token">API token printed by the server</label>
      <input id="token" type="password" value={v} onChange={(e) => setV(e.target.value)} autoComplete="off" />
      <button type="submit">Connect</button>
    </form>
  );
}

function Workspace({ token }: { token: string }) {
  const store = useMemo(() => new Store(new ApiClient(API, token)), [token]);
  const state = useStore(store);
  useEffect(() => { void store.load(); }, [store]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "SELECT", "TEXTAREA"].includes((e.target as HTMLElement).tagName), mod = e.ctrlKey || e.metaKey;
      if (typing) return;
      if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); void (e.shiftKey ? store.redo() : store.undo()); }
      else if (e.key === "Delete" || e.key === "Backspace") state.selection.forEach((id) => void store.remove(id));
      else if (e.key === "Escape") store.clearSelection();
    };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, [store, state.selection]);

  return (
    <div className="shell">
      <header style={{ display: "flex", gap: 8, padding: 8 }}>
        <strong>ArchStudio</strong> <span>{state.project?.name ?? "–"}</span>
        <button onClick={() => void store.undo()}>Undo</button><button onClick={() => void store.redo()}>Redo</button>
      </header>
      {state.error && <div role="alert">{state.error} <button onClick={() => store.dismissError()}>Dismiss</button></div>}
      <main>
        <aside className="tree-list" aria-label="Project tree"><Tree store={store} state={state} /></aside>
        <div className="viewport"><Viewport scene={state.scene} selection={state.selection} onPick={(id, add) => (id ? store.select(id, add) : add || store.clearSelection())} /></div>
        <aside aria-label="Inspector"><Inspector store={store} state={state} /></aside>
      </main>
    </div>
  );
}
