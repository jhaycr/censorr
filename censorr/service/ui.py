"""The single-page UI, embedded as a Python constant so the wheel needs no
extra package-data and the page needs no build chain. Self-contained: inline
CSS/JS, talks only to this service's own API."""

UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>censorr</title>
<style>
  :root { --fg:#1a1a1a; --muted:#667; --line:#ddd; --ok:#0a7d32; --bad:#b3261e; --accent:#3b5bdb;
          --hov:#eef1fb; }
  @media (prefers-color-scheme: dark) {
    :root { --fg:#e8e8e8; --muted:#99a; --line:#333; --ok:#4cc776; --bad:#ff6b61; --accent:#7a95f5;
            --hov:#23252d; }
    body { background:#141518; }
  }
  * { box-sizing:border-box; }
  body { margin:0 auto; max-width:64rem; padding:1rem; color:var(--fg);
         font:15px/1.5 system-ui, sans-serif; }
  h1 { font-size:1.3rem; } h2 { font-size:1.05rem; margin:1.6rem 0 .5rem; }
  #stat { color:var(--muted); font-size:.85rem; }
  table { border-collapse:collapse; width:100%; font-size:.85rem; }
  th, td { text-align:left; padding:.3rem .5rem; border-bottom:1px solid var(--line);
           overflow-wrap:anywhere; }
  th { color:var(--muted); font-weight:600; }
  .ok { color:var(--ok); } .bad { color:var(--bad); } .muted { color:var(--muted); }
  input[type=text], select, textarea { width:100%; padding:.4rem; border:1px solid var(--line);
    border-radius:4px; background:transparent; color:var(--fg); font:inherit; }
  textarea { font:12px/1.5 ui-monospace, monospace; min-height:18rem; }
  button { padding:.4rem .9rem; border:1px solid var(--accent); border-radius:4px;
    background:var(--accent); color:#fff; font:inherit; cursor:pointer; }
  button.quiet { background:transparent; color:var(--accent); }
  form.row { display:flex; gap:.5rem; align-items:center; }
  form.row input[type=text] { flex:1; }
  .msg { margin:.4rem 0; font-size:.85rem; white-space:pre-wrap; }
  label.chk { display:flex; gap:.3rem; align-items:center; font-size:.85rem; }
  #browser { border:1px solid var(--line); border-radius:6px; margin:.5rem 0; }
  .btoolbar { display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;
              padding:.4rem .5rem; border-bottom:1px solid var(--line); }
  #browse-crumbs { flex:1 1 14rem; display:flex; flex-wrap:wrap; align-items:center;
                   gap:.1rem; font-size:.85rem; min-width:0; }
  .crumb { color:var(--accent); text-decoration:none; padding:.05rem .25rem;
           border-radius:4px; overflow-wrap:anywhere; }
  a.crumb:hover { background:var(--hov); }
  .crumb.cur { color:var(--fg); font-weight:600; }
  #browse-filter { flex:0 1 11rem; width:auto; font-size:.85rem; }
  #browse-count { font-size:.75rem; white-space:nowrap; }
  #browse-list { max-height:24rem; overflow:auto; padding:.25rem; font-size:.85rem;
                 display:grid; grid-template-columns:repeat(auto-fill, minmax(15rem, 1fr));
                 gap:0 .5rem; align-content:start; }
  .brow { display:flex; align-items:center; gap:.4rem; padding:.25rem .5rem;
          border-radius:4px; cursor:pointer; min-width:0; }
  .brow:hover { background:var(--hov); }
  .bname { flex:1; overflow-wrap:anywhere; min-width:0; }
  .buse { visibility:hidden; font-size:.75rem; padding:.05rem .5rem; flex:none; }
  .brow:hover .buse, .buse:focus { visibility:visible; }
  .bspan { grid-column:1 / -1; padding:.3rem .5rem; }
</style>
</head>
<body>
<h1>censorr <span id="stat"></span></h1>

<h2>Submit a job</h2>
<form class="row" id="submit-form">
  <input type="text" id="job-path" placeholder="file or folder, e.g. /data/media/tv/Show/Season 05" required>
  <select id="job-preset" style="max-width:11rem"><option value="">default preset</option></select>
  <label class="chk"><input type="checkbox" id="job-force"> force</label>
  <button type="button" class="quiet" id="browse-toggle">Browse…</button>
  <button type="submit">Queue</button>
</form>
<div id="browser" style="display:none">
  <div class="btoolbar">
    <span id="browse-crumbs"></span>
    <input type="text" id="browse-filter" placeholder="type to filter" autocomplete="off">
    <span id="browse-count" class="muted"></span>
    <button type="button" id="browse-pick">Use this folder</button>
  </div>
  <div id="browse-list"></div>
</div>
<div class="msg muted">A folder queues a backfill: every source file under it (a whole
season, show, or library) is expanded into individual jobs, skipping files whose clean
copy is already up to date — tick force to redo those too.</div>
<div class="msg" id="submit-msg"></div>

<h2>History
  <select id="status-filter" style="width:auto">
    <option value="">all</option><option>done</option><option>running</option>
    <option>failed</option><option>queued</option>
  </select>
  <button class="quiet" id="refresh">Refresh</button>
</h2>
<table>
  <thead><tr><th>Source</th><th>Status</th><th>Result</th><th>Mode</th>
  <th>Censored</th><th>Progress</th><th>Finished</th></tr></thead>
  <tbody id="jobs"></tbody>
</table>

<h2>Configuration <button class="quiet" id="cfg-reload">Reload</button>
  <button id="cfg-save">Save</button></h2>
<div class="msg muted">Saved changes apply to webhooks immediately and to each
worker job as it starts. Queue-path or port changes need a container restart.</div>
<textarea id="cfg" spellcheck="false"></textarea>
<div class="msg" id="cfg-msg"></div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function refreshStatus() {
  try {
    const s = await (await fetch("status")).json();
    $("stat").textContent =
      `v${s.version} — queue ${s.queue_depth} · running ${s.processing} · done ${s.done} · failed ${s.failed}`;
    const sel = $("job-preset"), current = sel.value;
    const base = s.config_file ? `no preset — ${s.config_file}` : "no preset — built-in defaults";
    sel.innerHTML = `<option value="">${esc(base)}</option>` +
      (s.presets ?? []).map(p => `<option${p === current ? " selected" : ""}>${esc(p)}</option>`).join("");
  } catch { $("stat").textContent = "(status unavailable)"; }
}

async function refreshJobs() {
  const status = $("status-filter").value;
  const rows = await (await fetch("jobs" + (status ? `?status=${status}` : ""))).json();
  $("jobs").innerHTML = rows.map(r => {
    const src = (r.job?.source ?? "").split("/").pop();
    const res = r.result ? (r.result.status + (r.result.reason ? ` (${r.result.reason})` : "")) : (r.error ? `${r.error.kind}` : "");
    const cls = r.status === "done" ? "ok" : (r.status === "failed" ? "bad" : "muted");
    const fin = r.finished_at ? r.finished_at.replace("T", " ").slice(0, 19) : "";
    const st = r.result?.stats;
    const censored = st ? (st.entries_censored
      ? `${st.entries_censored} entries · ${st.muted_seconds.toFixed(1)}s muted (${(st.mute_ratio * 100).toFixed(1)}%)`
      : "clean") : "";
    return `<tr><td title="${esc(r.job?.source)}">${esc(src)}</td>` +
      `<td class="${cls}">${esc(r.status)}</td><td>${esc(res)}</td>` +
      `<td>${esc(r.result?.mode ?? "")}</td><td>${censored}</td>` +
      `<td>${Math.round((r.progress ?? 0) * 100)}%</td><td>${esc(fin)}</td></tr>`;
  }).join("") || `<tr><td colspan="7" class="muted">no jobs yet</td></tr>`;
}

$("submit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { path: $("job-path").value, force: $("job-force").checked };
  if ($("job-preset").value) body.preset = $("job-preset").value;
  const resp = await fetch("jobs", { method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
  const data = await resp.json();
  $("submit-msg").textContent = resp.ok ?
    `queued: ${data.job_id}` : `error: ${JSON.stringify(data)}`;
  $("submit-msg").className = "msg " + (resp.ok ? "ok" : "bad");
  refreshJobs(); refreshStatus();
});

async function loadConfig() {
  const resp = await fetch("config/file");
  if (resp.ok) { $("cfg").value = (await resp.json()).content; $("cfg-msg").textContent = ""; }
  else { $("cfg-msg").textContent = "no config file configured for this service"; }
}
$("cfg-reload").addEventListener("click", loadConfig);
$("cfg-save").addEventListener("click", async () => {
  const resp = await fetch("config/file", { method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ content: $("cfg").value }) });
  const data = await resp.json();
  $("cfg-msg").textContent = resp.ok ? "saved and reloaded" : `rejected: ${data.detail}`;
  $("cfg-msg").className = "msg " + (resp.ok ? "ok" : "bad");
});

let browseCurrent = null, browseParent = null, browseRoots = null;
let browseEntries = { dirs: [], files: [] };

async function fetchBrowse(path) {
  const resp = await fetch("browse?limit=10000" + (path ? `&path=${encodeURIComponent(path)}` : ""));
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail ?? `error ${resp.status}`);
  return data;
}

