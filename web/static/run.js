/* ballast. "Run it": launch agent jobs on the Fly runner, stream their steps, replay past runs. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MODEL = { "meta/muse-spark-1.3": "Muse Spark 1.3", "subq/subq-preview": "SubQ Preview", "google/gemini-3.8-flash": "Gemini 3.8 Flash" };
  const mname = (m) => MODEL[m] || String(m || "").replace(/^meta\//, "");
  const clip = (s, n = 220) => { s = String(s ?? ""); return s.length > n ? s.slice(0, n) + "…" : s; };
  let CASES = [];
  // benchmarked seconds per case, so the race bar fills at each model's real pace
  const PACE = { "meta/muse-spark-1.3": 40, "subq/subq-preview": 23, "google/gemini-3.8-flash": 30 };
  let race = null;

  async function get(p) { const r = await fetch(p); if (!r.ok) { let m = `${r.status}`; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); } return r.json(); }

  // ---------- terminal column: shared by live runs and replays ----------
  function column(meta) {
    const box = document.createElement("article");
    box.className = "term frame";
    box.innerHTML = `
      <header class="t-head">
        <span class="t-mode ${meta.replay ? "rep" : "live"}">${meta.replay ? "Replay" : "Live"}</span>
        <b>${esc(mname(meta.model))}</b><span class="mono">${esc(meta.case || "")}</span>
        <span class="t-stat mono" data-k="status">${esc(meta.status || "queued")}</span>
      </header>
      <div class="t-meter mono"><span>turn <b data-k="turn">0</b></span><span><b data-k="secs">0.0</b> s</span><span><b data-k="nsteps">0</b> steps</span>${meta.replay ? `<span class="t-ctl"><button type="button" class="btn small" data-k="speed" aria-pressed="false">4x</button><button type="button" class="btn small" data-k="skip">Skip</button></span>` : ""}</div>
      ${meta.race ? `<div class="race" aria-hidden="true"><span class="rbar" data-k="rbar"></span><span class="rtk"></span></div><div class="race-k mono"><span>pace ~${PACE[meta.model] ?? "-"} s / case</span><span data-k="place"></span></div>` : ""}
      <ol class="t-lines" aria-live="off"></ol>
      <div class="t-verdict" hidden></div>`;
    const el = (k) => box.querySelector(`[data-k="${k}"]`);
    let n = 0, lastTurn = -1;
    return {
      box,
      status(s) { const e = el("status"); e.textContent = s; e.dataset.s = s; },
      secs(x) { el("secs").textContent = Number(x).toFixed(1); },
      step(s) {
        n++; el("nsteps").textContent = n;
        if (s.turn != null && s.turn !== lastTurn) { lastTurn = s.turn; el("turn").textContent = s.turn; }
        const li = document.createElement("li");
        li.className = s.kind === "say" ? "say" : s.error ? "tool err" : "tool";
        li.innerHTML = s.kind === "say"
          ? `<span class="tn">t${String(s.turn ?? 0).padStart(2, "0")}</span><span class="tk">said</span><span class="tx">${esc(clip(s.text, 600))}</span>`
          : `<span class="tn">t${String(s.turn ?? 0).padStart(2, "0")}</span><span class="tk">${esc(s.tool || "tool")}</span><span class="tx"><code>${esc(clip(s.args, 200))}</code>${s.result ? `<span class="tr">${esc(clip(s.result, 260))}</span>` : ""}</span>`;
        const ol = box.querySelector(".t-lines");
        ol.appendChild(li);
        ol.scrollTop = ol.scrollHeight;
      },
      verdict(r) { const v = box.querySelector(".t-verdict"); v.hidden = false; v.innerHTML = verdictHTML(r); },
      el,
    };
  }
  function verdictHTML(r) {
    if (!r) return `<p class="muted">No result.</p>`;
    const c = r.check || {}, rec = r.recommendation || {}, b = r.backtest || {};
    const why = Object.fromEntries((rec.rationale || []).map((x) => [x.ref, x.text]));
    const res = [...(c.results || [])].sort((a, z) => (a.passed === z.passed ? 0 : a.passed ? 1 : -1));
    return `
      <div class="v-top"><span class="v-score ${c.passed ? "pos" : "neg"}">${c.score != null ? Number(c.score).toFixed(3) : "-"}</span>
        <span class="v-pass ${c.passed ? "pos" : "neg"}">${c.passed ? "✓ PASSED" : "✕ FAILED"}</span>
        <span class="mono muted">${r.turns ?? "-"} turns, ${((r.tokens_in || 0) + (r.tokens_out || 0)).toLocaleString("en-US")} tokens, ${r.seconds != null ? Number(r.seconds).toFixed(1) : "-"} s</span></div>
      ${r.error ? `<p class="errbox">${esc(r.error)}</p>` : ""}
      ${res.length ? `<table class="rules v-rules"><tbody>${res.map((x) => `<tr class="${x.passed ? "" : "f"}"><td>${esc(x.rule)}</td><td>${x.passed ? `<span class="ok">✓</span>` : `<span class="bad">✕</span>`}</td><td>${esc(x.detail || "")}</td></tr>`).join("")}</tbody></table>` : ""}
      ${(rec.trades || []).length ? `<ul class="trades">${rec.trades.map((t) => `<li><span class="act ${esc(t.action)}">${t.action === "sell" ? "▼ Sell" : "▲ Buy"}</span><span class="sym">${esc(t.symbol)}</span><span class="amt">$${Number(t.amount_usd).toLocaleString("en-US")}</span><span class="why"><span class="mono">${esc(t.reason_ref)}</span>${why[t.reason_ref] ? `: ${esc(clip(why[t.reason_ref], 180))}` : ""}</span></li>`).join("")}</ul>`
        : rec.no_action_reason ? `<p class="muted">No trades: ${esc(rec.no_action_reason)}</p>` : ""}
      ${b && b.months ? `<dl class="v-bt">
        <div><dt>12-mo return</dt><dd class="${b.forward_return < 0 ? "neg" : "pos"}">${(b.forward_return * 100).toFixed(1)}%</dd></div>
        <div><dt>max drawdown</dt><dd>${(b.max_drawdown * 100).toFixed(1)}%</dd></div>
        <div><dt>min cash</dt><dd class="${b.emergency_fund_breached ? "neg" : ""}">${Number(b.min_cash_coverage_months).toFixed(2)} mo</dd></div>
        <div><dt>forced sales</dt><dd class="${b.forced_sale_usd ? "neg" : ""}">$${Math.round(b.forced_sale_usd || 0).toLocaleString("en-US")}</dd></div>
        <div><dt>vs hold</dt><dd>${b.vs_hold_return != null ? ((b.vs_hold_return >= 0 ? "+" : "−") + Math.abs(b.vs_hold_return * 100).toFixed(1) + "%") : "-"}</dd></div></dl>` : ""}`;
  }

  // ---------- live job polling ----------
  function watchJob(jobId, model, caseId, racing) {
    const col = column({ model, case: caseId, status: "queued", race: racing });
    $("#runcols").appendChild(col.box);
    const entry = { model, col, done: false, score: null, secs: null };
    if (racing) race.push(entry);
    let seen = 0, t0 = null;
    const setBar = (f) => { const b = col.el("rbar"); if (b) b.style.transform = `scaleX(${Math.max(0, Math.min(1, f)).toFixed(3)})`; };
    const timer = setInterval(async () => {
      let j;
      try { j = await get(`/api/jobs/${jobId}`); } catch (e) { col.status(`error: ${e.message}`); return; }
      col.status(j.status);
      if (j.started_at && !t0) t0 = Date.parse(j.started_at);
      if (t0 && (j.status === "running" || j.status === "claimed")) {
        const el = (Date.now() - t0) / 1000;
        col.secs(el);
        if (racing) setBar(Math.min(0.97, el / (PACE[model] || 30)));
      }
      (j.steps || []).slice(seen).forEach((s) => col.step(s));
      seen = (j.steps || []).length;
      if (j.status === "done" || j.status === "error") {
        clearInterval(timer);
        if (j.result) { col.secs(j.result.seconds || 0); col.verdict(j.result); }
        else col.verdict({ error: j.error || "The worker reported an error." });
        if (racing) {
          setBar(1);
          entry.done = true; entry.score = j.result?.check?.score ?? null; entry.secs = j.result?.seconds ?? null;
          const place = race.filter((x) => x.done).length;
          col.el("place").innerHTML = `<b class="${place === 1 ? "pos" : ""}">${place === 1 ? "▲ finished first" : `finished #${place}`}</b> ${entry.secs != null ? `${Number(entry.secs).toFixed(1)} s` : ""}`;
          if (place === 1) col.box.classList.add("first");
          if (race.every((x) => x.done)) {
            // accuracy is judged separately from speed
            const best = Math.max(...race.map((x) => x.score ?? -1));
            const top = race.filter((x) => x.score === best && best >= 0);
            top.forEach((x) => { x.col.box.classList.add("accurate"); x.col.el("place").innerHTML += ` <b class="acc">◆ ${top.length > 1 ? "tied on accuracy" : "most accurate"} ${best.toFixed(3)}</b>`; });
          }
        }
        loadJobs();
      }
    }, 1500);
  }

  // ---------- replay ----------
  function replay(src) {
    $("#runcols").innerHTML = "";
    const col = column({ ...src, replay: true, status: "replaying" });
    $("#runcols").appendChild(col.box);
    $("#run-it").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    const steps = src.steps || [];
    let i = 0, speed = 1, clock = 0, stopped = false;
    const scale = src.result && src.result.seconds && steps.length ? Math.min(4, Math.max(0.6, src.result.seconds / steps.length)) : 1.2;
    const finish = () => { if (stopped) return; stopped = true; while (i < steps.length) col.step(steps[i++]); col.secs(src.result?.seconds || clock); col.status("done"); col.verdict(src.result); };
    const tick = () => {
      if (stopped) return;
      if (i >= steps.length) return finish();
      const s = steps[i++];
      col.step(s);
      const d = (s.kind === "say" ? 1.1 : 0.8) * scale;  // seconds of "agent time" this step represents
      clock += d; col.secs(clock);
      setTimeout(tick, (d * 1000) / speed / 2.5);
    };
    col.el("speed").addEventListener("click", (e) => { speed = speed === 1 ? 4 : 1; e.currentTarget.setAttribute("aria-pressed", speed === 4); });
    col.el("skip").addEventListener("click", finish);
    setTimeout(tick, 400);
  }
  const runToSource = (r) => ({
    model: r.model, case: r.case_id, steps: r.steps || [],
    result: { check: { score: r.score, passed: r.passed, violations: r.violations, results: r.results }, recommendation: r.recommendation,
              backtest: r.backtest, turns: r.turns, tokens_in: r.tokens_in, tokens_out: r.tokens_out, seconds: r.seconds, model: r.model, error: r.error },
  });
  window.ballastVerdict = verdictHTML;
  window.ballastPickCase = (c) => { $("#rf-filter").value = ""; fillCases(); $("#rf-case").value = c; onCase(); $("#run-it").scrollIntoView({ behavior: "smooth" }); };
  window.ballastReplay = async (kind, id, db) => {
    try {
      if (kind === "job") { const j = await get(`/api/jobs/${encodeURIComponent(id)}`); replay({ model: j.model, case: j.case, steps: j.steps || [], result: j.result }); }
      else { const r = await get(`/api/runs/${encodeURIComponent(id)}${db ? `?db=${db}` : ""}`); replay(runToSource(r)); }
    } catch (e) { $("#rf-msg").textContent = `Replay didn't load: ${e.message}`; }
  };

  // ---------- job history ----------
  async function loadJobs() {
    let js;
    try { js = await get("/api/jobs?limit=20"); } catch (e) { $("#jobl").innerHTML = `<li class="muted">Can't read jobs: ${esc(e.message)}</li>`; return; }
    $("#jobl").innerHTML = js.length ? js.map((j) => `<li>
      <span class="mono muted">${esc(String(j.created_at || "").slice(11, 19))}</span>
      <span class="mono">${esc(j.case)}</span><span>${esc(mname(j.model))}</span>
      <span class="chipx s-${esc(j.status)}">${esc(j.status)}</span>
      <span class="mono ${j.passed ? "pos" : j.passed === false ? "neg" : "muted"}">${j.score != null ? Number(j.score).toFixed(3) : "-"}</span>
      <button class="btn small" data-job="${esc(j.job_id)}" ${j.status === "done" || j.status === "error" ? "" : "disabled"}>Replay</button></li>`).join("")
      : `<li class="muted">No runs yet. Start one above.</li>`;
  }

  // ---------- form ----------
  function fillCases(q = "") {
    q = q.trim().toLowerCase();
    const hit = CASES.filter((c) => !q || c.case.includes(q) || (c.name || "").toLowerCase().includes(q) || (c.events || []).join(" ").includes(q));
    const groups = [...new Set(hit.map((c) => c.group))];
    const cur = $("#rf-case").value;
    $("#rf-case").innerHTML = groups.map((g) => `<optgroup label="${esc(g)}">${hit.filter((c) => c.group === g).map((c) => `<option value="${esc(c.case)}">${esc(c.case)}${c.events.length ? `  (${esc(c.events.join(", ").replace(/_/g, " "))})` : ""}</option>`).join("")}</optgroup>`).join("");
    if (hit.some((c) => c.case === cur)) $("#rf-case").value = cur;
    onCase();
  }
  async function onCase() {
    const c = CASES.find((x) => x.case === $("#rf-case").value);
    $("#rf-prev").innerHTML = c ? `${c.name ? `${esc(c.name)}, ` : ""}age ${esc(c.age)}, risk ${esc(c.risk)}, $${Number(c.value || 0).toLocaleString("en-US")}<br>cash <b class="${c.cash_months != null && c.cash_months < 3 ? "neg" : ""}">${c.cash_months ?? "-"} mo</b>, events: ${c.events.length ? esc(c.events.join(", ").replace(/_/g, " ")) : "none"}, as of ${esc(c.as_of || "-")}` : "No case matches the filter.";
    const jr = c && c.journey;
    let vs = [];
    try { vs = await get(`/api/playbook_versions${jr ? `?journey=${jr}` : ""}`); } catch (_) { vs = []; }
    $("#rf-pb").innerHTML = `<option value="">v0, the generic playbook</option>` + vs.filter((v) => v.version !== 0).map((v) => `<option value="${v.version}">v${v.version}${jr ? ` (${jr})` : ""}, ${esc(v.status || "")}</option>`).join("");
  }
  async function submit(e) {
    e.preventDefault();
    const models = [...document.querySelectorAll('#runf input[name="m"]:checked')].map((x) => x.value);
    const msg = $("#rf-msg");
    if (!models.length) { msg.textContent = "Pick at least one model."; return; }
    const pass = $("#rf-pass").value;
    try { sessionStorage.setItem("ballast-pass", pass); } catch (_) { /* private mode */ }
    $("#rf-go").disabled = true; msg.textContent = "Queueing.";
    try {
      const r = await fetch("/api/run", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ case: $("#rf-case").value, models, playbook_version: $("#rf-pb").value || null, passcode: pass }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || r.status);
      $("#runcols").innerHTML = "";
      race = [];
      d.job_ids.forEach((id, k) => watchJob(id, models[k], $("#rf-case").value, models.length > 1));
      msg.textContent = `Queued ${d.job_ids.length} ${d.job_ids.length === 1 ? "run" : "runs"} on the Fly runner.`;
      loadJobs();
    } catch (err) { msg.textContent = `Run didn't start: ${err.message}`; }
    finally { $("#rf-go").disabled = false; }
  }

  async function init() {
    try { const p = sessionStorage.getItem("ballast-pass"); if (p) $("#rf-pass").value = p; } catch (_) { /* private mode */ }
    try { CASES = await get("/api/cases"); } catch (_) { CASES = []; }
    fillCases();
    $("#rf-filter").addEventListener("input", (e) => fillCases(e.target.value));
    $("#rf-case").addEventListener("change", onCase);
    $("#rf-both").addEventListener("click", (e) => {
      document.querySelectorAll('#runf input[name="m"]').forEach((x) => (x.checked = x.value === "meta/muse-spark-1.3" || x.value === "subq/subq-preview"));
      submit(e);
    });
    $("#runf").addEventListener("submit", submit);
    try { (await get("/api/benchmark")).forEach((r) => { const id = r.model === "muse" ? "meta/muse-spark-1.3" : r.model === "subq" ? "subq/subq-preview" : null; if (id && r.seconds) PACE[id] = Math.round(r.seconds); }); } catch (_) { /* keep defaults */ }
    $("#jobl").addEventListener("click", (e) => { const b = e.target.closest("button[data-job]"); if (b) window.ballastReplay("job", b.dataset.job); });
    loadJobs();
    setInterval(() => { if (!document.hidden) loadJobs(); }, 10000);
    const m = /^#replay-(run|job)-(.+)$/.exec(location.hash);
    if (m) window.ballastReplay(m[1], decodeURIComponent(m[2]));
  }
  init();
})();
