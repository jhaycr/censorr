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
  :root { --fg:#1a1a1a; --muted:#667; --line:#ddd; --ok:#0a7d32; --bad:#b3261e; --accent:#3b5bdb; }
  @media (prefers-color-scheme: dark) {
    :root { --fg:#e8e8e8; --muted:#99a; --line:#333; --ok:#4cc776; --bad:#ff6b61; --accent:#7a95f5; }
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
</style>
</head>
<body>
<h1>censorr <span id="stat"></span></h1>

<h2>Submit a job</h2>
<form class="row" id="submit-form">
  <input type="text" id="job-path" placeholder="file or folder, e.g. /data/media/tv/Show/Season 05" required>
  <select id="job-preset" style="max-width:11rem"><option value="">default preset</option></select>
  <label class="chk"><input type="checkbox" id="job-force"> force</label>
  <button type="submit">Queue</button>
</form>
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
    sel.innerHTML = `<option value="">default preset</option>` +
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

$("refresh").addEventListener("click", () => { refreshJobs(); refreshStatus(); });
$("status-filter").addEventListener("change", refreshJobs);
refreshStatus(); refreshJobs(); loadConfig();
setInterval(() => { refreshStatus(); refreshJobs(); }, 5000);
</script>
</body>
</html>
"""
