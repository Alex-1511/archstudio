// Tiny DOM builder. Text is only ever set via textContent / text nodes: project data is untrusted (never innerHTML).
export type Child = string | Node | null | false | undefined;
export type Props = Record<string, string | boolean | number | ((e: Event) => void) | undefined>;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, props: Props | null, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v === undefined || v === false) continue;
    if (typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "class") el.className = String(v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children) if (c !== null && c !== false && c !== undefined) el.append(typeof c === "string" ? document.createTextNode(c) : c);
  return el;
}
export const clear = (el: Element): void => { while (el.firstChild) el.removeChild(el.firstChild); };
