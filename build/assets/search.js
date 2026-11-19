// Skill search sidebar: keyword + in-browser AI (semantic) search over the resume.
const TRANSFORMERS = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.1";
const MODEL = "Xenova/all-MiniLM-L6-v2";

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const panel = $("#ss"), backdrop = $("#ss-backdrop"), input = $("#ss-input"), body = $("#ss-body");
const statusDot = $("#ss-dot"), statusText = $("#ss-stext");

let IX = null, byName = {}, ai = null, aiState = "idle", docVecs = null, skillVecs = null, lastQ = "", lastFocus = null;

async function loadIndex() {
  if (IX) return IX;
  IX = await fetch("./search-index.json", { cache: "no-cache" }).then((r) => r.json());
  IX.skills.forEach((s) => (byName[s.name] = s));
  return IX;
}

// ---------- AI model (runs entirely in the browser) ----------
function setStatus(state, text) {
  aiState = state;
  statusDot.className = "ss-dot " + (state === "loading" ? "load" : state === "ready" ? "ok" : "");
  statusText.textContent = text;
}
async function loadAI() {
  if (ai || aiState === "loading") return;
  setStatus("loading", "Loading AI search model…");
  try {
    const { pipeline, env } = await import(TRANSFORMERS);
    env.allowLocalModels = false;
    const seen = {};
    ai = await pipeline("feature-extraction", MODEL, {
      dtype: "q8",
      progress_callback: (p) => {
        if (p.status === "progress" && p.total) {
          seen[p.file] = [p.loaded, p.total];
          const [l, t] = Object.values(seen).reduce((a, [x, y]) => [a[0] + x, a[1] + y], [0, 0]);
          setStatus("loading", `Loading AI search model… ${Math.round((l / t) * 100)}%`);
        }
      },
    });
    await loadIndex();
    const docTexts = IX.docs.map((d) => `${d.role} at ${d.company}: ${d.text}`);
    const skillTexts = IX.skills.map((s) => `${s.name} (${s.category}): ${s.aliases.join(", ")}`);
    docVecs = (await ai(docTexts, { pooling: "mean", normalize: true })).tolist();
    skillVecs = (await ai(skillTexts, { pooling: "mean", normalize: true })).tolist();
    setStatus("ready", "AI search ready · runs privately in your browser");
    if (lastQ) run(lastQ);
  } catch (e) {
    console.warn(e);
    ai = null;
    setStatus("off", "AI model unavailable · using keyword search");
  }
}
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);

// ---------- matching ----------
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9+#/.\- ]/g, " ").replace(/\s+/g, " ").trim();
function keywordScores(q) {
  const nq = " " + norm(q) + " ";
  const toks = norm(q).split(" ").filter((t) => t.length >= 2);
  const out = {};
  for (const s of IX.skills) {
    let best = 0;
    for (const a of [s.name, ...s.aliases].map(norm)) {
      if (!a) continue;
      if (norm(q) === a) best = Math.max(best, 1);
      else if (nq.includes(" " + a + " ")) best = Math.max(best, 0.9);
      else if (toks.some((t) => t.length >= 3 && a.startsWith(t))) best = Math.max(best, 0.6);
    }
    if (best) out[s.name] = best;
  }
  return out;
}
async function semantic(q) {
  if (!ai || !docVecs) return null;
  const qv = (await ai([q], { pooling: "mean", normalize: true })).tolist()[0];
  const docs = IX.docs.map((d, i) => ({ ...d, sim: dot(qv, docVecs[i]) })).sort((a, b) => b.sim - a.sim);
  const skills = {};
  IX.skills.forEach((s, i) => { const v = dot(qv, skillVecs[i]); if (v > 0.38) skills[s.name] = v; });
  for (const d of docs.slice(0, 6)) {
    if (d.sim < 0.3) break;
    for (const s of IX.skills)
      if (s.evidence.some((e) => e.text === d.text)) skills[s.name] = (skills[s.name] || 0) + d.sim * 0.5;
  }
  const top = docs.length ? docs[0].sim : 0;
  return { docs: docs.filter((d) => d.sim >= 0.32 && d.sim >= top * 0.75).slice(0, 5), skills };
}

// ---------- rendering ----------
const bar = (v) => `<div class="ss-bar"><i style="width:${Math.max(2, Math.min(100, v))}%"></i></div>`;
const yrs = (y) => (y >= 1 ? `${y} yr${y === 1 ? "" : "s"}` : y > 0 ? `${Math.round(y * 12)} mo` : "—");

