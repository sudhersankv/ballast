/* ballast. v3: genome replay, loop diagram, exploded stack. Vanilla JS, no build. Colors come from CSS tokens. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => Math.round(x * 100);
  const sd = (x, d = 3) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x).toFixed(d)}`;
  const signed = (n, unit = "") => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n)}${unit}`;
  const arrow = (n) => (n > 0 ? "▲" : n < 0 ? "▼" : "■");
  const fmtTok = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
  const HARD = new Set(["valid_output", "risk_band", "emergency_fund", "concentration", "cited"]);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DEMO = new URLSearchParams(location.search).get("demo") === "1";
  const tok = (n) => getComputedStyle(document.documentElement).getPropertyValue(`--${n}`).trim();

  const state = { steps: [], i: 0, versions: [], drift: [], analysis: [], lineage: {}, playing: null };

  async function get(p) {
    const r = await fetch(DEMO ? `${p}${p.includes("?") ? "&" : "?"}demo=1` : p);
    if (!r.ok) throw new Error(`${p} returned ${r.status}`);
    return r.json();
  }
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }
  const C = 0.866, S = 0.5;
  const iso = (ox, oy, x, y, z) => [ox + (x - y) * C, oy + (x + y) * S - z];
  const pts = (arr) => arr.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
  function box(ox, oy, x, y, z, a, b, t) {
    return {
      top: [iso(ox, oy, x, y, z + t), iso(ox, oy, x + a, y, z + t), iso(ox, oy, x + a, y + b, z + t), iso(ox, oy, x, y + b, z + t)],
      left: [iso(ox, oy, x, y + b, z), iso(ox, oy, x + a, y + b, z), iso(ox, oy, x + a, y + b, z + t), iso(ox, oy, x, y + b, z + t)],
      right: [iso(ox, oy, x + a, y, z), iso(ox, oy, x + a, y + b, z), iso(ox, oy, x + a, y + b, z + t), iso(ox, oy, x + a, y, z + t)],
    };
  }

  // ---------- step model ----------
  function buildSteps(versions, drift, analysis) {
    const byV = Object.fromEntries(versions.map((g) => [g.version, g]));
    const base = byV[0] || versions[0];
    const evs = [
      ...versions.map((g) => ({ t: g.created_at, type: "gen", g })),
      ...drift.filter((d) => d.action !== "none").map((d) => ({ t: d.time, type: "drift", d })),
      ...analysis.map((a) => ({ t: a.time, type: "analysis", a })),
    ].sort((a, b) => String(a.t).localeCompare(String(b.t)));
    let light = "green", live = null, lastAnalysis = null, lastDrift = null;
    const seen = [];
    const steps = [];
    for (const e of evs) {
      const s = { light };
      if (e.type === "gen") {
        const g = e.g, p = byV[g.parent], score = g.test.mean_score;
        Object.assign(s, { version: g.version, genome: g.version, score, scoreLabel: "average policy score on unseen clients",
          delta: base && g.version !== base.version ? { v: score - base.test.mean_score, label: "vs v0" } : null });
        seen.push(g.version);
        if (g.parent == null) {
          Object.assign(s, { kind: "base", label: `v${g.version} baseline`, title: `v${g.version}: the starting playbook`,
            body: "The advisory team's first playbook: read the case, rebalance to target. It has no habits for life events. On a layoff it rebalanced to normal targets and left about 2.7 months of cash where 6 were needed.",
            gate: gateBaseline(g), stamp: ["Baseline", "hold"], mut: { mode: "base" } });
          live = g.version;
        } else if (g.decision === "rejected") {
          const blocked = g.compliance && g.compliance.verdict === "block";
          Object.assign(s, { kind: "reject", label: `v${g.version} blocked`, title: `v${g.version} doesn't survive`,
            body: blocked ? `Muse proposed: "${g.changelog}" Gemini's compliance review blocked it. ${g.compliance.note}` : `Muse proposed: "${g.changelog}" It failed the gate: ${g.reason}.`,
            gate: gateTraining(g, p), stamp: ["Rejected", "block"], tone: "alarm", strand: "rejected", mut: { mode: "gen" } });
        } else if (g.mode === "drift") {
          Object.assign(s, { kind: "ship", label: `v${g.version} fix`, title: `v${g.version} fixes the drift`,
            body: `${g.changelog} It must pass every drifted case and the full regression set before it serves clients.`,
            gate: gateDriftFix(g), stamp: ["Shipped", "ship"], tone: "good", mut: { mode: "fix", drift: lastDrift, analysis: lastAnalysis } });
          if (light === "red") s.light = "yellow";
          live = g.version;
        } else {
          const from = p ? p.test.mean_score.toFixed(3) : null;
          const lead = /layoff/i.test(g.changelog) ? "Muse read the layoff failures and wrote a layoff skill: raise cash to 6 months of expenses first, then rebalance. " : `${g.changelog} `;
          Object.assign(s, { kind: "ship", label: `v${g.version} ships`, title: `v${g.version} ships`,
            body: `${lead}${from != null ? `On unseen clients the score goes from ${from} to ${score.toFixed(3)}.` : ""}`,
            gate: gateTraining(g, p), stamp: ["Shipped", "ship"], tone: "good", mut: { mode: "gen" } });
          live = g.version;
        }
      } else if (e.type === "analysis") {
        const a = e.a, top = a.patterns[0];
        lastAnalysis = a;
        Object.assign(s, { kind: "subq", label: "SubQ reads lineage", title: `SubQ reads all ${a.runs_read} runs at once`,
          body: `${a.summary} Worst pattern: ${top.condition}, which fails ${top.rule} ${pct(top.failure_rate)}% of the time.`,
          genome: live, version: live, score: top.failure_rate, scoreLabel: `of runs fail ${top.rule} in that pattern`, tone: "subq",
          gate: gateAnalysis(a), stamp: ["Diagnosed", "subq"], scan: true, mut: { mode: "subq", analysis: a } });
      } else if (e.d.action === "event_gate") {
        // SubQ Snap decision gate: early warning before the agent runs; the rule checker stays the source of truth
        const d = e.d, gt = (d.gates || []).find((x) => x.rerun_now) || (d.gates || [])[0];
        if (!gt) continue;
        const [rule, p] = Object.entries(gt.rule_risk || {}).sort((a, b) => b[1] - a[1])[0] || ["none", 0];
        Object.assign(s, { kind: "subq", label: "Snap flags an event", title: "A life event arrives, Snap flags it",
          body: `${gt.case_id} reports a ${gt.event.replace("_", " ")}. Before the agent runs, SubQ Snap scores it against the live playbook in ${gt.seconds.toFixed(1)}s: ${rule} is at risk (${p.toFixed(2)}) and the playbook covers this event with probability ${gt.covered.toFixed(2)}. ${gt.rerun_now ? "Decision: re-run this client first." : "Decision: no re-run needed."}`,
          version: live, genome: live, score: p, scoreText: (p * 100).toFixed(1), scoreLabel: `chance ${rule} fails without a re-run`, tone: "subq",
          gate: [chk("info", "Rule at risk", rule.replace(/_/g, " "), `${rule}, p ${p.toFixed(3)}`), chk("info", "Playbook covers it", gt.covered.toFixed(2), `p that v${live} already handles a ${gt.event.replace("_", " ")}`),
            chk(!gt.rerun_now, "Decision", gt.rerun_now ? "Re-run now" : "No re-run", `urgency ${gt.urgency} of 3, ${gt.seconds.toFixed(1)}s, ${fmtTok(gt.input_tokens)} tokens`)],
          stamp: [gt.rerun_now ? "Re-run" : "Clear", "subq"], snapGate: gt, mut: { mode: "snap", gate: gt, gates: d.gates } });
      } else {
        const d = e.d, n = (d.case_ids || []).length;
        lastDrift = d;
        Object.assign(s, { version: d.to_version, genome: d.to_version, score: d.rolling_score, scoreLabel: "rolling score on recent live cases",
          delta: { v: d.rolling_score - d.baseline, label: "vs shipped baseline" } });
        light = d.level; s.light = light;
        if (d.action === "rollback") {
          Object.assign(s, { kind: "red", label: "Drift caught", title: "Drift caught, rolled back",
            body: `Conditions changed under v${d.from_version}: ${n} live cases broke rules it always passed. The light turns red and ballast. puts v${d.to_version}, the last healthy genome, back in service.`,
            gate: gateContain(d), stamp: ["Rolled back", "block"], tone: "alarm", env: true, revertFrom: d.from_version, snapWindow: d.snap || null, mut: { mode: "rollback", drift: d } });
          live = d.to_version;
        } else if (d.action === "realign") {
          Object.assign(s, { kind: "muse", label: "Muse drafts a fix", title: "Muse drafts a fix",
            body: `The ${n} drifted cases become tests. Muse writes a fix from ${lastAnalysis ? "SubQ's diagnosis" : "the violations"}. It has 3 attempts before a person takes over.`,
            gate: gateRealign(d, lastAnalysis), stamp: ["Fixing", "muse"], tone: "alarm", env: true, draftOf: null, mut: { mode: "realign", drift: d, analysis: lastAnalysis } });
        } else if (d.action === "shipped_fix") {
          const g = byV[d.to_version];
          Object.assign(s, { kind: "green", label: "Aligned", title: "Aligned again",
            body: `v${d.to_version} serves every client. The rolling score is ${pct(d.rolling_score)}, against a baseline of ${pct(d.baseline)}. The drift became a skill the agent keeps.`,
            gate: g ? gateDriftFix(g) : gateRealign(d), stamp: ["Aligned", "ship"], tone: "good", mut: { mode: "fix", drift: lastDrift, analysis: lastAnalysis, version: d.to_version } });
          live = d.to_version;
        } else if (d.action === "escalated") {
          Object.assign(s, { kind: "red", label: "Escalated", title: "Escalated to an advisor",
            body: `Muse couldn't produce a passing fix in 3 attempts. v${d.to_version} keeps serving clients and an advisor is notified.`,
            gate: gateRealign(d), stamp: ["Escalated", "block"], tone: "alarm", mut: { mode: "rollback", drift: d } });
        } else {
          Object.assign(s, { kind: d.level === "red" ? "red" : "muse", label: `Drift ${d.level}`, title: `Drift light: ${d.level}`,
            body: `Rolling score ${pct(d.rolling_score)} against a baseline of ${pct(d.baseline)}.`, gate: gateRealign(d), stamp: ["Watching", "hold"], mut: { mode: "rollback", drift: d } });
        }
      }
      s.seen = [...seen];
      s.live = live;
      s.chartVersions = new Set(seen);
      s.driftSeen = steps.some((x) => x.kind === "red") || s.kind === "red";
      steps.push(s);
    }
    // the realign step drafts whatever the next drift-mode version becomes
    steps.forEach((s, k) => { if (s.kind === "muse") { const nx = steps.slice(k).find((x) => x.mut?.mode === "fix"); if (nx) s.draftOf = nx.version ?? nx.mut.version; } });
    // nothing is invented: stages with no real event yet are shown as pending
    const last = steps[steps.length - 1];
    const pend = (label, title, body) => steps.push({ kind: "pending", label, title, body, score: null, scoreLabel: "no real event yet", light: last ? last.light : "green",
      gate: [chk(null, "Detect", "—", "waiting for a real event"), chk(null, "Contain", "—", ""), chk(null, "Realign", "—", "")], stamp: ["Pending", "hold"],
      version: last?.live ?? null, genome: last?.live ?? null, live: last?.live ?? null, seen: last ? last.seen : [], chartVersions: last ? last.chartVersions : new Set(),
      driftSeen: false, mut: { mode: "pending" } });
    if (steps.length && !drift.some((d) => d.action === "rollback")) pend("Drift: pending", "Drift: no real drift event yet",
      "The drift loop runs when the live playbook starts failing rules it used to pass. Nothing has drifted in this run yet, so there is no rollback, SubQ diagnosis or fix to show. This step fills in from the real drift_events the moment one lands.");
    return steps;
  }

  const chk = (ok, k, v, n) => ({ ok, k, v, n });
  const cv = (c) => (c ? (c.verdict === "approve" ? "Approved" : "Blocked") : "Skipped");
  function gateBaseline(g) {
    return [chk(null, "Beats parent on unseen clients", "Baseline", "every upgrade must beat this"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "clients that must always pass"),
      chk(null, "Gemini compliance review", "Not needed", "nothing changed yet")];
  }
  function gateTraining(g, p) {
    const gain = p ? g.test.mean_score - p.test.mean_score : 0, c = g.compliance;
    return [chk(gain >= 0.02, "Beats parent, unseen clients", `${arrow(gain)} ${sd(gain)}`, `${p ? p.test.mean_score.toFixed(3) : "-"} → ${g.test.mean_score.toFixed(3)}, needs +0.020`),
      regHold(g, p),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", cv(c), c ? c.note : "")];
  }
  // the regression gate: an upgrade must hold its parent's regression pass rate (no lost ground)
  function regHold(g, p) {
    const floor = p ? p.regression.pass_rate : g.regression.pass_rate;
    return chk(g.regression.pass_rate >= floor, "Regression held", `${g.regression.pass_rate.toFixed(2)}`, `pass rate; parent ${floor.toFixed(2)}, must not drop`);
  }
  function gateDriftFix(g) {
    const m = /(\d+)\/(\d+)/.exec(g.reason || ""), c = g.compliance;
    const p = state.versions.find((x) => x.version === g.parent);
    return [chk(true, "Passes the drifted cases", m ? `${m[1]} of ${m[2]}` : "Passed", "now part of the test set"),
      regHold(g, p),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", cv(c), c ? c.note : "")];
  }
  function gateContain(d) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || ""),
      chk(true, "Contain", `Back to v${d.to_version}`, `v${d.from_version} out of service`),
      chk(true, "Capture", `${(d.case_ids || []).length} cases`, "added to the test set")];
  }
  function gateAnalysis(a) {
    return [chk("info", "Runs read", `${a.runs_read}`, `plus ${a.client_timelines} client timelines and ${a.playbook_versions} versions`),
      chk("info", "Context in one pass", `${fmtTok(a.tokens_read)} tokens`, "no chunking, no retrieval"),
      chk("info", "Patterns found", `${a.patterns.length}`, "sent to Muse with example traces")];
  }
  function gateRealign(d, a) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || "no new violations"),
      chk(a ? "info" : true, a ? "Diagnose" : "Contain", a ? `${a.patterns.length} patterns` : `v${d.to_version} live`, a ? "from SubQ's long-context pass" : "last healthy playbook"),
      chk(null, "Realign", "Attempt 1 of 3", "then an advisor steps in")];
  }

  // ---------- genome model ----------
  function genomeFor(s) {
    // -> { pairs: [{key, name, kind, state}], strand }
    const L = state.lineage;
    const g = L[s.genome];
    if (!g) return { pairs: [], strand: "ship" };
    const muts = g.mutations || { added: [], removed: [], edited: [] };
    const stateOf = (key) => (muts.added.some((m) => m.key === key) ? "add" : muts.edited.some((m) => m.key === key) ? "edit" : "keep");
    let pairs = g.elements.map((e) => ({ key: e.key, name: e.name, kind: e.kind, state: s.mut?.mode === "gen" || s.mut?.mode === "fix" ? stateOf(e.key) : "keep" }));
    if (s.mut?.mode === "gen" || s.mut?.mode === "fix") muts.removed.forEach((m) => pairs.push({ key: m.key, name: m.name, kind: m.kind, state: "del" }));
    if (s.revertFrom != null && L[s.revertFrom]) {
      // rollback: the drifted genome's extra pairs are reverted
      const have = new Set(g.elements.map((e) => e.key));
      L[s.revertFrom].elements.filter((e) => !have.has(e.key)).forEach((e) => pairs.push({ key: e.key, name: e.name, kind: e.kind, state: "del", note: "reverted" }));
    }
    if (s.draftOf != null && L[s.draftOf]) {
      const have = new Set(g.elements.map((e) => e.key));
      L[s.draftOf].elements.filter((e) => !have.has(e.key)).forEach((e) => pairs.push({ key: e.key, name: e.name, kind: e.kind, state: "draft" }));
    }
    // keep max_turns last
    pairs.sort((a, b) => (a.kind === "limit") - (b.kind === "limit"));
    return { pairs, strand: s.strand || (s.kind === "red" ? "env" : "ship") };
  }

  // ---------- render: genome = rule radar + genome lattice ----------
  const RULES = [["valid_output", "valid"], ["risk_band", "risk band"], ["emergency_fund", "cash buffer"], ["concentration", "concentr."], ["cited", "cited"],
    ["no_churn", "no churn"], ["event_child", "child"], ["event_marriage", "marriage"], ["event_job_change", "job change"], ["glidepath", "glidepath"]];
  // share of this version's test runs that pass the rule (test sets run 3x per version in the real loop)
  const passRate = (v, rule) => { const g = state.versions.find((x) => x.version === v); if (!g) return null; const n = g.test_runs || 20; return Math.max(0, 1 - ((g.violations_by_rule || {})[rule] || 0) / n); };
  function renderGenome(s) {
    renderRadar(s);
    renderLattice(s);
    const { pairs } = genomeFor(s);
    const glyph = { keep: "·", add: "+", edit: "~", del: "−", draft: "+" };
    const word = { keep: "kept", add: "added", edit: "edited", del: "removed", draft: "draft" };
    $("#pairs").innerHTML = pairs.filter((p) => p.state !== "keep").map((p) => `<li class="${p.state}"><b aria-hidden="true">${glyph[p.state]}</b>${esc(p.name)}<span class="sr">, ${word[p.state]}${p.note ? `, ${esc(p.note)}` : ""}</span>${p.note ? ` <span>(${esc(p.note)})</span>` : ""}</li>`).join("");
    renderRail(s);
  }
  function renderRadar(s) {
    // each version is a polygon over the 10 policy rules; radius = pass rate on 20 unseen clients (0.50 center, 1.00 rim)
    const svg = $("#radar");
    svg.innerHTML = "";
    svg.setAttribute("viewBox", "-22 0 404 340");
    const cx = 180, cy = 172, R = 112, N = RULES.length;
    const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / N;
    const pt = (i, v) => { const r = R * Math.max(0, Math.min(1, (v - 0.5) / 0.5)); return [cx + r * Math.cos(ang(i)), cy + r * Math.sin(ang(i))]; };
    [0.6, 0.7, 0.8, 0.9, 1.0].forEach((t) => {
      el("polygon", { points: pts(RULES.map((_, i) => pt(i, t))), fill: "none", stroke: tok(t === 1 ? "text-3" : "rim"), "stroke-width": t === 1 ? 1 : 0.75 }, svg);
      const [x, y] = pt(0, t);
      el("text", { x: x + 4, y: y + 3 }, svg).textContent = t.toFixed(1);
    });
    RULES.forEach(([rule, short], i) => {
      const [x, y] = pt(i, 1.0);
      el("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: tok("rim"), "stroke-width": 0.75 }, svg);
      const [lx, ly] = [cx + (R + 16) * Math.cos(ang(i)), cy + (R + 16) * Math.sin(ang(i))];
      const t = el("text", { x: lx, y: ly + 3, "text-anchor": Math.abs(Math.cos(ang(i))) < 0.2 ? "middle" : Math.cos(ang(i)) > 0 ? "start" : "end", class: "axis-l" }, svg);
      t.textContent = short;
    });
    const seen = s.seen.filter((v) => state.versions.some((g) => g.version === v));
    const cur = s.genome ?? s.version;
    seen.filter((v) => v !== cur).forEach((v) => {
      el("polygon", { points: pts(RULES.map(([r], i) => pt(i, passRate(v, r)))), fill: "none", stroke: tok("text-3"), "stroke-width": 0.75, "stroke-opacity": 0.6 }, svg);
    });
    if (cur != null && passRate(cur, "valid_output") != null) {
      const rej = state.versions.find((g) => g.version === cur)?.decision === "rejected";
      const c = tok(rej ? "gold" : "mint");
      const P = RULES.map(([r], i) => pt(i, passRate(cur, r)));
      el("polygon", { points: pts(P), fill: c, "fill-opacity": 0.12, stroke: c, "stroke-width": 1.75, "stroke-dasharray": rej ? "5 3" : "" }, svg);
      P.forEach(([x, y], i) => {
        const v = passRate(cur, RULES[i][0]);
        el("rect", { x: x - 2.5, y: y - 2.5, width: 5, height: 5, fill: c }, svg);
        if (v < 1) { const t = el("text", { x: x + 5, y: y - 4, fill: tok("text") }, svg); t.textContent = v.toFixed(2); }
      });
    }
    // drift: the rules that broke on live cases, marked on the rim
    (s.mut?.drift?.violations || []).forEach((x) => {
      const i = RULES.findIndex(([r]) => r === x.rule); if (i < 0) return;
      const [px, py] = pt(i, 1.0);
      el("path", { d: `M${px - 6},${py - 6}L${px + 6},${py + 6}M${px + 6},${py - 6}L${px - 6},${py + 6}`, stroke: tok("red"), "stroke-width": 2 }, svg);
    });
    // SubQ: failure rate inside each pattern, plotted as pass rate
    (s.mut?.analysis && (s.kind === "subq" || s.kind === "muse") ? s.mut.analysis.patterns : []).forEach((p) => {
      const i = RULES.findIndex(([r]) => r === p.rule); if (i < 0) return;
      const [px, py] = pt(i, 1 - p.failure_rate);
      el("rect", { x: px - 4, y: py - 4, width: 8, height: 8, fill: "none", stroke: tok("subq"), "stroke-width": 1.5, transform: `rotate(45 ${px} ${py})` }, svg);
      const t = el("text", { x: px + 7, y: py + 3, fill: tok("subq") }, svg); t.textContent = (1 - p.failure_rate).toFixed(2);
    });
    el("text", { x: 4, y: 334 }, svg).textContent = `v${cur ?? "-"} filled, earlier versions outlined`;
  }
  function renderLattice(s) {
    // versions are columns, playbook elements are rows; each pair carries a number
    const svg = $("#lattice");
    svg.innerHTML = "";
    const L = state.lineage;
    const cols = s.seen.filter((v) => L[v]);
    const { pairs } = genomeFor(s);
    if (s.draftOf != null && L[s.draftOf]) cols.push("draft");
    const rowsMap = new Map();
    const addRow = (e) => { if (!rowsMap.has(e.key)) rowsMap.set(e.key, { key: e.key, name: e.kind === "limit" ? "max_turns" : e.name, kind: e.kind }); };
    cols.forEach((v) => (v === "draft" ? L[s.draftOf] : L[v]).elements.forEach(addRow));
    pairs.forEach(addRow);
    const rows = [...rowsMap.values()].sort((a, b) => (a.kind === "limit") - (b.kind === "limit") || (a.kind === "prompt" ? -1 : b.kind === "prompt" ? 1 : 0));
    const x0 = 112, top = 30, W = 360, H = 320;
    const vbH = Math.round(Math.max(180, top + Math.min(26, (H - top) / Math.max(1, rowsMap.size)) * rowsMap.size + 34));
    svg.setAttribute("viewBox", `0 0 360 ${vbH}`);
    const cw = Math.min(42, (W - x0 - 6) / Math.max(1, cols.length)), rh = Math.min(26, (H - top) / Math.max(1, rows.length));
    const d = Math.min(cw, rh) * 0.42;
    const curIdx = cols.indexOf(s.genome);
    if (curIdx >= 0) el("rect", { x: x0 + curIdx * cw, y: top - 22, width: cw, height: rows.length * rh + 22, fill: tok("panel"), stroke: tok("text-3"), "stroke-width": 0.75 }, svg);
    const numFor = (v, row) => {
      const g = v === "draft" ? L[s.draftOf] : L[v];
      const e = g.elements.find((x) => x.key === row.key);
      if (!e) return null;
      if (row.kind === "limit") return e.body;
      if (row.kind === "prompt") return String(e.body.split("\n").filter(Boolean).length);
      return String((g.lessons || []).filter((l) => l.skill === e.name).length);
    };
    cols.forEach((v, c) => {
      const x = x0 + c * cw + cw / 2;
      const rej = v !== "draft" && L[v].status === "rejected";
      const t = el("text", { x, y: top - 8, "text-anchor": "middle", fill: tok(v === s.genome ? "text" : rej ? "gold" : "text-3") }, svg);
      t.textContent = v === "draft" ? "draft" : `${rej ? "✕" : ""}v${v}`;
    });
    rows.forEach((row, r) => {
      const y = top + r * rh + rh / 2;
      const name = row.name.length > 16 ? row.name.slice(0, 15) + "…" : row.name;
      el("text", { x: x0 - 8, y: y + 3.5, "text-anchor": "end" }, svg).textContent = name;
      let prev = null;
      cols.forEach((v, c) => {
        const x = x0 + c * cw + cw / 2, n = numFor(v, row);
        const isCur = v === s.genome, isDraft = v === "draft";
        const st = isCur ? (pairs.find((p) => p.key === row.key)?.state || (n == null ? null : "keep")) : isDraft ? (n != null && !(L[s.genome]?.elements || []).some((e) => e.key === row.key) ? "draft" : n != null ? "keep" : null) : n != null ? "keep" : null;
        if (prev && st && st !== "del") el("line", { x1: prev + d, y1: y, x2: x - d, y2: y, stroke: tok("rim"), "stroke-width": 1 }, svg);
        if (!st) { el("line", { x1: x - 2, y1: y, x2: x + 2, y2: y, stroke: tok("rim") }, svg); prev = null; return; }
        const color = { keep: isCur ? "text-2" : "rim", add: "mint", edit: "gold", del: "red", draft: "muse" }[st];
        el("polygon", { points: `${x},${y - d} ${x + d},${y} ${x},${y + d} ${x - d},${y}`, fill: st === "keep" ? tok(isCur ? "panel-2" : "deep") : tok(color), "fill-opacity": st === "del" || st === "draft" ? 0.15 : 1,
          stroke: tok(color), "stroke-width": st === "keep" ? 0.75 : 1.25, "stroke-dasharray": st === "del" || st === "draft" ? "3 2" : "" }, svg);
        const num = st === "del" ? "−" : n ?? "";
        const t = el("text", { x, y: y + 3.5, "text-anchor": "middle", class: "n", fill: tok(st === "keep" || st === "del" || st === "draft" ? (isCur || isDraft ? "text" : "text-3") : "on-accent") }, svg);
        t.textContent = num;
        prev = st === "del" ? null : x;
      });
    });
    el("text", { x: 4, y: vbH - 6 }, svg).textContent = "numbers: lessons carried, prompt lines, turn budget";
  }
  function renderRail(s) {
    const vs = Object.values(state.lineage).sort((a, b) => a.version - b.version);
    $("#rail").classList.toggle("scan", !!s.scan);
    $("#rail").innerHTML = vs.map((g) => {
      const seen = s.seen.includes(g.version);
      const m = g.mutations, cnt = m.added.length + m.edited.length + m.removed.length;
      const st = !seen ? "future" : g.status === "rolled_back" ? (s.driftSeen ? "rolled_back" : "shipped") : g.status;
      const cur = g.version === s.genome;
      const glyph = st === "rejected" ? "✕" : st === "rolled_back" ? "↺" : "";
      return `<li><button data-v="${g.version}" class="${st}" aria-current="${cur}" aria-label="Playbook v${g.version}, ${esc(g.status)}${cnt ? `, ${cnt} mutations` : ""}">${glyph ? `${glyph} ` : ""}v${g.version}${cnt ? `<span>${m.added.length ? `+${m.added.length}` : ""}${m.edited.length ? ` ~${m.edited.length}` : ""}${m.removed.length ? ` −${m.removed.length}` : ""}</span>` : ""}</button></li>`;
    }).join("");
  }

  // ---------- render: mutation strip ----------
  function li(kind, g, t, n, d) {
    return `<li class="k-${kind}"><span class="g" aria-hidden="true">${g}</span><span class="t">${esc(t)}</span><span class="n">${n ?? ""}</span>${d ? `<span class="d">${esc(d)}</span>` : ""}</li>`;
  }
  const firstLine = (s) => String(s || "").split("\n").map((x) => x.trim()).filter(Boolean)[0] || "";
  function addedLine(before, after) {
    const b = new Set(String(before || "").split("\n").map((x) => x.trim()));
    return String(after || "").split("\n").map((x) => x.trim()).filter((x) => x && !b.has(x))[0] || firstLine(after);
  }
  // SubQ Snap: probabilities as bars, numbers right-aligned, next to the rule checker's verdict
  const bar = (label, p, color, note) => `<li><span class="sl mono">${esc(label)}</span><span class="sb"><span style="width:${Math.max(1, p * 100).toFixed(1)}%;background:var(--${color})"></span></span><span class="sn">${p.toFixed(3)}</span>${note ? `<span class="sx">${esc(note)}</span>` : ""}</li>`;
  function renderSnap(s) {
    const box = $("#mut-snap");
    const gt = s.snapGate, w = s.snapWindow;
    if (!gt && !w) { box.hidden = true; return; }
    box.hidden = false;
    if (gt) {
      const risks = Object.entries(gt.rule_risk || {}).sort((a, b) => b[1] - a[1]);
      box.innerHTML = `<div class="snap-head"><h4>SubQ Snap decision gate</h4><span class="mono">${esc(gt.model || "subq-snap-1.1")}</span></div>
        <div class="snap-cols"><div><p class="snap-k">Rule risk for <span class="mono">${esc(gt.case_id)}</span>, ${esc(gt.event.replace("_", " "))}</p><ul class="snap-bars">${risks.map(([r, p]) => bar(r, p, p >= 0.5 ? "red" : "text-3")).join("")}</ul></div>
        <div><p class="snap-k">Does the live playbook cover this event?</p><ul class="snap-bars">${bar("covered", gt.covered, gt.covered >= 0.5 ? "mint" : "red", gt.covered < 0.5 ? "not covered" : "covered")}</ul>
        <p class="snap-verdict ${gt.rerun_now ? "neg" : "pos"}">${gt.rerun_now ? "▲ Re-run this client now" : "■ No re-run needed"}, urgency ${gt.urgency} of 3</p></div></div>
        <p class="snap-cal">Calibrated against the rule checker: gate F1 0.94 (precision 0.98, recall 0.90) over 39 events, about 0.8s and 1.4K tokens a call. The rules stay the source of truth; Snap is the early warning.</p>`;
    } else {
      const lv = w.level_p || {};
      box.innerHTML = `<div class="snap-head"><h4>Second opinion: SubQ Snap</h4><span class="mono">${esc(w.model || "subq-snap-1.1")}</span></div>
        <div class="snap-cols"><div><p class="snap-k">Window level</p><ul class="snap-bars">${bar("green", lv.green || 0, "mint")}${bar("yellow", lv.yellow || 0, "gold")}${bar("red", lv.red || 0, "red")}</ul></div>
        <div><p class="snap-k">Severity</p><ul class="snap-bars">${bar("rollback", w.rollback_p || 0, "red")}${bar(w.rule || "rule", w.rule_p || 0, "red", "rule named")}${bar("new condition", w.novel_p || 0, "subq", (w.novel_p || 0) >= 0.5 ? "not forgetting" : "forgetting")}</ul></div></div>
        <p class="snap-verdict ${w.agrees ? "pos" : "neg"}">${w.agrees ? "✓ Agrees" : "✕ Disagrees"} with the rule checker: Snap says ${esc(w.level)}, rules say ${esc(w.rule_level)}.</p>
        <p class="snap-cal">On 14 of 14 windows Snap agreed with the rule checker, and it named the failing rule on 6 of 6 red windows.</p>`;
    }
  }
  function renderMut(s) {
    if (s.mut?.mode === "pending") {
      $("#mut-ex").hidden = true; renderSnap({});
      ["#mut-why", "#mut-what", "#mut-learned"].forEach((k) => ($(k).innerHTML = `<p class="muted">Pending. No real drift event yet.</p>`));
      return;
    }
    const L = state.lineage, why = $("#mut-why"), what = $("#mut-what"), learned = $("#mut-learned"), ex = $("#mut-ex");
    ex.hidden = true;
    renderSnap(s);
    const none = (t) => `<p class="muted">${esc(t)}</p>`;
    const mode = s.mut?.mode;
    const g = L[s.genome];
    const mutList = (m) => {
      const rows = [
        ...m.added.map((x) => li("add", "+", x.name, x.kind, x.desc || firstLine(x.body))),
        ...m.edited.map((x) => li("edit", "~", x.name, x.kind, x.kind === "limit" ? `${x.before} → ${x.body}` : addedLine(x.before, x.body))),
        ...m.removed.map((x) => li("del", "−", x.name, x.kind, x.desc || firstLine(x.body))),
      ];
      return rows.length ? `<ul>${rows.join("")}</ul>` : none("No playbook changes.");
    };
    const learnedList = (lg, scoreBefore, scoreAfter) => {
      const rows = (lg.rules || []).filter((r) => r.before !== r.after).slice(0, 4).map((r) => {
        const dn = r.after - r.before;
        return li(dn < 0 ? "add" : "del", dn < 0 ? "▼" : "▲", r.rule, `${r.before} → ${r.after}`, `${dn < 0 ? "fewer" : "more"} unseen clients failing (${HARD.has(r.rule) ? "hard" : "soft"} rule)`);
      });
      if (scoreBefore != null && scoreAfter != null) {
        const d = scoreAfter - scoreBefore;
        rows.unshift(li(d >= 0 ? "add" : "del", d >= 0 ? "▲" : "▼", "Average score", `${scoreBefore.toFixed(3)} → ${scoreAfter.toFixed(3)}`, `${sd(d)} on ${lg.cases || 20} unseen clients`));
      }
      return rows.length ? `<ul>${rows.join("")}</ul>` : none("No measurable change on unseen clients.");
    };
    if (mode === "base" && g) {
      const lg = g.learned;
      why.innerHTML = none("Starting point. The advisory team wrote it by hand.");
      what.innerHTML = `<ul>${g.elements.map((x) => li("keep", "·", x.name, x.kind, x.desc || firstLine(x.body))).join("")}</ul>`;
      const rows = (lg.rules || []).filter((r) => r.after > 0).slice(0, 4).map((r) => li("del", "✕", r.rule, `${r.after} of ${lg.cases}`, "unseen clients failing"));
      learned.innerHTML = rows.length ? `<ul>${rows.join("")}</ul>` : none("No failures on unseen clients.");
    } else if ((mode === "gen") && g) {
      why.innerHTML = g.why.length ? `<ul>${g.why.map((w) => li("why", "✕", w.rule, `${w.count} of ${w.total}`, w.example)).join("")}</ul><p class="muted" style="margin-top:10px">v${g.parent} on ${g.why_set} clients, the only set Muse sees.</p>` : none("No parent failures recorded.");
      // lead with what the agent learned (its own words); the skill diff is the mechanism underneath
      const lessonRows = (g.lessons_added || []).map((l) => `<li class="k-${s.kind === "reject" ? "del" : "add"} lesson-li"><span class="g" aria-hidden="true">${s.kind === "reject" ? "✕" : "+"}</span><span class="t">${esc(l.lesson)}</span><span class="n mono">${esc(l.rule)}</span><span class="d">in skill <span class="mono">${esc(l.skill)}</span>, from ${esc(l.triggered_by)}</span></li>`).join("");
      what.innerHTML = (lessonRows ? `<ul>${lessonRows}</ul><p class="muted sub-h">Playbook changes</p>` : "") + mutList(g.mutations);
      if (s.kind === "reject") {
        const gt = g.gate || {}, c = gt.compliance;
        learned.innerHTML = `<ul>${li("del", "✕", "Didn't survive", "", gt.reason || "failed the gate")}${c ? li(c.verdict === "approve" ? "add" : "del", c.verdict === "approve" ? "✓" : "✕", "Gemini review", cv(c), c.note) : ""}${gt.regression ? (() => { const pr = state.versions.find((x) => x.version === g.parent)?.regression?.pass_rate ?? 1; const ok = gt.regression.pass_rate >= pr;
          return li(ok ? "add" : "del", ok ? "✓" : "✕", "Regression held", `${pr.toFixed(2)} → ${gt.regression.pass_rate.toFixed(2)}`, "pass rate must not drop below the parent"); })() : ""}</ul>`;
      } else {
        // the gate's generation metrics are the authoritative scores; per-run means are a fallback
        const gv = state.versions.find((x) => x.version === g.version), gp = state.versions.find((x) => x.version === g.parent);
        learned.innerHTML = learnedList(g.learned, gp ? gp.test.mean_score : g.learned.score_before, gv ? gv.test.mean_score : g.learned.score_after);
        const e = g.learned.example;
        if (e) { ex.hidden = false; ex.innerHTML = `<b>${esc(e.case_id)}</b><span>${esc(e.rule)} on an unseen client</span><b>before, v${g.parent}</b><span class="before">✕ ${esc(e.before)}</span><b>after, v${g.version}</b><span class="after">✓ ${esc(e.after)}</span>`; }
      }
    } else if (mode === "rollback") {
      const d = s.mut.drift;
      why.innerHTML = `<ul>${d.violations.map((v) => li("why", "✕", v.rule, v.severity, v.detail)).join("")}</ul>`;
      const from = L[d.from_version], to = L[d.to_version];
      const lost = from && to ? from.elements.filter((e) => !to.elements.some((x) => x.key === e.key)) : [];
      what.innerHTML = `<ul>${li("del", "↺", `Reverted to v${d.to_version}`, "", "the last genome that passed every rule it was trusted on")}${lost.map((e) => li("del", "−", e.name, e.kind, "set aside until a fix proves itself")).join("")}</ul>`;
      learned.innerHTML = `<ul>${li("del", "▼", "Rolling score", `${pct(d.baseline)} → ${pct(d.rolling_score)}`, `${(d.case_ids || []).length} drifted cases captured as tests`)}</ul>`;
    } else if (mode === "snap") {
      const gt = s.mut.gate;
      why.innerHTML = `<ul>${li("pat", "◆", `${gt.event.replace("_", " ")} reported`, gt.case_id, "the MongoDB change stream fired the gate on insert")}</ul>`;
      what.innerHTML = none("Nothing yet. Snap decides whether to re-run first; the rules decide pass or fail.");
      learned.innerHTML = `<ul>${s.mut.gates.map((g) => { const [r, p] = Object.entries(g.rule_risk || {}).sort((a, b) => b[1] - a[1])[0] || ["none", 0];
        return li(g.rerun_now ? "del" : "add", g.rerun_now ? "▲" : "■", `${g.case_id}, ${g.event.replace("_", " ")}`, g.rerun_now ? "re-run" : "clear", `${r} ${p.toFixed(2)}, covered ${g.covered.toFixed(2)}`); }).join("")}</ul>`;
    } else if (mode === "subq") {
      const a = s.mut.analysis;
      why.innerHTML = none("The drift light is red. Before Muse edits anything, SubQ reads the whole lineage to find the pattern.");
      what.innerHTML = `<ul>${li("pat", "◆", "Nothing yet", "", a.handoff)}</ul>`;
      learned.innerHTML = `<ul>${a.patterns.map((p) => li("pat", "◆", p.rule, `${pct(p.failure_rate)}%`, `${p.condition}, ${p.runs} runs`)).join("")}</ul>`;
    } else if (mode === "realign") {
      const a = s.mut.analysis, d = s.mut.drift, nx = L[s.draftOf], cur = L[s.genome];
      why.innerHTML = a ? `<ul>${a.patterns.map((p) => li("pat", "◆", p.rule, `${pct(p.failure_rate)}%`, p.condition)).join("")}</ul>` : `<ul>${d.violations.map((v) => li("why", "✕", v.rule, v.severity, v.detail)).join("")}</ul>`;
      const draft = nx && cur ? nx.elements.filter((e) => !cur.elements.some((x) => x.key === e.key)) : [];
      what.innerHTML = draft.length ? `<ul>${draft.map((e) => li("draft", "+", e.name, "draft", e.desc || firstLine(e.body))).join("")}</ul>` : none("Muse is drafting.");
      learned.innerHTML = none("Not yet. The draft has to pass the drifted cases and the regression set first.");
    } else if (mode === "fix") {
      const v = s.mut.version ?? s.version, gv = L[v], d = s.mut.drift, a = s.mut.analysis;
      why.innerHTML = a ? `<ul>${a.patterns.slice(0, 3).map((p) => li("pat", "◆", p.rule, `${pct(p.failure_rate)}%`, p.condition)).join("")}</ul><p class="muted" style="margin-top:10px">SubQ's diagnosis of the drift.</p>` : d ? `<ul>${d.violations.map((x) => li("why", "✕", x.rule, x.severity, x.detail)).join("")}</ul>` : none("Drift on live cases.");
      what.innerHTML = gv ? mutList(gv.mutations) : none("No playbook data.");
      const gt = gv?.gate || {}, m = /(\d+)\/(\d+)/.exec(gt.reason || "");
      const rows = [];
      if (m) rows.push(li("add", "▲", "Drifted cases", `0 → ${m[1]} of ${m[2]}`, "now pass every hard rule"));
      if (gt.regression) rows.push(li("add", "✓", "Regression set", `${pct(gt.regression.pass_rate)}%`, "nothing that used to work broke"));
      if (s.kind === "green" && d) rows.push(li("add", "▲", "Rolling score", `${pct(d.rolling_score)} → ${pct(state.drift.find((x) => x.action === "shipped_fix")?.rolling_score ?? d.rolling_score)}`, "on live cases after the fix"));
      learned.innerHTML = rows.length ? `<ul>${rows.join("")}</ul>` : none("Verified on the drifted cases.");
    } else {
      why.innerHTML = what.innerHTML = learned.innerHTML = none("No lineage data for this step.");
    }
  }

  // ---------- render: step ----------
  function show(i) {
    const steps = state.steps;
    if (!steps.length) return;
    state.i = Math.max(0, Math.min(steps.length - 1, i));
    const s = steps[state.i];
    $("#step-count").textContent = `Step ${state.i + 1} of ${steps.length}`;
    $("#step-title").textContent = s.title;
    $("#step-body").textContent = s.body;
    $("#stage").dataset.kind = s.kind;
    $(".score").dataset.tone = s.tone || "";
    $("#score-num").textContent = s.scoreText ?? (s.score == null ? "—" : s.score.toFixed(3));
    $("#score-label").textContent = s.scoreLabel;
    const dl = $("#score-delta");
    if (s.delta) { dl.textContent = `${arrow(s.delta.v)} ${sd(s.delta.v)} ${s.delta.label}`; dl.className = `delta ${s.delta.v < 0 ? "neg" : "pos"}`; }
    else { dl.textContent = ""; dl.className = "delta"; }
    $("#prev").disabled = state.i === 0;
    $("#next").textContent = state.i === steps.length - 1 ? "Start over" : "Next step";
    document.querySelectorAll("#steps button").forEach((b, k) => {
      if (k === state.i) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
      b.classList.toggle("done", k < state.i);
    });
    const cur = document.querySelector(`#steps button[data-i="${state.i}"]`);
    if (cur) { const row = $("#steps"); row.scrollTo({ left: cur.offsetLeft - row.clientWidth / 2 + cur.offsetWidth / 2, behavior: reduced ? "auto" : "smooth" }); }
    setLight(s.light);
    renderGenome(s);
    renderMut(s);
    renderGate(s);
    renderCurve(s);
    history.replaceState(null, "", `${location.search}#step-${state.i + 1}`);
  }
  function setLight(level) {
    const l = $("#light");
    l.dataset.level = level;
    l.querySelector("b").textContent = level === "red" ? "Drift" : level === "yellow" ? "Verifying" : "Aligned";
  }
  function renderGate(s) {
    $("#gate").innerHTML = s.gate.map((c) => {
      const cls = c.ok === true ? "ok" : c.ok === false ? "no" : c.ok === "info" ? "info" : "";
      const sym = c.ok === true ? "✓" : c.ok === false ? "✕" : c.ok === "info" ? "i" : "–";
      return `<li class="${c.ok == null ? "pending" : ""}"><span class="k"><span class="mark ${cls}" aria-hidden="true">${sym}</span>${esc(c.k)}</span><span class="v">${esc(c.v)}</span><span class="n">${esc(c.n)}</span></li>`;
    }).join("");
    const st = $("#stamp");
    st.textContent = s.stamp[0];
    st.className = `stamp ${s.stamp[1]}`;
    if (!reduced) { void st.offsetWidth; st.classList.add("pop"); }
  }
  function renderCurve(s) {
    const svg = $("#curve");
    svg.innerHTML = "";
    const W = Math.round(Math.max(340, Math.min(720, svg.clientWidth || 720))), H = W < 500 ? 240 : 260, L = 36, R = 16, Tp = 26, B = 40;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const vs = state.versions;
    if (!vs.length) return;
    const xs = (k) => L + (k * (W - L - R)) / Math.max(1, vs.length - 1);
    const lo = 0.4, hi = 1.0, ys = (v) => Tp + (1 - (Math.max(lo, v) - lo) / (hi - lo)) * (H - Tp - B);
    // barber-pole fill for the drift band (avionics limit convention)
    const defs = el("defs", {}, svg), pat = el("pattern", { id: "barber", width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
    el("rect", { width: 4, height: 8, fill: tok("red"), "fill-opacity": 0.22 }, pat);
    // tape scale: minor ticks every 0.02, labeled major ticks every 0.10
    for (let t = lo; t <= hi + 1e-9; t += 0.02) {
      const major = Math.abs((t * 10) - Math.round(t * 10)) < 1e-6;
      if (major) el("line", { class: "grid", x1: L, x2: W - R, y1: ys(t), y2: ys(t) }, svg);
      el("line", { class: "tick", x1: L - (major ? 7 : 4), x2: L, y1: ys(t), y2: ys(t) }, svg);
      if (major) el("text", { class: "axis", x: L - 10, y: ys(t) + 4, "text-anchor": "end" }, svg).textContent = t.toFixed(1);
    }
    // target bug: what the current version's successor must clear
    const curG = vs.find((g) => g.version === s.version);
    if (curG && curG.decision === "shipped" && ["ship", "base"].includes(s.kind)) {
      const tgt = Math.min(1, curG.test.mean_score + 0.02);
      el("line", { class: "bug", x1: L, x2: W - R, y1: ys(tgt), y2: ys(tgt) }, svg);
      el("text", { class: "bug-l", x: W - R, y: ys(tgt) - 5, "text-anchor": "end" }, svg).textContent = `next gate ${tgt.toFixed(3)}`;
    }
    const seen = (g) => s.chartVersions.has(g.version);
    const red = state.drift.find((d) => d.action === "rollback");
    if (red && s.driftSeen) {
      const k1 = vs.findIndex((g) => g.version === red.from_version);
      const fix = state.drift.find((d) => d.action === "shipped_fix");
      const k2 = fix ? vs.findIndex((g) => g.version === fix.to_version) : vs.length - 1;
      if (k1 >= 0) {
        const x1 = xs(k1), x2 = xs(Math.max(k2, k1 + 1)), mx = (x1 + x2) / 2;
        el("rect", { class: "drift-band", x: x1, y: Tp, width: x2 - x1, height: H - Tp - B }, svg);
        el("rect", { class: "drift-pt", x: mx - 5, y: ys(red.rolling_score) - 5, width: 10, height: 10 }, svg);
        el("text", { class: "drift-lbl", x: mx, y: ys(red.rolling_score) + 22, "text-anchor": "middle" }, svg).textContent = `▼ drift ${red.rolling_score.toFixed(3)}`;
      }
    }
    const shown = vs.map((g, k) => ({ g, k })).filter((o) => o.g.decision === "shipped" && seen(o.g));
    if (shown.length) {
      const d = shown.map((o, j) => `${j ? "L" : "M"}${xs(o.k).toFixed(1)},${ys(o.g.test.mean_score).toFixed(1)}`).join("");
      const last = shown[shown.length - 1];
      el("path", { class: "area", d: `${d}L${xs(last.k)},${H - B}L${xs(shown[0].k)},${H - B}Z` }, svg);
      el("path", { class: "ln", d }, svg);
    }
    vs.forEach((g, k) => {
      const on = seen(g), rej = g.decision === "rejected", cur = g.version === s.version;
      const grp = el("g", { class: on ? "" : "future" }, svg);
      const sz = cur ? 7 : 5;
      el("rect", { class: `pt ${rej ? "rej" : ""} ${cur ? "cur" : ""}`, x: xs(k) - sz, y: ys(g.test.mean_score) - sz, width: sz * 2, height: sz * 2, transform: `rotate(45 ${xs(k)} ${ys(g.test.mean_score)})` }, grp);
      el("text", { class: "vlbl", x: xs(k), y: H - B + 24, "text-anchor": "middle" }, grp).textContent = `v${g.version}`;
      if (rej) el("text", { class: "rej-lbl", x: xs(k), y: ys(g.test.mean_score) + 22, "text-anchor": "middle" }, grp).textContent = `✕ ${g.test.mean_score.toFixed(3)}`;
      else if (on) el("text", { class: "axis", x: xs(k) + (k === 0 ? 8 : 0), y: ys(g.test.mean_score) - 14, "text-anchor": k === 0 ? "start" : "middle", fill: tok("text") }, grp).textContent = g.test.mean_score.toFixed(3);
    });
  }

  // ---------- the loop ----------
  const NODES = {
    case: { c: 0, r: 0, name: "Client case", color: "text" },
    agent: { c: 2, r: 0, name: "Pi agent on Muse", color: "muse" },
    checker: { c: 4, r: 0, name: "Policy checker", color: "mint" },
    rollback: { c: 6, r: 0, name: "Rollback", color: "red" },
    subq: { c: 6, r: 2, name: "SubQ analyst", color: "subq" },
    mentor: { c: 4, r: 2, name: "Muse mentor", color: "muse" },
    gate: { c: 2, r: 2, name: "Ship gate", color: "gold" },
    live: { c: 0, r: 2, name: "Live playbook", color: "mint" },
  };
  const LOOPS = {
    improve: [
      ["case", "Profile, holdings, market prices and any new life events."],
      ["agent", "Pi runs Muse in a sandbox. It reads the case and writes a cited recommendation."],
      ["checker", "Fixed rules the agent can't see or edit score every recommendation."],
      ["mentor", "Muse reads up to 8 failures and rewrites the playbook, at most 3 changes."],
      ["gate", "Beat the parent on unseen clients by +0.020, hold the regression set, pass Gemini review."],
      ["live", "The new version serves every client, and the loop runs again."],
    ],
    drift: [
      ["case", "A new life event lands in MongoDB. The change stream asks SubQ Snap whether to re-run now."],
      ["agent", "The live playbook runs on the new case."],
      ["checker", "A hard rule it always passed now fails. The light turns red."],
      ["rollback", "The last healthy playbook goes back in service at once."],
      ["subq", "SubQ reads every run, timeline and version in one pass and names the pattern."],
      ["mentor", "Muse writes a fix from SubQ's diagnosis. The drifted cases become tests."],
      ["gate", "The fix must pass the drifted cases and the full regression set."],
      ["live", "Back to green. After 3 failed attempts, an advisor takes over."],
    ],
  };
  const how = { mode: "improve", hop: 0, timer: null, raf: null };
  const LU = 84, LOX = 236, LOY = 64, NA = 54, NT = 18;
  const nodePos = (k, z = 0) => iso(LOX, LOY, NODES[k].c * LU + NA / 2, NODES[k].r * LU + NA / 2, z);
  function renderLoop() {
    const svg = $("#loop");
    svg.innerHTML = "";
    const pad = 40;
    el("polygon", { points: pts([iso(LOX, LOY, -pad, -pad, -6), iso(LOX, LOY, 6 * LU + NA + pad, -pad, -6), iso(LOX, LOY, 6 * LU + NA + pad, 2 * LU + NA + pad, -6), iso(LOX, LOY, -pad, 2 * LU + NA + pad, -6)]),
      fill: tok("void"), stroke: tok("rim") }, svg);
    const path = LOOPS[how.mode].map((x) => x[0]);
    const red = how.mode === "drift";
    const edges = [];
    for (let i = 0; i < path.length; i++) {
      if (i === path.length - 1 && red) break;
      const [x1, y1] = nodePos(path[i]), [x2, y2] = nodePos(path[(i + 1) % path.length]);
      const on = i < how.hop;
      edges.push({ p: el("path", { class: `edge-path ${on ? "on" : ""} ${on && red && i >= 2 && i <= 3 ? "red" : ""}`, d: `M${x1},${y1}L${x2},${y2}` }, svg), x1, y1, x2, y2 });
    }
    Object.entries(NODES).sort((a, b) => (a[1].c + a[1].r) - (b[1].c + b[1].r)).forEach(([k, n]) => {
      const inPath = path.includes(k), cur = path[how.hop] === k, visited = path.slice(0, how.hop + 1).includes(k);
      const c = tok(n.color);
      const g = el("g", { opacity: inPath ? 1 : 0.25 }, svg);
      const b = box(LOX, LOY, n.c * LU, n.r * LU, cur ? 10 : 0, NA, NA, NT);
      el("polygon", { points: pts(b.left), fill: visited ? c : tok("panel"), "fill-opacity": visited ? 0.6 : 1 }, g);
      el("polygon", { points: pts(b.right), fill: visited ? c : tok("deep"), "fill-opacity": visited ? 0.4 : 1 }, g);
      el("polygon", { points: pts(b.top), fill: visited ? c : tok("panel-2"), "fill-opacity": visited ? 0.9 : 1 }, g);
      const e = el("g", { fill: "none", stroke: c, "stroke-width": cur ? 2.5 : 1.2 }, g);
      [b.top, b.left, b.right].forEach((p) => el("polygon", { points: pts(p) }, e));
      const [tx, ty] = iso(LOX, LOY, n.c * LU + NA, n.r * LU + NA, 0);
      const t = el("text", { x: tx, y: ty + 26, "text-anchor": "middle" }, g);
      t.textContent = n.name;
      if (cur) t.setAttribute("style", `fill:${c}`);
    });
    if (how.hop > 0 && edges[how.hop - 1]) {
      const e = edges[how.hop - 1];
      const dot = el("circle", { class: "packet", r: 6, cx: e.x2, cy: e.y2 }, svg);
      if (!reduced) {
        cancelAnimationFrame(how.raf);
        const t0 = performance.now();
        const tick = (t) => {
          const k = Math.min(1, (t - t0) / 600), q = 1 - Math.pow(1 - k, 3);
          dot.setAttribute("cx", e.x1 + (e.x2 - e.x1) * q); dot.setAttribute("cy", e.y1 + (e.y2 - e.y1) * q);
          if (k < 1) how.raf = requestAnimationFrame(tick);
        };
        how.raf = requestAnimationFrame(tick);
      }
    }
    $("#how-steps").innerHTML = LOOPS[how.mode].map(([k, txt], i) => `<li class="${i === how.hop ? "cur" : ""}" data-h="${i}"><b>${esc(NODES[k].name)}</b><span>${esc(txt)}</span></li>`).join("");
  }
  function hop(n) { how.hop = (n + LOOPS[how.mode].length) % LOOPS[how.mode].length; renderLoop(); }
  function setMode(m) {
    how.mode = m; how.hop = 0;
    ["improve", "drift"].forEach((x) => { const b = $(`#tab-${x}`); b.setAttribute("aria-selected", x === m); b.tabIndex = x === m ? 0 : -1; });
    $("#how-panel").setAttribute("aria-labelledby", `tab-${m}`);
    renderLoop();
  }
  function stopHowAuto() { clearInterval(how.timer); how.timer = null; }
  function bindHow() {
    $("#tab-improve").addEventListener("click", () => { stopHowAuto(); setMode("improve"); });
    $("#tab-drift").addEventListener("click", () => { stopHowAuto(); setMode("drift"); });
    $(".how-tabs").addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const m = how.mode === "improve" ? "drift" : "improve"; stopHowAuto(); setMode(m); $(`#tab-${m}`).focus(); }
    });
    $("#how-next").addEventListener("click", () => { stopHowAuto(); hop(how.hop + 1); });
    $("#how-prev").addEventListener("click", () => { stopHowAuto(); hop(how.hop - 1); });
    $("#how-steps").addEventListener("click", (e) => { const l = e.target.closest("li"); if (l) { stopHowAuto(); hop(+l.dataset.h); } });
    if (!reduced && "IntersectionObserver" in window) {
      let started = false;
      new IntersectionObserver((ents) => ents.forEach((en) => {
        if (en.isIntersecting && !started) { started = true; how.timer = setInterval(() => hop(how.hop + 1), 2400); }
        if (!en.isIntersecting) stopHowAuto();
      }), { threshold: 0.4 }).observe($("#how-panel"));
    }
    renderLoop();
  }

  // ---------- stack ----------
  const TECH = [
    { id: "fetch", name: "Fetch.ai Agentverse", role: "Client chat, Next: not built yet", color: "amber", next: true, job: "Planned: each client's agent as a uAgent on Agentverse, so a client can chat with their own agent. Not built yet; no Agentverse key." },
    { id: "mongo", name: "MongoDB Atlas", role: "Memory and triggers", color: "jade", job: "Stores clients, runs, versions, lessons, jobs and drift events. Change streams fire a drift check when a life event lands and start live runs from the website. Next: vector search over past drift cases." },
    { id: "gemini", name: "Gemini", role: "Google DeepMind, compliance reviewer", color: "gold", wide: true, job: "Independent compliance reviewer in both stacks. Example: it blocked a Muse change that hard-coded \"$600 monthly contribution\" copied from one client's violation." },
    { id: "snap", name: "SubQ Snap", role: "Subquadratic, decision gates", color: "subq", job: "Scores every new life event in under a second: which rules are at risk, whether the playbook covers it, whether to re-run now. Gate F1 0.94 over 39 events, $0.04 per 1M input tokens. A second opinion on every drift window; the rules stay the source of truth." },
    { id: "subq", name: "SubQ Preview", role: "Subquadratic, long-context drift analyst", color: "subq", job: "Long-context drift analyst that reads every run, client timeline and playbook version in one pass, without chunking or retrieval. In the benchmark it also runs the whole SubQ stack: agent and mentor." },
    { id: "muse", name: "Muse", role: "Meta Model API, agent and mentor", color: "muse", wide: true, job: "Meta Model API. In the Muse stack, Muse Spark 1.3 is the agent and Muse Wonder 1.0 is the mentor that rewrites the playbook from failures." },
    { id: "pi", name: "Pi harness", role: "Coding-agent runtime", color: "mint", job: "Runs the agent with three tools (read, bash, write), a 20-turn limit and a 3-minute timeout. The playbook is its only config." },
    { id: "fly", name: "Fly.io Machines", role: "Runner and website", color: "text-2", job: "Agent runs happen on Fly machines in Virginia (Meta's API refuses San Jose). Each case runs in its own sandbox as an unprivileged user that can't read the checker or any keys." },
  ];
  let selTech = "subq";
  function renderLayers() {
    const svg = $("#layers");
    svg.innerHTML = "";
    const PA = 112, PT = 10, gap = 60, ox = 190, oy = 30 + (TECH.length - 1) * gap;
    svg.setAttribute("viewBox", `0 0 520 ${oy + PA + 24}`);
    [[0, 0], [PA, 0], [0, PA], [PA, PA]].forEach(([x, y]) => {
      const [a1, b1] = iso(ox, oy, x, y, 0), [a2, b2] = iso(ox, oy, x, y, (TECH.length - 1) * gap + PT);
      el("line", { x1: a1, y1: b1, x2: a2, y2: b2, stroke: tok("rim"), "stroke-dasharray": "3 5" }, svg);
    });
    [...TECH].reverse().forEach((t, i) => {
      const z = i * gap, sel = t.id === selTech, c = tok(t.color);
      // unbuilt parts render as a dashed wireframe only
      const g = el("g", { class: `layer ${sel ? "" : "dim"}`, ...(t.next ? { "stroke-dasharray": "4 3", opacity: sel ? 0.9 : 0.35 } : {}) }, svg);
      const b = box(ox, oy, 0, 0, z, PA, PA, PT);
      if (t.next) {
        [b.top, b.left, b.right].forEach((p) => el("polygon", { points: pts(p), fill: "none", stroke: c, "stroke-dasharray": "4 3" }, g));
        const [tx2, ty2] = iso(ox, oy, PA, 0, z + PT / 2);
        el("line", { x1: tx2 + 4, y1: ty2, x2: tx2 + 22, y2: ty2, stroke: c, "stroke-dasharray": "3 2" }, g);
        el("text", { x: tx2 + 28, y: ty2 + 4 }, g).textContent = `${t.name} (Next)`;
        el("text", { class: "sub", x: tx2 + 28, y: ty2 + 21 }, g).textContent = "not built yet";
        g.addEventListener("click", () => selectTech(t.id));
        return;
      }
      el("polygon", { points: pts(b.left), fill: c, "fill-opacity": sel ? 0.7 : 0.35 }, g);
      el("polygon", { points: pts(b.right), fill: c, "fill-opacity": sel ? 0.45 : 0.22 }, g);
      el("polygon", { points: pts(b.top), fill: c, "fill-opacity": sel ? 0.28 : 0.1, stroke: c, "stroke-width": sel ? 2 : 1 }, g);
      if (t.id === "snap") {
        // decision gate: one fast tick per event
        [0.2, 0.45, 0.7].forEach((f, k) => el("polygon", { points: pts(box(ox, oy, PA * f - 6, PA / 2 - 6, z + PT, 12, 12, 0).top), fill: k === 1 ? tok("red") : c }, g));
      }
      if (t.id === "subq") {
        for (let k = 0; k < 40; k++) {
          const x0 = 10 + (k * (PA - 20)) / 40;
          el("polygon", { points: pts([iso(ox, oy, x0, PA / 2 - 9, z + PT), iso(ox, oy, x0 + 2.2, PA / 2 - 9, z + PT), iso(ox, oy, x0 + 2.2, PA / 2 + 9, z + PT), iso(ox, oy, x0, PA / 2 + 9, z + PT)]), fill: k % 7 === 3 ? tok("red") : c }, g);
        }
      }
      const [tx, ty] = iso(ox, oy, PA, 0, z + PT / 2);
      el("line", { x1: tx + 4, y1: ty, x2: tx + 22, y2: ty, stroke: c }, g);
      const lab = el("text", { x: tx + 28, y: ty + 4 }, g);
      lab.textContent = t.name;
      if (sel) lab.setAttribute("style", `fill:${c}`);
      el("text", { class: "sub", x: tx + 28, y: ty + 21 }, g).textContent = t.role.split(",")[0];
      g.addEventListener("click", () => selectTech(t.id));
    });
  }
  function renderBento() {
    $("#bento").innerHTML = TECH.map((t) => `<li class="${t.wide ? "wide" : ""}"><button data-id="${t.id}" aria-pressed="${t.id === selTech}" style="--c:var(--${t.color})">
      <span class="who"><i style="background:var(--${t.color})"></i>${esc(t.name)}${t.next ? ` <span class="nextb">Next</span>` : ""}</span><span class="role">${esc(t.role)}</span><span class="job">${esc(t.job)}</span></button></li>`).join("");
    $("#bento").onclick = (e) => { const b = e.target.closest("button[data-id]"); if (b) selectTech(b.dataset.id); };
  }
  function selectTech(id) {
    selTech = id;
    renderLayers();
    document.querySelectorAll("#bento button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.id === id));
  }
  function renderBench(rows, demo) {
    const color = { muse: "muse", subq: "subq", gemini: "gold" };
    rows = rows.filter((r) => r.model !== "gemini");
    const max = Math.max(...rows.map((r) => r.mean_score), 0.01);
    const best = (k, lo) => { const v = rows.map((r) => r[k]).filter((x) => x != null); return v.length ? (lo ? Math.min(...v) : Math.max(...v)) : null; };
    const flag = (r, k, lo) => rows.length > 1 && r[k] != null && r[k] === best(k, lo) ? ` <span class="pos">▲</span>` : "";
    $("#bench-sub").textContent = demo
      ? "Muse stack vs SubQ stack on the same cases. Demo numbers until the benchmark runs land."
      : `Head to head, interim: the Muse stack and the SubQ stack from the same generic v0 on the same cases (test repeated 3×, paired gate, control arm). Read live from ${rows.map((r) => r.db).join(" and ")}. ▲ marks the better value per column.`;
    // speed as an instrument: each bar sweeps one case at that stack's real pace (time compressed 4x)
    let rc = document.getElementById("bench-race");
    if (!rc) { rc = document.createElement("div"); rc.id = "bench-race"; rc.className = "brace"; $("#bench").before(rc); }
    rc.innerHTML = rows.map((r) => `<div class="br-row">
      <span class="br-l"><b style="color:var(--${color[r.model] || "text"})">${esc(r.label)}</b></span>
      <span class="br-track" aria-hidden="true"><span class="br-fill" style="--d:${(r.seconds / 4).toFixed(2)}s;background:var(--${color[r.model] || "mint"})"></span></span>
      <span class="br-n"><b>${Number(r.seconds).toFixed(1)}</b> s/case</span><span class="br-n"><b>${r.runs_per_min != null ? Number(r.runs_per_min).toFixed(1) : "-"}</b> runs/min</span><span class="br-n"><b>${fmtTok(r.tokens)}</b> tok/case</span></div>`).join("")
      + `<p class="br-note">Bars sweep one case at each stack's measured pace, 4× faster than real time. Speed and accuracy are scored separately.</p>`;
    $("#bench").innerHTML = `<thead><tr><th>Stack</th><th class="barcell"><span class="sr">Score bar</span></th><th>Score</th><th>Pass rate</th><th>s / case</th><th>Runs / min</th><th>Tokens / case</th><th>Holdout start → final</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td><span class="m" style="color:var(--${color[r.model] || "text"})">${esc(r.label)}</span><span class="p">${esc(r.provider || "")}${r.runs ? `, ${r.runs} runs` : ""}</span></td>
        <td class="barcell"><div class="b"><span style="width:${(r.mean_score / max) * 100}%;background:var(--${color[r.model] || "mint"})"></span></div></td>
        <td>${Number(r.mean_score).toFixed(3)}${flag(r, "mean_score")}<span class="p">${esc(r.score_basis || "")}</span></td>
        <td>${(r.pass_rate * 100).toFixed(0)}%${flag(r, "pass_rate")}</td>
        <td>${Number(r.seconds).toFixed(1)}${flag(r, "seconds", true)}</td>
        <td>${r.runs_per_min != null ? Number(r.runs_per_min).toFixed(1) : "-"}${flag(r, "runs_per_min")}</td>
        <td>${fmtTok(r.tokens)}${flag(r, "tokens", true)}</td>
        <td>${r.holdout_start != null ? `${Number(r.holdout_start).toFixed(3)} → ${Number(r.holdout_final).toFixed(3)}<span class="p">${r.journeys} ${r.journeys === 1 ? "journey" : "journeys"}</span>` : "-"}</td></tr>`).join("")}</tbody>
      <tfoot><tr><td colspan="8" class="p">Gemini is the compliance reviewer in both stacks, not a contender. Reference only: Gemini 3.8 Flash as agent, v0 test 0.714.</td></tr></tfoot>`;
  }

  // ---------- clients ----------
  function renderClients(list) {
    if (!list.length) { $("#clients").innerHTML = `<li class="muted" style="grid-column:1/-1">No client profiles in this run's database yet. They're written when a version ships; per-client results are under Client journeys.</li>`; return; }
    $("#clients").innerHTML = list.map((c) => `<li><button data-id="${esc(c.client_id)}">
      <span class="nm">${esc(c.name)}</span><span class="sc ${c.passed === false ? "bad" : ""}">${c.score != null ? `${c.passed === false ? "✕ " : ""}${pct(c.score)}` : "–"}</span>
      <span class="meta"><span class="mono">${esc(c.client_id)}</span>, age ${esc(c.age)}, risk ${esc(c.risk_score)} ${c.events.map((e) => `<span class="chip">${esc(e.type.replace("_", " "))}</span>`).join("")}</span>
    </button></li>`).join("");
  }
  async function openClient(id) {
    const sheet = $("#sheet"), body = $("#sheet-body");
    body.innerHTML = "<p>Loading client.</p>";
    sheet.showModal();
    try {
      const c = await get(`/api/clients/${encodeURIComponent(id)}`);
      const rec = c.last_recommendation || {};
      const why = Object.fromEntries((rec.rationale || []).map((r) => [r.ref, r.text]));
      const trades = rec.trades || [], up = rec.profile_updates || {};
      const updates = [
        ...(up.goals_add || []).map((g) => `Add ${g.type} goal for ${g.target_year}`),
        up.monthly_contribution != null ? `Raise monthly contribution to $${Number(up.monthly_contribution).toLocaleString("en-US")}` : null,
        ...(rec.flags || []).map((f) => `Flag for review: ${f.replace(/_/g, " ")}`),
      ].filter(Boolean);
      const last = c.history[c.history.length - 1];
      body.innerHTML = `
        <h3 id="sheet-title">${esc(c.name)}</h3>
        <p class="sub"><span class="mono">${esc(c.client_id)}</span>, age ${esc(c.age)}, risk score ${esc(c.risk_score)}, served by playbook v${esc(c.agent_version)}</p>
        ${c.events.length ? `<p style="margin-top:10px">${c.events.map((e) => `<span class="chip">${esc(e.type.replace("_", " "))} on ${esc(e.date)}</span>`).join(" ")}</p>` : ""}
        <h4>Latest recommendation</h4>
        ${trades.length ? `<ul class="trades">${trades.map((t) => `<li><span class="act ${t.action}">${t.action === "sell" ? "▼ Sell" : "▲ Buy"}</span><span class="sym">${esc(t.symbol)}</span>
          <span class="amt">$${Number(t.amount_usd).toLocaleString("en-US")}</span><span class="why"><span class="mono">${esc(t.reason_ref)}</span>${why[t.reason_ref] ? `: ${esc(why[t.reason_ref])}` : ""}</span></li>`).join("")}</ul>`
          : `<p class="sub">No trades. ${esc(rec.no_action_reason || "")}</p>`}
        ${updates.length ? `<h4>Profile changes</h4><ul>${updates.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
        <h4>Score by playbook version</h4>
        <div class="hist" role="img" aria-label="This client's score by version">${c.history.map((h) => `<div class="${h.passed ? "" : "fail"}" style="height:${Math.max(6, h.score * 100)}%"><span>v${h.version}</span></div>`).join("")}</div>
        ${last && last.violations.length ? `<h4>Open issues</h4><ul>${last.violations.map((x) => `<li><span class="mono">${esc(x.rule)}</span>: ${esc(x.detail)}</li>`).join("")}</ul>` : `<p class="sub">✓ Passes every policy check on the current playbook.</p>`}`;
    } catch (e) {
      body.innerHTML = `<h3 id="sheet-title">Client didn't load</h3><p class="sub">${esc(e.message)}. Close and try again.</p>`;
    }
  }

  // ---------- lessons ledger ----------
  const fmtDate = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); };
  const evName = (e) => String(e || "").replace(/_/g, " ");
  function stepForVersion(v) { return state.steps.findIndex((s) => s.version === v && ["ship", "base", "reject"].includes(s.kind)); }
  function renderLedger(d) {
    const ol = $("#ledger");
    if (d && !d.lessons.length && (d.journey_lessons || []).length) {
      // the fleet playbook hasn't shipped a lesson yet; show the real per-client lessons from the journeys
      const all = d.journey_lessons.flatMap((j) => j.lessons.map((l) => ({ ...l, client: j.client, journey: j.journey })));
      ol.innerHTML = `<li class="muted" style="padding:12px 0">The shared playbook hasn't shipped a lesson yet (every candidate so far failed the gate). These are the real lessons each client's own agent learned on its journey.</li>` +
        all.map((l, i) => `<li class="lesson">
          <div class="l-meta"><span class="l-n">${String(i + 1).padStart(2, "0")} / ${String(all.length).padStart(2, "0")}</span><span class="mono l-rule">${esc(l.journey)}/${esc(l.at || "-")}</span><span class="mono l-rule">${esc(l.rule)}</span></div>
          <div class="l-body"><p class="l-text">${esc(l.lesson)}</p>
            <dl class="l-dl"><div><dt>Learned from</dt><dd><b>${esc(String(l.triggered_by || "").replace(/_/g, " "))}</b>, ${esc(l.client)}'s checkpoint ${esc(l.at || "-")}. ${esc(l.root_cause)}</dd></div>
              <div><dt>Proven on</dt><dd>kept only because it passed that checkpoint and every earlier one; see the client's holdout result under Client journeys</dd></div></dl>
            <p class="l-skill">Carried by skill <span class="mono">${esc(l.skill)}</span></p></div></li>`).join("");
      $("#pb-yaml").textContent = d.playbook_yaml || "No shipped playbook yet.";
      return;
    }
    if (!d || !d.lessons.length) { ol.innerHTML = `<li class="muted">No lessons yet. They appear when a playbook with a lesson ships.</li>`; $("#pb-yaml").textContent = d?.playbook_yaml || "No shipped playbook yet."; return; }
    ol.innerHTML = d.lessons.map((l, i) => {
      const p = l.proven || {};
      const proofs = [];
      if (p.before > p.after) proofs.push(`<li><b class="pos">▼ ${p.before} → ${p.after}</b> unseen clients failing <span class="mono">${esc(l.rule)}</span> when v${l.version} shipped${p.current_version != null && p.current_version !== l.version ? `; ${p.now} of ${p.cases} on v${p.current_version} today` : ""}</li>`);
      else if (l.mode === "drift" && l.gate_reason) proofs.push(`<li><b class="pos">✓</b> ${esc(l.gate_reason)}</li>`);
      if ((p.journeys || []).length) proofs.push(`<li><b class="pos">✓</b> holds on holdout checkpoints <span class="mono">${p.journeys.map(esc).join(", ")}</span></li>`);
      if (!proofs.length) proofs.push(`<li class="muted">Kept through the gate; no failures on this rule since.</li>`);
      return `<li class="lesson">
        <div class="l-meta"><span class="l-n">${String(i + 1).padStart(2, "0")} / ${String(d.lessons.length).padStart(2, "0")}</span>
          ${p.before > p.after ? `<span class="l-big">${p.before}→${p.after}<small>unseen clients failing<br>${esc(l.rule)}</small></span>` : (p.journeys || []).length ? `<span class="l-big">${p.journeys.length}<small>holdout checkpoints<br>held</small></span>` : ""}
          <button class="vchip" data-v="${l.version}" aria-label="See the v${l.version} mutation in the replay">v${l.version}</button></div>
        <div class="l-body">
          <p class="l-text">${esc(l.lesson)}</p>
          <dl class="l-dl">
            <div><dt>Learned from</dt><dd><b>${esc(evName(l.triggered_by))}</b>${l.date ? `, ${fmtDate(l.date)}` : ""}. ${esc(l.root_cause)}${l.example ? `<span class="l-ex mono">${esc(l.example)}</span>` : ""}</dd></div>
            <div><dt>Proven on</dt><dd><ul class="l-proof">${proofs.join("")}</ul></dd></div>
          </dl>
          <p class="l-skill">Carried by skill <span class="mono">${esc(l.skill)}</span></p>
        </div></li>`;
    }).join("");
    ol.onclick = (e) => { const b = e.target.closest("button[data-v]"); if (!b) return; const k = stepForVersion(+b.dataset.v); if (k >= 0) { stopPlay(); show(k); $("#genome").scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); } };
    const lost = $("#lost");
    if (d.rejected.length) {
      lost.hidden = false;
      $("#lost-sum").textContent = `${d.rejected.length} ${d.rejected.length === 1 ? "lesson" : "lessons"} didn't survive the gate`;
      $("#lost-list").innerHTML = d.rejected.map((l) => `<li><p class="l-text small">✕ ${esc(l.lesson)}</p><p class="muted">v${l.version}: ${esc(l.compliance?.note || l.reason || "failed the gate")}</p></li>`).join("");
    }
    $("#pb-yaml").textContent = d.playbook_yaml || "No shipped playbook yet.";
  }

  // ---------- client journeys ----------
  function tileState(r) { if (!r) return "none"; if (!r.violation) return "clean"; return r.passed ? "soft" : "fail"; }
  const TILE = { clean: ["✓", "no violations"], soft: ["◐", "passed with a soft miss"], fail: ["✕", "failed a hard rule"], none: ["·", "not run"] };
  function renderJourneys(list) {
    if (!list || !list.length) { $("#journeys").hidden = true; return; }
    const pick = $("#jpick");
    pick.innerHTML = list.map((j, i) => `<button data-j="${i}" aria-pressed="${i === 0}">${esc(j.persona.name)}<span>${esc(j.journey_id)}${j.progress ? ` ${j.progress.done}/${j.progress.total}` : ""}</span>${(j.lessons || []).length ? `<i class="pos">+${j.lessons.length}</i>` : ""}</button>`).join("");
    pick.onclick = (e) => { const b = e.target.closest("button[data-j]"); if (!b) return; pick.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b)); drawJourney(list[+b.dataset.j]); };
    // open on a client whose agent has already learned something
    const first = Math.max(0, list.findIndex((j) => (j.lessons || []).length));
    pick.querySelectorAll("button").forEach((x, k) => x.setAttribute("aria-pressed", k === first));
    drawJourney(list[first]);
  }
  function drawJourney(j) {
    const cps = j.checkpoints, first = j.persona.name.split(" ")[0];
    const lessonAt = {};
    (j.lessons || []).forEach((l) => { (lessonAt[l.at] = lessonAt[l.at] || []).push(l); });
    const cols = `repeat(${cps.length}, minmax(116px, 1fr))`;
    const cell = (inner, cls = "") => `<div class="jc ${cls}">${inner}</div>`;
    // live journey tiles open a replay of that exact run on /live
    const tile = (r, who) => { const st = tileState(r); const [g, w] = TILE[st];
      const lbl = `${who}: ${w}${r?.violation ? `, ${r.violation}` : ""}`;
      const t = j.source === "live" && r?.run_id
        ? `<a class="jt ${st}" href="/live#replay-run-${encodeURIComponent(r.run_id)}" title="Replay: ${esc(r?.violation || w)}" aria-label="${esc(lbl)}. Replay this run">${g}</a>`
        : `<span class="jt ${st}" title="${esc(r?.violation || w)}" aria-label="${esc(lbl)}">${g}</span>`;
      return `${t}${r && r.version != null ? `<span class="jv">v${r.version}</span>` : ""}`; };
    const hold = cps.filter((c) => c.split === "holdout");
    const ran = (k) => hold.filter((c) => c[k]).length;
    const clean = (k) => hold.filter((c) => tileState(c[k]) === "clean").length;
    const sm = j.summary;
    // 12-month forward backtest per checkpoint: minimum cash coverage, drawdown, breach
    const bt = (r) => { const b = r && r.backtest; if (!b) return `<span class="muted">-</span>`;
      const cash = b.min_cash_coverage_months, br = b.emergency_fund_breached;
      return `<span class="jbt"><span class="${br ? "neg" : ""}">${br ? "✕ " : ""}${cash != null ? Number(cash).toFixed(1) : "-"} mo</span><br>dd ${b.max_drawdown != null ? (b.max_drawdown * 100).toFixed(1) : "-"}%${b.forced_sale_usd ? `<br><span class="neg">$${Math.round(b.forced_sale_usd).toLocaleString("en-US")} forced</span>` : ""}</span>`; };
    const acts = (c) => (c.actions || []).map((a) => a.action === "learn" ? `<span class="jl">+ v${a.version}</span>` : `<span class="jl rej" title="${esc(a.reason || "")}">✕ v${a.version}</span>`).join("");
    $("#journey").innerHTML = `
      <div class="jhead">
        <div><p class="jname">${esc(j.persona.name)}, ${esc(j.persona.age ?? "")}</p><p class="muted">${esc(j.persona.occupation)}${j.persona.state ? `, ${esc(j.persona.state)}` : ""}, risk ${esc(j.persona.risk_score)}. ${esc(j.arc)}</p>
          ${j.regime_text ? `<p class="jregime">▼ ${esc(j.regime_text)}</p>` : ""}</div>
        <dl class="jscore"><div><dt>Holdout checkpoints clean</dt>
          ${sm ? `<dd><span class="neg">${esc(sm.holdout_pass_start)}</span> generic agent, mean ${Number(sm.holdout_mean_start).toFixed(3)}</dd><dd><span class="pos">${esc(sm.holdout_pass_final)}</span> ${esc(first)}'s agent, mean ${Number(sm.holdout_mean_final).toFixed(3)}</dd>`
            : ran("personal") ? `<dd><span class="neg">${clean("baseline")}/${ran("baseline") || hold.length}</span> generic agent</dd><dd><span class="pos">${clean("personal")}/${ran("personal")}</span> ${esc(first)}'s agent</dd>`
            : `<dd><span>${j.progress ? `${j.progress.done}/${j.progress.total}` : "-"}</span> checkpoints run; holdout not reached yet</dd>`}</div></dl>
        <span class="source">${j.source === "demo" ? "Illustration, not from a run" : `Real run, ${esc(j.db || "")}`}</span>
      </div>
      <div class="jscroll" tabindex="0" aria-label="Checkpoint timeline, scroll sideways">
        <div class="jgrid" style="grid-template-columns: 140px ${cols}">
          ${cell("", "lab")}${cps.map((c) => cell(`<b>${esc(c.date.slice(0, 7))}</b><span class="split ${c.split}">${c.split}</span>`, "date")).join("")}
          ${cell("Market", "lab")}${cps.map((c) => { const rg = (j.regimes || []).find((r) => r.name === c.regime); return cell(rg ? `<span class="regime ${esc(rg.kind)}">${esc(rg.name)}</span>` : `<span class="muted">calm</span>`, "mkt"); }).join("")}
          ${cell("Life events", "lab")}${cps.map((c) => cell(c.events.length ? c.events.map((e) => `<span class="chip">${esc(evName(e))}</span>`).join(" ") : `<span class="muted">none</span>`)).join("")}
          ${cell("Generic agent", "lab")}${cps.map((c) => cell(tile(c.baseline, "Generic agent"), "trow")).join("")}
          ${cell(`${esc(first)}'s agent`, "lab")}${cps.map((c) => cell(tile(c.personal, `${first}'s agent`), "trow")).join("")}
          ${cell("12-mo backtest", "lab")}${cps.map((c) => cell(bt(c.personal))).join("")}
          ${cell("Lessons", "lab")}${cps.map((c) => cell((lessonAt[c.id] || []).map((l) => `<span class="jl" title="${esc(l.lesson)}">◆ ${esc(l.rule)}</span>`).join("") + acts(c))).join("")}
        </div>
      </div>
      ${(j.lessons || []).length ? "" : `<p class="jempty muted">No lessons yet. ${esc(first)}'s agent learns at the first train checkpoint it fails.</p>`}
      <ol class="jlessons">${(j.lessons || []).slice().sort((a, b) => String(a.at).localeCompare(String(b.at))).map((l) => {
        const c = cps.find((x) => x.id === l.at);
        return `<li><span class="mono">${esc(l.at)}</span><div><p class="l-text small">${esc(l.lesson)}</p><p class="muted">Learned at ${esc(c ? c.date.slice(0, 7) : l.at)} from ${esc(evName(l.triggered_by))}: ${esc(l.root_cause)}</p></div></li>`; }).join("")}</ol>`;
  }

  // ---------- coverage: what the agent is ready for ----------
  const LIFE = [["layoff", "Layoff", ["layoff"]], ["job_change", "Raise or new job", ["job_change"]], ["marriage", "Marriage", ["marriage"]], ["child", "New child", ["child"]],
    ["divorce", "Divorce", ["divorce"]], ["inheritance", "Inheritance", ["inheritance"]], ["retirement", "Retirement", ["retirement", "approaching retirement"]],
    ["death", "Death in the family", ["death", "death_in_family"]], ["home", "Home purchase", ["home_purchase"]], ["disability", "Disability or illness", ["disability", "illness"]]];
  const MKT = [["crash", "Market crash", ["market drop", "market_drop", "crash"]], ["rates", "Rate shock", ["rates", "rate shock"]], ["inflation", "Inflation spike", ["inflation"]],
    ["concentration", "Single-stock blow-up", ["single-stock holding", "concentration"]], ["calm", "Calm, nothing changed", ["no new events", "calm"]], ["unfamiliar", "Event types never seen", ["unfamiliar event types"]]];
  function renderCoverage(les, jrn, drift) {
    // fleet lessons say which playbook version carries them; client-journey lessons say whose agent learned them
    const learned = {}, seen = new Set();
    ((les && les.lessons) || []).forEach((l) => { const k = String(l.triggered_by).toLowerCase(); if (!(k in learned)) learned[k] = `lesson in v${l.version}`; });
    (jrn || []).forEach((j) => (j.lessons || []).forEach((l) => { const k = String(l.triggered_by).toLowerCase(); if (!(k in learned)) learned[k] = `${j.persona.name.split(" ")[0]}'s agent`; }));
    (jrn || []).forEach((j) => { j.checkpoints.forEach((c) => c.events.forEach((e) => seen.add(e))); (j.regimes || []).forEach((r) => seen.add(r.kind)); });
    (drift || []).forEach((d) => (d.gates || []).forEach((g) => seen.add(g.event)));
    const row = ([key, label, aliases]) => {
      const hit = aliases.find((a) => a in learned);
      const st = hit ? "learned" : aliases.some((a) => seen.has(a)) || seen.has(key) ? "seen" : "new";
      const g = { learned: "✓", seen: "◐", new: "○" }[st];
      const note = st === "learned" ? learned[hit] : st === "seen" ? "seen, no lesson yet" : "Snap flags it";
      return `<li class="c-${st}"><b aria-hidden="true">${g}</b><span>${esc(label)}</span><em>${esc(note)}</em></li>`;
    };
    $("#cover-life").innerHTML = LIFE.map(row).join("");
    $("#cover-mkt").innerHTML = MKT.map(row).join("");
  }

  // ---------- controls + theme ----------
  function stopPlay() { clearInterval(state.playing); state.playing = null; $("#play").setAttribute("aria-pressed", "false"); $("#play").textContent = "Play"; }
  function bind() {
    $("#next").addEventListener("click", () => { stopPlay(); show(state.i === state.steps.length - 1 ? 0 : state.i + 1); });
    $("#prev").addEventListener("click", () => { stopPlay(); show(state.i - 1); });
    $("#play").addEventListener("click", () => {
      if (state.playing) return stopPlay();
      if (state.i === state.steps.length - 1) show(0);
      $("#play").setAttribute("aria-pressed", "true"); $("#play").textContent = "Pause";
      state.playing = setInterval(() => { if (state.i >= state.steps.length - 1) stopPlay(); else show(state.i + 1); }, 6000);
    });
    $("#steps").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { stopPlay(); show(+b.dataset.i); } });
    $("#rail").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-v]"); if (!b) return;
      const v = +b.dataset.v, k = state.steps.findIndex((s) => s.version === v && (s.kind === "ship" || s.kind === "base" || s.kind === "reject"));
      if (k >= 0) { stopPlay(); show(k); }
    });
    document.addEventListener("keydown", (e) => {
      if ($("#sheet").open || e.target.closest("input, textarea, [role=tablist]")) return;
      if (e.key === "ArrowRight") { stopPlay(); show(state.i + 1); }
      if (e.key === "ArrowLeft") { stopPlay(); show(state.i - 1); }
    });
    $("#clients").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) openClient(b.dataset.id); });
    $("#sheet-close").addEventListener("click", () => $("#sheet").close());
    $("#sheet").addEventListener("click", (e) => { if (e.target === $("#sheet")) $("#sheet").close(); });
  }
  // hero instrument panel: the real training run, read live from the runtime's database
  async function renderBoard() {
    const host = $("#board");
    let d;
    try { d = await get("/api/scoreboard"); } catch (_) { d = null; }
    const vs = (d && d.versions) || [];
    const shipped = vs.filter((v) => v.decision === "shipped");
    const cur = shipped[shipped.length - 1] || vs[vs.length - 1];
    if (!cur || !cur.test) {
      host.innerHTML = `<div class="bd-head"><span>Live training run</span><span>no generations yet</span></div><p class="bd-note">The scoreboard fills in when the runtime finishes its first baseline.</p>`;
      return;
    }
    const base = vs[0];
    const tape = (m, bug) => `<div class="tape" aria-hidden="true"><span class="fill" style="width:${(m.mean * 100).toFixed(1)}%"></span>${bug != null ? `<span class="bug" style="left:${(bug * 100).toFixed(1)}%"></span>` : ""}</div>`;
    const row = (k, m, bug) => m ? `<div class="bd-row"><span>${k}</span>${tape(m, bug)}<b>${m.mean.toFixed(3)}</b><em>${m.passed}/${m.n}</em></div>` : "";
    const regFloor = cur.regression ? cur.regression.mean : null;
    const xs = vs.map((v) => v.test?.mean ?? null).filter((x) => x != null);
    const sp = xs.length > 1 ? (() => {
      const lo = Math.min(...xs) - 0.02, hi = Math.max(...xs) + 0.02, w = 200, h = 30;
      const P = xs.map((x, i) => [(i / (xs.length - 1)) * w, h - ((x - lo) / (hi - lo)) * h]);
      return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${P.map((p) => p.join(",")).join(" ")}" fill="none" stroke="var(--mint)" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
    })() : `<svg viewBox="0 0 200 30" aria-hidden="true"><line x1="0" y1="15" x2="200" y2="15" stroke="var(--rim)" stroke-dasharray="3 3"/></svg>`;
    const delta = base && base !== cur ? cur.test.mean - base.test.mean : null;
    host.innerHTML = `
      <div class="bd-head"><span>Live run, <b>${esc((d.model || "").replace(/^meta\//, ""))}</b></span><span>${esc(d.db)}, v${cur.version}</span></div>
      <div class="bd-big"><span class="n">${cur.test.mean.toFixed(3)}</span><span class="k">mean policy score on ${cur.test.n} unseen clients${delta != null ? `<br><span class="${delta >= 0 ? "pos" : "neg"}">${arrow(delta)} ${sd(delta)} vs v0</span>` : ""}</span></div>
      <div class="bd-rows">${row("practice", cur.practice)}${row("test", cur.test, Math.min(1, cur.test.mean + 0.02))}${row("regression", cur.regression, regFloor)}</div>
      <div class="bd-spark"><span>test by version</span>${sp}<span>${vs.length} gen</span></div>
      <p class="bd-note">Magenta bugs mark the gate for the next upgrade: test must clear ${(cur.test.mean + 0.02).toFixed(3)}, regression must hold its floor (${regFloor != null ? regFloor.toFixed(3) : "-"}). Muse only ever sees practice.</p>`;
  }
  async function liveDot() {
    try {
      const r = await fetch("/api/live/status");
      if (!r.ok) return;
      const s = await r.json(), a = document.querySelector(".live-link");
      a.classList.toggle("on", !!s.active);
      a.title = s.active ? "A training run is in progress" : s.last_activity ? "No runs in the last 2 minutes" : "No training run yet";
    } catch (_) { /* optional on this page */ }
  }

  async function init() {
    liveDot();
    renderBoard();
    setInterval(() => { if (!document.hidden) liveDot(); }, 20000);
    bind();
    bindHow();
    renderLayers();
    renderBento();
    try {
      const [ov, versions, drift, clients, analysis, bench, lin, les, jrn] = await Promise.all([
        get("/api/overview"), get("/api/versions"), get("/api/drift"), get("/api/clients"),
        get("/api/analysis").catch(() => []), get("/api/benchmark").catch(() => []), get("/api/lineage"),
        get("/api/lessons").catch(() => null), get("/api/journeys").catch(() => [])]);
      state.lessons = les; state.journeys = jrn;
      state.versions = versions; state.drift = drift; state.analysis = analysis;
      lin.forEach((g) => { state.lineage[g.version] = g; });
      const src = $("#source");
      src.hidden = false;
      src.textContent = ov.source === "live" ? `Story: real runs, ${ov.db}` : ov.source === "demo" ? "Illustration, not from a run" : "Story: no runs yet";
      state.steps = buildSteps(versions, drift, analysis);
      const kindAttr = (k) => (k === "green" ? "ship" : k);
      $("#steps").innerHTML = state.steps.map((s, k) => `<li><button data-i="${k}" data-kind="${kindAttr(s.kind)}"><i aria-hidden="true"></i>${esc(s.label)}</button></li>`).join("");
      renderClients(clients);
      if (bench.length) renderBench(bench, !bench.some((r) => r.real)); else $(".bench").hidden = true;
      renderLedger(les);
      renderJourneys(jrn);
      renderCoverage(les, jrn, drift);
      const m = /#step-(\d+)/.exec(location.hash);
      show(m ? +m[1] - 1 : 0);
      let rt;
      addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => renderCurve(state.steps[state.i]), 150); });
    } catch (e) {
      $("#step-title").textContent = "Data didn't load";
      $("#step-body").textContent = `${e.message}. Reload the page.`;
    }
  }
  init();
})();
