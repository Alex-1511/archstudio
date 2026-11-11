"use client";
// Three.js viewport. Geometry comes from the Python engine (scene buffers); this file only draws and forwards picks.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fitCamera } from "@archstudio/app-core";
import type { Scene } from "@archstudio/app-core";

interface Props { scene: Scene | null; selection: readonly string[]; onPick: (id: string | null, additive: boolean) => void }

const COLORS = { wall: 0xcfc9bd, door: 0xb7742f, window: 0x3f8fc4, accent: 0xd9622b } as const;

export function Viewport({ scene, selection, onPick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const three = useRef<{ renderer: THREE.WebGLRenderer; cam: THREE.PerspectiveCamera; controls: OrbitControls; root: THREE.Group; fitted: boolean } | null>(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    el.appendChild(renderer.domElement);
    const sc = new THREE.Scene();
    sc.background = new THREE.Color(0xecebe7);
    const cam = new THREE.PerspectiveCamera(50, 1, 0.05, 5000);
    cam.up.set(0, 0, 1);                                         // the engine is Z-up
    const controls = new OrbitControls(cam, renderer.domElement);
    sc.add(new THREE.HemisphereLight(0xffffff, 0x888880, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(10, -15, 25); sc.add(sun);
    const grid = new THREE.GridHelper(200, 200, 0xaaaaaa, 0xd0cdc5); grid.rotateX(Math.PI / 2); sc.add(grid);
    const root = new THREE.Group(); sc.add(root);
    three.current = { renderer, cam, controls, root, fitted: false };

    const resize = () => { const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h); cam.aspect = w / Math.max(h, 1); cam.updateProjectionMatrix(); };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();
    let raf = 0; const loop = () => { raf = requestAnimationFrame(loop); controls.update(); renderer.render(sc, cam); }; loop();

    // click-to-pick (ignore drags); on coincident hits an opening beats the wall around it, as in app-core
    const ray = new THREE.Raycaster(); let down: [number, number] | null = null;
    const dom = renderer.domElement;
    dom.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
    dom.addEventListener("pointerup", (e) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) { down = null; return; }
      down = null;
      const r = dom.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), cam);
      const hits = ray.intersectObjects(root.children, false);
      const first = hits[0];
      const best = first ? (hits.find((h) => Math.abs(h.distance - first.distance) < 1e-6 && h.object.userData.type === "opening") ?? first) : null;
      pick.current(best ? (best.object.userData.id as string) : null, e.shiftKey || e.ctrlKey || e.metaKey);
    });
    return () => { cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); renderer.dispose(); dom.remove(); three.current = null; };
  }, []);

  useEffect(() => {              // rebuild meshes when the engine's geometry changes
    const t = three.current; if (!t) return;
    for (const c of [...t.root.children]) { const m = c as THREE.Mesh; m.geometry.dispose(); (m.material as THREE.Material).dispose(); t.root.remove(c); }
    if (!scene) return;
    for (const e of scene.elements) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(e.positions, 3)); g.setIndex(new THREE.BufferAttribute(e.indices, 1)); g.computeVertexNormals();
      const base = e.type === "wall" ? COLORS.wall : e.kind === "door" ? COLORS.door : COLORS.window;
      const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: base, transparent: e.type === "opening", opacity: e.type === "opening" ? 0.35 : 1, depthWrite: e.type !== "opening" }));
      m.userData = { id: e.id, type: e.type, base }; t.root.add(m);
    }
    if (!t.fitted && scene.elements.length) {
      const c = fitCamera(scene.bounds, 50, t.cam.aspect);
      t.cam.position.set(...c.position); t.controls.target.set(...c.target); t.controls.update(); t.fitted = true;
    }
  }, [scene]);

  useEffect(() => {              // selection highlight
    const t = three.current; if (!t) return;
    const sel = new Set(selection);
    for (const c of t.root.children) { const m = c as THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>; m.material.emissive.setHex(sel.has(m.userData.id) ? COLORS.accent : 0x000000); m.material.emissiveIntensity = 0.55; }
  }, [selection, scene]);

  return <div ref={host} style={{ position: "absolute", inset: 0 }} role="img" aria-label="3D view of the building" />;
}