// Shortest suffix of `root` that tells the configured roots apart, so root
// crumbs/chips read "tv/General" rather than "/data/media/tv/General".
function rootLabel(root) {
  const split = (p) => p.split("/").filter(Boolean);
  const roots = (browseRoots?.length ? browseRoots : [root]).map(split);
  let n = 0;
  while (roots.every(r => r.length > n + 1 && r[n] === roots[0][n])) n++;
  return split(root).slice(n).join("/") || root;
}

function pickPath(path) {
  $("job-path").value = path;
  $("browser").style.display = "none";
}

function renderCrumbs() {
  const crumbs = [{ label: "roots", path: null }];
  if (browseCurrent !== null) {
    const root = (browseRoots ?? []).find(r => browseCurrent === r || browseCurrent.startsWith(r + "/"));
    if (root) {
      crumbs.push({ label: rootLabel(root), path: root });
      if (browseCurrent !== root) {
        const parts = browseCurrent.slice(root.length + 1).split("/");
        parts.forEach((seg, i) =>
          crumbs.push({ label: seg, path: root + "/" + parts.slice(0, i + 1).join("/") }));
      }
    } else crumbs.push({ label: browseCurrent, path: browseCurrent });
  }
  $("browse-crumbs").innerHTML = crumbs.map((c, i) =>
    (i ? `<span class="muted">/</span>` : "") +
    (i === crumbs.length - 1 && crumbs.length > 1
      ? `<span class="crumb cur">${esc(c.label)}</span>`
      : `<a href="#" class="crumb" data-p="${esc(c.path ?? "")}">${esc(c.label)}</a>`)).join("");
  $("browse-crumbs").querySelectorAll("a.crumb").forEach(a =>
    a.addEventListener("click", e => { e.preventDefault(); browseTo(a.dataset.p || null); }));
}

