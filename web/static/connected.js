/* ballast. connected client data: the connector feeds, what the agent checked, what it found vs the truth. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clip = (s, n = 180) => { s = String(s ?? ""); return s.length > n ? s.slice(0, n) + "…" : s; };
  // rows that usually carry the signal: stopped pay, benefits, care, tuition, blackout, babies, raises, debt
  const TELL = /(unemploy|cobra|severance|final pay|last pay|terminat|layoff|laid off|wind[- ]?down|blackout|insider|restricted|defer|home care|care\b|caregiv|tuition|twins|expecting|pregnan|baby|nursery|raise|promotion|merit increase|salary increase|overdue|late fee|minimum payment|cash advance)/i;
  const SYN = {
    layoff: ["layoff", "laid off", "job loss", "lost her job", "lost his job", "unemploy", "wind-down", "wind down", "terminat", "severance", "cobra", "paychecks stop", "income stopped"],
    job_change: ["raise", "promotion", "new job", "higher income", "income increase", "salary increase", "pay increase"],
    child: ["child", "baby", "babies", "twins", "expecting", "pregnan", "newborn"],
    marriage: ["marri", "wedding", "spouse"], divorce: ["divorc"], inheritance: ["inherit"],
    market_drop: ["market drop", "crash", "drawdown"],
    shutdown: ["wind-down", "wind down", "shutdown", "shut down", "desk closure", "role eliminat", "severance", "layoff", "job loss"],
    blackout: ["blackout", "insider", "restricted", "trading window"],
    care: ["care", "caregiv", "mother", "mom", "parent", "dependent", "assisted"],
    tuition: ["tuition", "education", "college", "school"],
  };
  const keywords = (ev) => {
    const t = String(ev.type || "").toLowerCase();
    const extra = Object.entries(SYN).filter(([k]) => t.includes(k)).flatMap(([, v]) => v);
    const own = t.split(/[_\s-]+/).filter((w) => w.length > 3);
    const det = JSON.stringify(ev.details || {}).toLowerCase();
    const hints = [/care/.test(t + det) && ["care", "mother", "mom", "parent", "dependent"], /tuition|education/.test(t + det) && ["tuition", "education"],
      /blackout|insider|restricted/.test(t + det) && ["blackout", "insider", "restricted"], /defer|bonus/.test(t + det) && ["defer", "bonus"],
      /credit|debt|card/.test(t + det) && ["credit", "card", "debt", "balance"]].filter(Boolean).flat();
    return [...new Set([...extra, ...own, ...hints])];
  };
  const rowsOf = (x) => Array.isArray(x) ? x : x && typeof x === "object" ? (Object.values(x).find(Array.isArray) || null) : null;
  const scalarsOf = (x) => x && typeof x === "object" && !Array.isArray(x) ? Object.entries(x).filter(([, v]) => v == null || typeof v !== "object") : [];
  const money = (v) => typeof v === "number" ? `${v < 0 ? "−" : "+"}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 2 })}` : esc(v);

  // a connector file is an object of scalars, nested objects and lists: show scalars + flattened objects as a key grid, each list as its own ledger
  function feedTable(name, data) {
    if (Array.isArray(data)) return listTable("", data);
    if (!data || typeof data !== "object") return `<p class="muted">No data.</p>`;
    const kv = [], lists = [];
    const walk = (obj, pre) => Object.entries(obj).forEach(([k, v]) => {
      const key = pre ? `${pre} ${k}` : k;
      if (Array.isArray(v)) { if (v.length && typeof v[0] === "object") lists.push([key, v]); else kv.push([key, v.length ? v.join(", ") : "none"]); }
      else if (v && typeof v === "object") walk(v, key);
      else kv.push([key, v]);
    });
    walk(data, "");
    let html = kv.length ? `<dl class="ckv">${kv.map(([k, v]) => `<div class="${TELL.test(`${k} ${v}`) ? "tell" : ""}"><dt>${esc(k.replace(/_/g, " "))}</dt><dd class="mono">${typeof v === "number" && /salary|bonus|amount|balance|pay|limit/.test(k) ? `$${v.toLocaleString("en-US")}` : esc(v)}</dd></div>`).join("")}</dl>` : "";
    lists.forEach(([k, v]) => { html += listTable(k, v); });
    return html || `<p class="muted">No data.</p>`;
  }
  function listTable(title, rows) {
    let html = "";
    if (rows.length) {
      const obj = rows.filter((r) => r && typeof r === "object");
      const keys = [...new Set(obj.flatMap((r) => Object.keys(r)))].filter((k) => !/^id$/.test(k)).slice(0, 5);
      const dateK = keys.find((k) => /date|day|when|due|start/.test(k));
      const sorted = dateK ? [...obj].sort((a, b) => String(b[dateK]).localeCompare(String(a[dateK]))) : obj;
      const tells = sorted.filter((r) => TELL.test(JSON.stringify(r))).length;
      html += `<p class="cmeta mono">${title ? `${esc(title.replace(/_/g, " "))}: ` : ""}${rows.length} rows${tells ? `, <b class="gold">${tells} flagged</b>` : ""}</p>
        <div class="cscroll"><table class="rules ctab"><thead><tr>${keys.map((k) => `<th class="${/amount|balance|gross|net|value|pay|limit/.test(k) ? "r" : ""}">${esc(k.replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>
        ${sorted.map((r) => `<tr class="${TELL.test(JSON.stringify(r)) ? "tell" : ""}">${keys.map((k) => { const v = r[k]; const num = typeof v === "number";
          return `<td class="${num ? "r mono" : ""} ${num && v < 0 ? "neg" : ""}">${num && /amount|pay|gross|net|deposit/.test(k) ? money(v) : num ? v.toLocaleString("en-US") : esc(clip(typeof v === "object" ? JSON.stringify(v) : v, 120))}</td>`; }).join("")}</tr>`).join("")}
        </tbody></table></div>`;
    }
    return html;
  }

  function trail(steps) {
    const calls = [];
    // a step can query several sources (chained bash) or read connector files directly; count every one
    (steps || []).forEach((s) => {
      if (s.kind !== "tool") return;
      const a = String(s.args || "");
      const srcs = [...a.matchAll(/clientdata\.py\s+([a-z_]+)/gi), ...a.matchAll(/connectors\/([a-z_]+)\.json/gi)].map((m) => m[1].toLowerCase());
      [...new Set(srcs)].forEach((src) => calls.push({ src, turn: s.turn, result: s.result, error: s.error, via: /connectors\//.test(a) && !/clientdata/.test(a) ? "read" : "clientdata.py" }));
    });
    return calls;
  }

  function agentText(job) {
    const r = (job && job.result) || {}, rec = r.recommendation || {};
    return [...(job?.steps || []).filter((s) => s.kind === "say").map((s) => s.text),
      ...(rec.rationale || []).map((x) => `${x.ref} ${x.text}`), ...(rec.flags || []), ...(rec.trades || []).map((t) => t.reason_ref),
      JSON.stringify(rec.profile_updates || {}), JSON.stringify(rec.inferred_events || rec.detected_events || [])].join(" \n ");
  }

  // v0 (generic playbook) vs v1 (Muse's rewrite after reading the v0 failures on connected clients)
  function learnHTML(L) {
    if (!L || !(L.v0 || L.v1)) return "";
    const ck = (j) => (j && j.check) || {};
    const side = (k, j) => { const ch = ck(j);
      return `<div class="lv"><p class="mono muted csm">${k}</p>${j ? `<p class="lv-n ${ch.passed ? "pos" : "neg"}">${ch.score != null ? Number(ch.score).toFixed(3) : "—"}</p><p class="mono csm ${ch.passed ? "pos" : "neg"}">${ch.passed ? "✓ passed" : "✕ failed"}</p>
        ${(ch.violations || []).map((x) => `<p class="lv-viol mono">✕ ${esc(x.rule)}${x.detail ? `: ${esc(clip(x.detail, 140))}` : ""}</p>`).join("") || `<p class="mono muted csm">no violations</p>`}
        <button class="btn small" type="button" data-rj="${esc(j.job_id)}">Replay</button>` : `<p class="muted">Not run yet.</p>`}</div>`; };
    const r0 = new Set((ck(L.v0).violations || []).map((x) => x.rule)), r1 = new Set((ck(L.v1).violations || []).map((x) => x.rule));
    const gone = [...r0].filter((r) => !r1.has(r)), added = [...r1].filter((r) => !r0.has(r));
    const s0 = ck(L.v0).score, s1 = ck(L.v1).score;
    const d = s0 != null && s1 != null ? s1 - s0 : null;
    const lessons = L.lessons || [];
    return `<section class="panel a-gap clearn"><h3 class="panel-h">What it learned: v0 → v1</h3>
      <p class="muted csm">Muse read the v0 failures on connected clients and rewrote the playbook once. Gemini reviewed it${L.compliance && L.compliance.approved === false ? " and flagged it" : ""}. Same client, same data, re-run on v1.</p>
      ${L.changelog ? `<p class="csm lnote"><span class="mono muted">v1 changelog</span> ${esc(typeof L.changelog === "string" ? L.changelog : JSON.stringify(L.changelog))}</p>` : ""}
      <div class="lgrid">${side("v0, generic playbook", L.v0)}<div class="larrow mono ${d == null ? "muted" : d > 0 ? "pos" : d < 0 ? "neg" : "muted"}">${d == null ? "→" : d === 0 ? "= 0.000" : `${d > 0 ? "▲ +" : "▼ −"}${Math.abs(d).toFixed(3)}`}</div>${side("v1, after learning", L.v1)}</div>
      ${gone.length ? `<p class="mono pos csm lnote">✓ Gone on v1: ${gone.map(esc).join(", ")}</p>` : ""}${added.length ? `<p class="mono neg csm lnote">✕ New on v1: ${added.map(esc).join(", ")}</p>` : ""}
      ${lessons.length ? `<p class="cmeta mono">Lessons in v1 that target this client</p><ul class="llist">${lessons.map((l) => `<li><p class="mono csm"><span class="chip">${esc(l.triggered_by || "any event")}</span> <span class="chip">${esc(l.rule || "")}</span>${l.skill ? ` <span class="muted">skill ${esc(l.skill)}</span>` : ""}</p>
        <p>${esc(l.lesson || "")}</p>${l.root_cause ? `<p class="muted csm">Root cause: ${esc(l.root_cause)}</p>` : ""}</li>`).join("")}</ul>`
        : `<p class="muted csm lnote">No v1 lesson targets this client's events or its v0 violations.${d != null && d < 0 ? " The drop comes from the shared playbook rewrite, not from a lesson about this client. The ship gate exists to catch this." : ""}</p>`}
    </section>`;
  }

  async function show(id) {
    const v = $("#cview");
    v.innerHTML = `<p class="muted">Loading ${esc(id)}.</p>`;
    let c;
    try { c = await (await fetch(`/api/connected/${encodeURIComponent(id)}`)).json(); } catch (e) { v.innerHTML = `<p class="muted">Couldn't load ${esc(id)}: ${esc(e.message)}</p>`; return; }
    const cl = c.client || {}, job = c.job, conn = c.connectors || {};
    const calls = trail(job?.steps);
    const checked = new Set(calls.map((x) => x.src).filter((x) => x !== "sources"));
    const text = agentText(job).toLowerCase();
    const truth = (c.truth || []).map((ev) => { const ks = keywords(ev); const hit = ks.find((k) => text.includes(k.toLowerCase())); return { ev, hit }; });
    const found = truth.filter((t) => t.hit).length;
    v.innerHTML = `
      <div class="chead frame">
        <div><p class="jname">${esc(cl.name || c.id)}, ${esc(cl.age ?? "")}</p><p class="muted">${esc(cl.occupation || "")}${cl.risk_score ? `, risk ${esc(cl.risk_score)}` : ""}. <span class="mono">${esc(c.case)}</span></p>
          <p class="cnote mono">events.json is hidden from the agent. It only sees: ${Object.keys(conn).map((k) => `<span class="chip">${esc(k)}</span>`).join(" ")}</p></div>
        <dl class="jscore"><div><dt>Found by the agent</dt><dd><span class="${job ? (found === truth.length ? "pos" : "neg") : ""}">${job ? `${found}/${truth.length}` : "—"}</span> real events</dd>
          <dd><span>${job ? `${checked.size}/${Object.keys(conn).length}` : "—"}</span> sources checked</dd>
          <dd><span class="${job?.result?.check?.passed ? "pos" : "neg"}">${job?.result?.check?.score != null ? Number(job.result.check.score).toFixed(3) : "—"}</span> score</dd></div></dl>
      </div>
      <div class="cwall">${Object.entries(conn).map(([k, d]) => `<section class="panel cfeed ${checked.has(k) ? "checked" : ""}"><h3 class="panel-h">${esc(k)}${job ? (checked.has(k) ? ` <span class="ok mono csm">✓ checked</span>` : ` <span class="muted mono csm">not checked</span>`) : ""}</h3>${feedTable(k, d)}</section>`).join("")}</div>
      <div class="a-two a-gap">
        <section class="panel"><h3 class="panel-h">What the agent checked</h3>
          ${calls.length ? `<ol class="ctrail">${calls.map((x, i) => `<li><span class="mono cn">${String(i + 1).padStart(2, "0")}</span><div><b class="mono">${x.via === "read" ? `read connectors/${esc(x.src)}.json` : `clientdata.py ${esc(x.src)}`}</b> <span class="muted mono">turn ${esc(x.turn)}</span>${x.result ? `<pre>${esc(clip(x.result, 300))}</pre>` : ""}</div></li>`).join("")}</ol>`
            : `<p class="muted">${job ? "The agent didn't call clientdata.py in this run." : "Not run yet."}</p>`}
        </section>
        <section class="panel"><h3 class="panel-h">What it found vs what happened</h3>
          <ul class="cfound">${truth.map((t) => `<li class="${t.hit ? "hit" : "miss"}"><span class="g">${job ? (t.hit ? "✓" : "✕") : "·"}</span><div><b class="mono">${esc(t.ev.type)}</b> <span class="muted mono">${esc(t.ev.date || "")}</span>
            <p class="muted">${esc(clip(JSON.stringify(t.ev.details || {}), 160))}</p>${job ? `<p class="cev">${t.hit ? `found: agent mentioned "${esc(t.hit)}"` : "not mentioned by the agent"}</p>` : ""}</div></li>`).join("") || `<li class="muted">No truth events.</li>`}</ul>
          <p class="muted csm" style="margin-top:8px">Truth comes from the hidden events.json the grader uses; matching is by keyword in what the agent said, cited and flagged.</p>
        </section>
      </div>
      ${learnHTML(c.learn)}
      <section class="panel a-gap"><h3 class="panel-h">Verdict</h3>
        ${job ? `${window.ballastVerdict ? window.ballastVerdict(job.result) : ""}<p style="margin-top:12px"><button class="btn small primary" type="button" id="c-replay">Replay this run</button> <span class="muted mono csm">${esc(job.model || "")}, ${esc(job.job_id)}</span></p>`
          : `<p class="muted">Not run yet.</p><p style="margin-top:10px"><button class="btn small primary" type="button" id="c-run">Pick this client in Run it</button></p>`}
      </section>`;
    $("#c-replay")?.addEventListener("click", () => window.ballastReplay && window.ballastReplay("job", job.job_id));
    v.querySelectorAll("button[data-rj]").forEach((b) => b.addEventListener("click", () => window.ballastReplay && window.ballastReplay("job", b.dataset.rj)));
    $("#c-run")?.addEventListener("click", () => window.ballastPickCase && window.ballastPickCase(c.case));
  }

  async function init() {
    let list = [];
    try { list = await (await fetch("/api/connected")).json(); } catch (_) { list = []; }
    if (!list.length) { $("#cview").innerHTML = `<p class="muted">No connected clients in this build yet.</p>`; return; }
    const pick = $("#cpick");
    pick.innerHTML = list.map((c, i) => `<button data-id="${esc(c.id)}" aria-pressed="${i === 0}">${esc(c.name || c.id)}<span>${esc(c.id)}${c.job && c.job.score != null ? ` ${Number(c.job.score).toFixed(2)}` : ""}</span></button>`).join("");
    pick.onclick = (e) => { const b = e.target.closest("button[data-id]"); if (!b) return; pick.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b)); show(b.dataset.id); };
    const m = /#connected-(cx-\d+)/.exec(location.hash);
    const first = m ? m[1] : list[0].id;
    pick.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.id === first));
    show(first);
  }
  init();
})();