function highlight(text, q) {
  const terms = norm(q).split(" ").filter((t) => t.length >= 3);
  let h = esc(text);
  for (const t of terms) h = h.replace(new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}[a-z0-9-]*)`, "gi"), "<mark>$1</mark>");
  return h;
}

function card(s, q) {
  const work = s.evidence.filter((e) => e.kind === "experience");
  const study = s.evidence.filter((e) => e.kind === "education");
  const ev = [...work, ...study];
  const first = ev.slice(0, 3), rest = ev.slice(3);
  const evLi = (e) => `<li>${highlight(e.text, q)}<small>${esc(e.role)} · ${esc(e.company)} · ${esc(e.date)}${e.kind === "education" ? " · coursework" : ""}</small></li>`;
  const used = s.months ? `${s.roles} role${s.roles === 1 ? "" : "s"} · ${s.companies.length} co.` : study.length ? "Coursework" : "Listed skill";
  const parts = Object.entries(s.parts).filter(([, v]) => v > 0)
    .map(([k, v]) => `<div class="ss-part"><span>${esc(k)}</span>${bar((v / ({ "Hands-on years": 45, Recency: 20, "Breadth of roles": 15, "Related techs": 20, "Study / listed": 10 }[k] || 20)) * 100)}<em>+${v}</em></div>`).join("");
  return `<article class="ss-card">
    <div class="ss-ch"><div><h3>${esc(s.name)}</h3><div class="ss-cat">${esc(s.category)}${s.companies.length ? " · " + esc(s.companies.join(", ")) : ""}</div></div><span class="ss-lv lv-${s.level}">${s.level}</span></div>
    <div class="ss-score">${bar(s.score)}<b>${s.score}/100</b></div>
    <div class="ss-m"><div><b>${yrs(s.years)}</b><span>Hands-on at work</span></div><div><b>${esc(s.last_label || "—")}</b><span>Last used</span></div><div><b>${esc(used)}</b><span>Where</span></div></div>
    <div class="ss-lbl">How the level is calculated</div><div class="ss-parts">${parts}</div>
    ${s.related_present.length ? `<div class="ss-lbl">Related techs in the profile (${s.related_present.length}/${s.related.length})</div><div class="ss-tags">${s.related_present.map((r) => `<button class="ss-tag" data-q="${esc(r)}">${esc(r)}</button>`).join("")}${s.related_missing.map((r) => `<span class="ss-tag miss">${esc(r)}</span>`).join("")}</div>` : ""}
    ${ev.length ? `<div class="ss-lbl">Evidence from the resume</div><ul class="ss-ev">${first.map(evLi).join("")}</ul>${rest.length ? `<ul class="ss-ev" hidden style="margin-top:8px">${rest.map(evLi).join("")}</ul><button class="ss-more">Show ${rest.length} more</button>` : ""}` : `<p class="ss-empty" style="padding:6px 0 0">Listed in technical skills.</p>`}
  </article>`;
}

function overview() {
  const soft = ["Leadership", "Operations", "Domains"];
  const top = IX.skills.filter((s) => s.months && !soft.includes(s.category)).slice(0, 10);
  const expert = IX.skills.filter((s) => s.level === "Expert").length;
  body.innerHTML = `
    <div class="ss-kpis"><div class="ss-kpi"><b>${IX.career_years}</b><span>years since first role</span></div><div class="ss-kpi"><b>${IX.skills.length}</b><span>skills found</span></div><div class="ss-kpi"><b>${expert}</b><span>at Expert level</span></div></div>
    <div class="ss-sec">Strongest technical skills</div>
    ${top.map((s) => `<button class="ss-row" data-q="${esc(s.name)}"><span class="ss-rn">${esc(s.name)}<span class="ss-rc">${esc(s.level)} · ${yrs(s.years)} · ${s.last_label === "Present" ? "current" : "last " + esc(s.last_label)}</span></span>${bar(s.score)}<span class="ss-rs">${s.score}</span></button>`).join("")}
    <p class="ss-note">Levels combine hands-on years from role dates (overlaps counted once), how recently the skill was used, how many roles used it, and how many related technologies also appear in the profile. Everything is calculated from the resume itself.</p>`;
}

let runId = 0;
async function run(q) {
  lastQ = q = q.trim();
  await loadIndex();
  if (!q) return overview();
  const id = ++runId;
  const kw = keywordScores(q);
  const sem = await semantic(q);
  if (id !== runId) return;
  const comb = { ...kw };
  if (sem) for (const [k, v] of Object.entries(sem.skills)) comb[k] = (comb[k] || 0) + v;
  const ranked = Object.entries(comb).sort((a, b) => b[1] - a[1] || byName[b[0]].score - byName[a[0]].score)
    .filter(([, v], i, arr) => v >= arr[0][1] * 0.45).slice(0, 5).map(([k]) => byName[k]);
  let html = "";
  if (sem && sem.docs.length) {
    html += `<div class="ss-sec">Best-matching experience</div>` + sem.docs.slice(0, 3).map((d) =>
      `<div class="ss-hit">${highlight(d.text, q)}<small><span>${esc(d.role)} · ${esc(d.company)} · ${esc(d.date)}</span><span>${Math.round(d.sim * 100)}% match</span></small></div>`).join("");
  }
  html += ranked.length
    ? `<div class="ss-sec" style="margin-top:16px">Skills & expertise</div>` + ranked.map((s) => card(s, q)).join("")
    : `<p class="ss-empty">No direct match for “${esc(q)}”.${aiState === "ready" ? "" : " The AI model is still loading. Results for related wording will appear when it's ready."} Try a technology like Kubernetes, Java or RAG.</p>`;
  body.innerHTML = html;
}

// ---------- open / close / events ----------
function openPanel(q) {
  lastFocus = document.activeElement;
  panel.classList.add("on"); backdrop.classList.add("on");
  panel.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  if (typeof q === "string") input.value = q;
  run(input.value);
  loadAI();
  setTimeout(() => input.focus(), 50);
}
function closePanel() {
  panel.classList.remove("on"); backdrop.classList.remove("on");
  panel.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  lastFocus && lastFocus.focus && lastFocus.focus();
}
document.querySelectorAll("[data-ss-open]").forEach((b) => b.addEventListener("click", () => openPanel()));
$("#ss-x").addEventListener("click", closePanel);
backdrop.addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && panel.classList.contains("on")) closePanel();
  if (e.key === "/" && !panel.classList.contains("on") && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); openPanel(); }
});
let t;
input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => run(input.value), 220); });
panel.addEventListener("click", (e) => {
  const q = e.target.closest("[data-q]");
  if (q) { input.value = q.dataset.q; run(q.dataset.q); body.scrollTop = 0; return; }
  const more = e.target.closest(".ss-more");
  if (more) { more.previousElementSibling.hidden = false; more.remove(); }
});
if (new URLSearchParams(location.search).has("search")) openPanel(new URLSearchParams(location.search).get("search") || "");
