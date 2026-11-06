// What every demo page shares: a few helpers and markdown through marked (loaded by the page).
export const $ = id => document.getElementById(id);
export const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const get = async path => (await fetch(path)).json();
export const post = async (path, body) => {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body || {}) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
};
export const ago = t => { const s = Math.round(Date.now() / 1000 - t); return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`; };
export const clock = t => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const wsUrl = (sid, f) => `/ws/${sid}/${f.id}`;
/** Markdown to HTML, with images and links that name files in `files` (the job's workspace folder) resolved. */
export function md(src, sid, files = []) {
  const div = document.createElement("div");
  div.innerHTML = window.marked ? marked.parse(src || "") : `<pre>${esc(src)}</pre>`;
  div.querySelectorAll("img").forEach(img => {
    const rel = (img.getAttribute("src") || "").replace(/^\.\//, "");
    const f = files.find(f => f.rel === rel) || files.find(f => f.rel.endsWith("/" + rel.split("/").pop()));
    if (f) img.src = wsUrl(sid, f); else img.remove();
  });
  div.querySelectorAll("a").forEach(a => { a.target = "_blank"; a.rel = "noopener"; });
  return div.innerHTML;
}
export const pill = (status, label) => `<span class="pill ${status}">${esc(label || status)}</span>`;
export const steps = list => list.length ? `<div class="steps">${list.map(s => `<span class="step"><b>${esc(s.kind)}</b> ${esc(s.text)}</span>`).join("")}</div>` : "";
