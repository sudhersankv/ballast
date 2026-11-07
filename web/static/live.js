/* ballast. live: polls /api/live every 3 s and renders the running training session. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => (x == null ? "–" : Math.round(x * 100));
  const fmtTok = (n) => (n == null ? "–" : n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`);
  const params = new URLSearchParams(location.search);
  const S = { db: params.get("db") || "ballast_dev", session: null, since: null, runs: new Map(), log: [], blocks: [], versions: [], lastAt: null, timer: null, err: null };

  async function get(p) {
    const r = await fetch(p);
    if (!r.ok) { let m = `${r.status}`; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
    return r.json();
  }
  const ago = (iso) => {
    if (!iso) return "never";
    const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    return s < 60 ? `${Math.round(s)}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
  };

  async function poll() {
    try {
      const q = new URLSearchParams({ db: S.db });
      if (S.since) q.set("since", S.since);
      const d = await get(`/api/live?${q}`);
      S.err = null;
      if (d.session !== S.session) {
        const had = S.session !== null || S.since;
        S.session = d.session; S.runs.clear(); S.log = []; S.seen = new Set(); $("#log").innerHTML = "";
        if (had && S.since) { S.since = null; return poll(); }
      }
      S.seen = S.seen || new Set();
      const fresh = d.log.filter((l) => { const k = `${l.created_at}|${l.msg}`; if (S.seen.has(k)) return false; S.seen.add(k); return true; });
      fresh.forEach((l) => S.log.push(l));
      d.runs.forEach((r) => S.runs.set(r.run_id, r));
      S.gates = S.gates || new Map();
      const firstLoad = S.gates.size === 0;
      const newGates = (d.gates || []).filter((g) => { const k = `${g.time}|${g.case_id}|${g.event}`; if (S.gates.has(k)) return false; S.gates.set(k, g); return true; });
      if (newGates.length) renderGates(firstLoad ? [] : newGates);
      S.blocks = d.blocks; S.versions = d.versions; S.started = d.started_at; S.progress = d.progress;
      const stamps = [...d.log.map((l) => l.created_at), ...d.runs.map((r) => r.created_at)].filter(Boolean).sort();
      if (stamps.length) {
        const mx = stamps[stamps.length - 1];
        if (!S.lastAt || mx > S.lastAt) S.lastAt = mx;
        // overlap the cursor by 5 s: parallel workers can insert slightly out of order; we dedupe above
        const back = new Date(Date.parse(mx) - 5000).toISOString().replace("Z", "+00:00");
        if (!S.since || back > S.since) S.since = back;
      }
      render(fresh);
    } catch (e) {
      S.err = e.message;
      renderStatus();
    }
  }

  const active = () => S.lastAt && Date.now() - Date.parse(S.lastAt) < 120000;
  function renderStatus() {
    const st = $("#status");
    if (S.err) { st.dataset.level = "red"; st.querySelector("b").textContent = "Offline"; $("#live-sub").textContent = `Can't read ${S.db}: ${S.err}. Retrying every 3 s.`; return; }
    const on = active();
    // connecting -> live -> stale (session exists, no rows for 2 min) -> idle (no session)
    st.dataset.level = on ? "live" : S.session ? "yellow" : "idle";
    st.querySelector("b").textContent = on ? "Live" : S.session ? `Stale, last run ${ago(S.lastAt)}` : "No session";
    document.querySelector(".live-link")?.classList.toggle("on", !!on);
  }

  function render(newLog) {
    renderStatus();
    if (!S.session) {
      $("#live-sub").textContent = `No training session in ${S.db} yet. Start one with python -m runtime.loop train.`;
      return;
    }
    $("#live-sub").textContent = `Session ${S.session}, started ${ago(S.started)} in ${S.db}. Open any tile for the full trace.`;
    // progress
    const p = S.progress;
    if (p) {
      $("#prog-k").textContent = `Playbook v${p.version}, ${p.set} set`;
      $("#prog-num").innerHTML = `${p.done}<small>/${p.total}</small>`;
      $("#t-pass").textContent = p.passed; $("#t-fail").textContent = p.failed; $("#t-mean").textContent = pct(p.mean);
      $("#prog-bar").style.width = `${Math.min(100, (p.done / p.total) * 100)}%`;
      const all = S.blocks.reduce((a, b) => a + b.done, 0);
      $("#prog-meta").textContent = `${all} cases finished this session across ${S.blocks.length} ${S.blocks.length === 1 ? "batch" : "batches"}. Last run ${ago(S.lastAt)}.`;
    }
    renderBlocks();
    renderLog(newLog);
    renderVersions();
  }

  function renderBlocks() {
    const host = $("#blocks");
    if (!S.blocks.length) { host.innerHTML = `<p class="muted">No runs in this session yet. The first tile appears when the agent finishes its first case.</p>`; return; }
    const runs = [...S.runs.values()];
    host.innerHTML = S.blocks.map((b, bi) => {
      const mine = runs.filter((r) => r.playbook_version === b.version && r.set === b.set).sort((x, y) => x.created_at.localeCompare(y.created_at));
      const isCur = bi === S.blocks.length - 1;
      const cells = mine.map((r) => {
        const cls = r.error && r.score == null ? "err" : r.passed ? "pass" : "fail";
        const label = `${r.case_id}, ${r.passed ? "passed" : "failed"}, score ${pct(r.score)}${r.top_violation ? `, ${r.top_violation}` : ""}`;
        return `<button class="cell ${cls}" data-run="${esc(r.run_id)}" aria-label="${esc(label)}" title="${esc(label)}"></button>`;
      });
      for (let k = mine.length; k < b.total; k++) {
        const running = isCur && active() && k === mine.length;
        cells.push(`<span class="cell ${running ? "run" : "wait"}" aria-hidden="true"></span>`);
      }
      const verdict = b.done >= b.total ? `${b.passed}/${b.total} passed, mean ${pct(b.mean)}` : `${b.done} of ${b.total} done`;
      return `<div class="block ${isCur ? "cur" : ""}"><div class="block-k"><b>v${b.version}</b> ${esc(b.set)}<span>${verdict}</span></div><div class="cells">${cells.join("")}</div></div>`;
    }).join("");
  }

  function logClass(m) {
    if (/SHIPPED|level: green|aligned/i.test(m)) return "ok";
    if (/REJECTED|block|invalid/i.test(m)) return "warn";
    if (/rolled back|level: red|escalat|error|failed/i.test(m)) return "bad";
    if (/analyst|subq/i.test(m)) return "subq";
    if (/mentor|muse/i.test(m)) return "muse";
    if (/^==/.test(m.trim())) return "head";
    return "";
  }
  function renderLog(newLog) {
    const ol = $("#log");
    if (!S.log.length) { ol.innerHTML = `<li class="muted">No log lines yet.</li>`; return; }
    if (!newLog.length) return;
    ol.querySelector(".muted")?.remove();
    ol.insertAdjacentHTML("beforeend", newLog.map((l) => `<li class="${logClass(l.msg)}"><time datetime="${esc(l.created_at)}">${esc((l.created_at || "").slice(11, 19))}</time><span>${esc(l.msg)}</span></li>`).join(""));
    if ($("#follow").checked) ol.scrollTop = ol.scrollHeight;
  }

  function renderGates(fresh) {
    const rows = [...S.gates.values()].sort((a, b) => String(b.time).localeCompare(String(a.time)));
    const isFresh = new Set(fresh.map((g) => `${g.time}|${g.case_id}|${g.event}`));
    $("#gates").innerHTML = `<thead><tr><th>Time</th><th>Client</th><th>Event</th><th>Top rule at risk</th><th class="r">p</th><th class="r">Covered</th><th class="r hide-m">Urgency</th><th>Decision</th><th class="r hide-m">Seconds</th></tr></thead>
      <tbody>${rows.map((g) => {
        const [r, p] = Object.entries(g.rule_risk || {}).sort((a, b) => b[1] - a[1])[0] || ["none", 0];
        return `<tr class="${isFresh.has(`${g.time}|${g.case_id}|${g.event}`) ? "fresh" : ""}">
          <td class="mono">${esc(String(g.time || "").slice(11, 19))}</td><td class="mono">${esc(g.case_id)}</td><td>${esc(String(g.event || "").replace(/_/g, " "))}</td>
          <td class="mono">${esc(r)}</td><td class="r rr">${Number(p).toFixed(3)}</td><td class="r">${Number(g.covered ?? 0).toFixed(3)}</td>
          <td class="r hide-m">${esc(g.urgency ?? "–")}</td><td class="${g.rerun_now ? "yes" : "no"}">${g.rerun_now ? "▲ Re-run" : "■ Clear"}</td>
          <td class="r hide-m">${g.seconds != null ? Number(g.seconds).toFixed(2) : "–"}</td></tr>`;
      }).join("")}</tbody>`;
    if (fresh.length) setTimeout(() => document.querySelectorAll("#gates tr.fresh").forEach((t) => t.classList.remove("fresh")), 1200);
  }

  function renderVersions() {
    const ul = $("#ver-list");
    if (!S.versions.length) { ul.innerHTML = `<li class="muted">No versions yet.</li>`; return; }
    ul.innerHTML = S.versions.map((v) => `<li><button data-v="${v.version}" class="ver ${esc(v.status)}">
      <b>v${v.version}</b><span class="badge">${esc(v.status || "")}</span><span class="cl">${esc(v.changelog || "")}</span></button></li>`).join("");
  }

  // ---------- drawers ----------
  function openSheet(html) { $("#sheet-body").innerHTML = html; if (!$("#sheet").open) $("#sheet").showModal(); }
  async function openRun(id) {
    openSheet(`<p>Loading run ${esc(id)}.</p>`);
    try {
      const r = await get(`/api/runs/${encodeURIComponent(id)}?db=${S.db}`);
      const c = r.client || {}, rec = r.recommendation || {};
      const why = Object.fromEntries((rec.rationale || []).map((x) => [x.ref, x.text]));
      const res = [...(r.results || [])].sort((a, b) => (a.passed === b.passed ? 0 : a.passed ? 1 : -1));
      const up = rec.profile_updates || {};
      const updates = [
        ...(up.goals_add || []).map((g) => `Add ${g.type} goal for ${g.target_year}`),
        up.monthly_contribution != null ? `Set monthly contribution to $${Number(up.monthly_contribution).toLocaleString()}` : null,
        up.risk_score != null ? `Change risk score to ${up.risk_score}` : null,
        ...(rec.flags || []).map((f) => `Flag for review: ${String(f).replace(/_/g, " ")}`),
      ].filter(Boolean);
      openSheet(`
        <h3 id="sheet-title">${esc(c.name || r.case_id)}</h3>
        <p class="sub">${esc(r.case_id)}, playbook v${esc(r.playbook_version)}, ${esc(r.set)} set, model ${esc(r.model || "unknown")}</p>
        <div class="kv">
          <div><span>Score</span><b class="${r.passed ? "ok" : "bad"}">${pct(r.score)}</b></div>
          <div><span>Result</span><b class="${r.passed ? "ok" : "bad"}">${r.passed ? "Passed" : "Failed"}</b></div>
          <div><span>Turns</span><b>${esc(r.turns ?? "–")}</b></div>
          <div><span>Tokens</span><b>${fmtTok((r.tokens_in || 0) + (r.tokens_out || 0))}</b></div>
          <div><span>Time</span><b>${esc(r.seconds ?? "–")}s</b></div>
        </div>
        ${r.error ? `<p class="errbox">${esc(r.error)}</p>` : ""}
        <h4>Client</h4>
        ${c.client_id ? `<p class="sub">Age ${esc(c.age ?? "–")}, risk score ${esc(c.risk_score ?? "–")}${c.occupation ? `, ${esc(c.occupation)}` : ""}</p>
          <p style="margin-top:8px">${(c.events || []).map((e) => `<span class="chip">${esc(String(e.type).replace(/_/g, " "))}${e.date ? ` on ${esc(e.date)}` : ""}</span>`).join(" ") || `<span class="sub">No new life events.</span>`}</p>`
          : `<p class="sub">This client's profile isn't in ${esc(S.db)} yet. It's written when a test set finishes.</p>`}
        <h4>Policy checker, rule by rule</h4>
        ${res.length ? `<table class="rules"><thead><tr><th>Rule</th><th>Severity</th><th>Result</th><th>Detail</th></tr></thead><tbody>
          ${res.map((x) => `<tr class="${x.passed ? "" : "f"}"><td>${esc(x.rule)}</td><td>${esc(x.severity)}</td><td>${x.passed ? `<span class="ok">Pass</span>` : `<span class="bad">Fail</span>`}</td><td>${esc(x.detail || "")}</td></tr>`).join("")}
        </tbody></table>` : `<p class="sub">No rule results on this run.</p>`}
        <h4>Recommendation</h4>
        ${r.recommendation ? `${(rec.trades || []).length ? `<ul class="trades">${rec.trades.map((t) => `<li><span class="act ${esc(t.action)}">${t.action === "sell" ? "Sell" : "Buy"}</span><span>${esc(t.symbol)}</span>
            <span class="amt">$${Number(t.amount_usd).toLocaleString()}</span><span class="why">${esc(t.reason_ref)}${why[t.reason_ref] ? `: ${esc(why[t.reason_ref])}` : ""}</span></li>`).join("")}</ul>`
            : `<p class="sub">No trades. ${esc(rec.no_action_reason || "")}</p>`}
          ${updates.length ? `<ul class="plain">${updates.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
          ${rec.target_allocation ? `<p class="sub" style="margin-top:8px">Target: ${Object.entries(rec.target_allocation).map(([k, v]) => `${esc(k)} ${pct(v)}%`).join(", ")}</p>` : ""}`
          : `<p class="sub">The agent didn't produce a recommendation.</p>`}
        <h4>Agent trace</h4>
        ${(r.steps || []).length ? `<ol class="trace">${r.steps.map((s) => s.kind === "say"
          ? `<li class="say"><span class="tn"><span class="tag">Said</span>Turn ${esc(s.turn)}</span><p>${esc(s.text)}</p></li>`
          : `<li class="tool ${s.error ? "e" : ""}"><span class="tn"><span class="tag">${s.error ? "Tool error" : "Tool"}</span>Turn ${esc(s.turn)}</span><b>${esc(s.tool)}</b><code>${esc(s.args)}</code>${s.result ? `<details><summary>Result</summary><pre>${esc(s.result)}</pre></details>` : ""}</li>`).join("")}</ol>`
          : `<p class="sub">No trace steps recorded for this run.</p>`}`);
    } catch (e) {
      openSheet(`<h3 id="sheet-title">Run didn't load</h3><p class="sub">${esc(e.message)}. Close this and try again.</p>`);
    }
  }
  async function openVersion(v) {
    openSheet(`<p>Loading playbook v${esc(v)}.</p>`);
    try {
      const d = await get(`/api/live/versions/${v}?db=${S.db}`);
      const g = d.generations[d.generations.length - 1];
      const row = (k) => (g && g[k] ? `<tr><td>${k}</td><td>${pct(g[k].mean_score)}</td><td>${pct(g[k].pass_rate)}%</td></tr>` : "");
      const lines = d.parent == null ? [] : d.diff.filter((l) => !l.startsWith("---") && !l.startsWith("+++"));
      openSheet(`
        <h3 id="sheet-title">Playbook v${esc(d.version)}</h3>
        <p class="sub">${esc(d.status || "")}${d.parent != null ? `, child of v${esc(d.parent)}` : ", the baseline"}. ${esc(d.changelog || "")}</p>
        ${g ? `<h4>Gate metrics</h4><table class="rules"><thead><tr><th>Set</th><th>Mean score</th><th>Pass rate</th></tr></thead><tbody>${row("practice")}${row("test")}${row("regression")}</tbody></table>
          <div class="kv" style="margin-top:12px"><div><span>Decision</span><b class="${g.decision === "shipped" ? "ok" : "bad"}">${esc(g.decision)}</b></div><div class="wide"><span>Reason</span><b>${esc(g.reason || "")}</b></div></div>
          ${g.compliance ? `<p class="${g.compliance.verdict === "approve" ? "okbox" : "errbox"}">Compliance (${esc(g.compliance.reviewer || "gemini")}): ${esc(g.compliance.verdict)}. ${esc(g.compliance.note || "")}</p>` : ""}`
          : `<p class="sub" style="margin-top:12px">No gate metrics yet. They're written when this version finishes its test and regression sets.</p>`}
        ${lines.length ? `<h4>Diff vs v${esc(d.parent)}</h4><pre class="diff">${lines.map((l) => { const c = l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "@" ? "hunk" : "ctx"; return `<span class="${c}">${esc(c === "hunk" ? "…" : l.slice(1)) || " "}</span>`; }).join("")}</pre>` : ""}
        <details class="yaml"><summary>Full playbook YAML</summary><pre class="diff">${esc(d.yaml || "")}</pre></details>`);
    } catch (e) {
      openSheet(`<h3 id="sheet-title">Version didn't load</h3><p class="sub">${esc(e.message)}. Close this and try again.</p>`);
    }
  }

  function setDb(db) {
    S.db = db; S.session = null; S.since = null; S.runs.clear(); S.log = []; S.lastAt = null; S.seen = new Set(); S.gates = new Map();
    $("#gates").innerHTML = `<tbody><tr><td class="muted">No life events in the last 24 hours.</td></tr></tbody>`;
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.db === db));
    $("#log").innerHTML = ""; $("#blocks").innerHTML = "";
    const u = new URL(location); u.searchParams.set("db", db); history.replaceState(null, "", u);
    poll();
  }

  $("#blocks").addEventListener("click", (e) => { const b = e.target.closest("button[data-run]"); if (b) openRun(b.dataset.run); });
  $("#ver-list").addEventListener("click", (e) => { const b = e.target.closest("button[data-v]"); if (b) openVersion(b.dataset.v); });
  $("#sheet-close").addEventListener("click", () => $("#sheet").close());
  $("#sheet").addEventListener("close", () => { if (/^#(run|v)-/.test(location.hash)) history.replaceState(null, "", location.pathname + location.search); });
  const _openRun = openRun, _openVersion = openVersion;
  openRun = (id) => { history.replaceState(null, "", `${location.pathname}${location.search}#run-${id}`); return _openRun(id); };
  openVersion = (v) => { history.replaceState(null, "", `${location.pathname}${location.search}#v-${v}`); return _openVersion(v); };
  const deep = /^#run-(.+)$/.exec(location.hash), deepV = /^#v-(\d+)$/.exec(location.hash);
  if (deep) openRun(decodeURIComponent(deep[1]));
  else if (deepV) openVersion(deepV[1]);
  $("#sheet").addEventListener("click", (e) => { if (e.target === $("#sheet")) $("#sheet").close(); });
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => setDb(b.dataset.db)));
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.db === S.db));
  poll();
  S.timer = setInterval(() => { if (!document.hidden) poll(); }, 3000);
  setInterval(renderStatus, 10000);
})();