function renderList() {
  const q = $("browse-filter").value.trim().toLowerCase();
  const dirs = browseEntries.dirs.filter(d => d.toLowerCase().includes(q));
  const files = browseEntries.files.filter(f => f.toLowerCase().includes(q));
  const join = (n) => browseCurrent ? browseCurrent + "/" + n : n;
  $("browse-list").innerHTML =
    dirs.map(d => `<div class="brow bdir" data-p="${esc(join(d))}" title="${esc(join(d))}">` +
      `<span>&#128193;</span><span class="bname">${esc(browseCurrent ? d : rootLabel(d))}</span>` +
      `<button type="button" class="quiet buse" title="queue this folder">use</button></div>`).join("") +
    files.map(f => `<div class="brow bfile" data-p="${esc(join(f))}" title="${esc(join(f))}">` +
      `<span>&#127916;</span><span class="bname">${esc(f)}</span></div>`).join("") ||
    `<div class="bspan muted">${q ? "no matches" : "empty"}</div>`;
  const total = browseEntries.dirs.length + browseEntries.files.length;
  $("browse-count").textContent =
    (q ? `${dirs.length + files.length} of ` : "") +
    `${total}${browseEntries.truncated ? ` (first ${total} only)` : ""}`;
  $("browse-list").querySelectorAll(".bdir").forEach(el =>
    el.addEventListener("click", () => browseTo(el.dataset.p)));
  $("browse-list").querySelectorAll(".bfile").forEach(el =>
    el.addEventListener("click", () => pickPath(el.dataset.p)));
  $("browse-list").querySelectorAll(".buse").forEach(el =>
    el.addEventListener("click", e => { e.stopPropagation(); pickPath(el.closest(".brow").dataset.p); }));
}

async function browseTo(path) {
  let b;
  try { b = await fetchBrowse(path); }
  catch (err) { $("browse-list").innerHTML = `<div class="bspan bad">${esc(err.message)}</div>`; return; }
  if (b.path === null) browseRoots = b.dirs;
  browseCurrent = b.path; browseParent = b.parent;
  browseEntries = { dirs: b.dirs, files: b.files, truncated: b.truncated };
  $("browse-filter").value = "";
  $("browse-pick").style.display = b.path ? "" : "none";
  renderCrumbs(); renderList();
  $("browse-filter").focus();
}

$("browse-toggle").addEventListener("click", () => {
  const el = $("browser");
  el.style.display = el.style.display === "none" ? "" : "none";
  if (el.style.display === "") browseTo(browseCurrent);   // reopen where you left off
});
$("browse-filter").addEventListener("input", renderList);
$("browse-filter").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("browser").style.display = "none"; return; }
  if (e.key === "Backspace" && !e.target.value && browseCurrent !== null) {
    e.preventDefault(); browseTo(browseParent); return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    const rows = $("browse-list").querySelectorAll(".brow");
    if (rows.length === 1) rows[0].click();   // sole match: enter dir / pick file
  }
});
$("browse-pick").addEventListener("click", () => {
  if (browseCurrent) pickPath(browseCurrent);
});

$("refresh").addEventListener("click", () => { refreshJobs(); refreshStatus(); });
$("status-filter").addEventListener("change", refreshJobs);
refreshStatus(); refreshJobs(); loadConfig();
setInterval(() => { refreshStatus(); refreshJobs(); }, 5000);
</script>
</body>
</html>
"""
