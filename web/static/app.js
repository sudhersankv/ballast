/* ballast. v3: genome replay, loop diagram, exploded stack. Vanilla JS, no build. Colors come from CSS tokens. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => Math.round(x * 100);
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
          delta: base && g.version !== base.version ? { v: pct(score) - pct(base.test.mean_score), label: "points vs v0" } : null });
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
          const from = p ? pct(p.test.mean_score) : null;
          const lead = /layoff/i.test(g.changelog) ? "Muse read the layoff failures and wrote a layoff skill: raise cash to 6 months of expenses first, then rebalance. " : `${g.changelog} `;
          Object.assign(s, { kind: "ship", label: `v${g.version} ships`, title: `v${g.version} ships`,
            body: `${lead}${from != null ? `On unseen clients the score goes from ${from} to ${pct(score)}.` : ""}`,
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
          delta: { v: pct(d.rolling_score) - pct(d.baseline), label: "points vs shipped baseline" } });
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
    const gain = p ? pct(g.test.mean_score) - pct(p.test.mean_score) : 0, c = g.compliance;
    return [chk(gain >= 2, "Beats parent on unseen clients", `${arrow(gain)} ${signed(gain)} pts`, "needs +2 points or more"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", cv(c), c ? c.note : "")];
  }
  function gateDriftFix(g) {
    const m = /(\d+)\/(\d+)/.exec(g.reason || ""), c = g.compliance;
    return [chk(true, "Passes the drifted cases", m ? `${m[1]} of ${m[2]}` : "Passed", "now part of the test set"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
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

  // ---------- render: helix ----------
  const HX = { W: 640, H: 380, x0: 36, x1: 604, cy: 150, A: 64, turns: 2.4, r0: 64, r1: 500 };
  const helix = { phase: 0.6, raf: null, visible: true, nodes: null };
  function renderHelix(s) {
    const svg = $("#helix");
    svg.innerHTML = "";
    // narrow screens hide the rotated SVG labels (the chip list carries them), so crop that band away
    svg.setAttribute("viewBox", matchMedia("(max-width: 1000px)").matches ? "0 30 640 230" : "0 0 640 380");
    const { pairs, strand } = genomeFor(s);
    const col = { keep: tok("text-3"), add: tok("mint"), edit: tok("gold"), del: tok("red"), draft: tok("muse") };
    const strandCol = strand === "rejected" ? tok("gold") : tok("jade");
    // environment band (drift = the world changed around the genome)
    if (s.env) {
      el("rect", { x: 8, y: HX.cy - HX.A - 30, width: HX.W - 16, height: HX.A * 2 + 60, rx: 8, fill: tok("red"), "fill-opacity": 0.08, stroke: tok("red"), "stroke-opacity": 0.5, "stroke-dasharray": "5 5" }, svg);
      const t = el("text", { x: 20, y: HX.cy - HX.A - 12, class: "env", fill: tok("red") }, svg);
      t.textContent = "Environment changed: new event types and a market drop";
    }
    const back = [el("path", { fill: "none", stroke: strandCol, "stroke-width": 2, "stroke-opacity": 0.35, "stroke-dasharray": strand === "rejected" ? "6 5" : "" }, svg),
      el("path", { fill: "none", stroke: strandCol, "stroke-width": 2, "stroke-opacity": 0.35, "stroke-dasharray": strand === "rejected" ? "6 5" : "" }, svg)];
    const n = Math.max(1, pairs.length);
    const xs = pairs.map((_, i) => HX.r0 + ((i + 0.5) * (HX.r1 - HX.r0)) / n);
    const rungs = pairs.map((p, i) => {
      const g = el("g", {}, svg);
      const c = col[p.state];
      const line = el("line", { stroke: c, "stroke-width": p.state === "keep" ? 2.5 : 4, "stroke-linecap": "round", "stroke-dasharray": p.state === "del" || p.state === "draft" ? "4 4" : "", "stroke-opacity": p.state === "del" ? 0.7 : 1 }, g);
      const a = el("circle", { r: 5, fill: c }, g), b = el("circle", { r: 5, fill: c }, g);
      if (p.state !== "keep") {
        const t = el("text", { x: xs[i], y: HX.cy - HX.A - (s.env ? 40 : 14), "text-anchor": "middle", class: "glyph", fill: c }, svg);
        t.textContent = { add: "+", edit: "~", del: "−", draft: "+" }[p.state];
      }
      const lbl = el("text", { x: xs[i], y: HX.cy + HX.A + 30, transform: `rotate(35 ${xs[i]} ${HX.cy + HX.A + 30})`, class: "lbl", fill: p.state === "keep" ? tok("text-3") : c }, svg);
      lbl.textContent = p.note ? `${p.name} (${p.note})` : p.name;
      return { line, a, b, x: xs[i] };
    });
    const front = [el("path", { fill: "none", stroke: strandCol, "stroke-width": 3.5, "stroke-linecap": "round", "stroke-dasharray": strand === "rejected" ? "8 6" : "" }, svg),
      el("path", { fill: "none", stroke: strandCol, "stroke-width": 3.5, "stroke-linecap": "round", "stroke-dasharray": strand === "rejected" ? "8 6" : "" }, svg)];
    let scan = null;
    if (s.scan) {
      scan = el("rect", { x: HX.x0, y: HX.cy - HX.A - 12, width: 6, height: HX.A * 2 + 24, rx: 3, fill: tok("subq"), "fill-opacity": 0.85 }, svg);
      el("rect", { x: HX.x0, y: HX.cy - HX.A - 12, width: HX.x1 - HX.x0, height: HX.A * 2 + 24, rx: 8, fill: tok("subq"), "fill-opacity": 0.07, stroke: tok("subq"), "stroke-opacity": 0.6 }, svg);
      const t = el("text", { x: HX.x0, y: HX.cy - HX.A - 20, class: "env", fill: tok("subq") }, svg);
      t.textContent = `SubQ reads every version, run and timeline in one pass`;
    }
    helix.nodes = { back, front, rungs, scan };
    drawHelixFrame();
    // HTML base-pair list: readable labels on small screens, and a color-independent legend everywhere
    const glyph = { keep: "·", add: "+", edit: "~", del: "−", draft: "+" };
    const word = { keep: "kept", add: "added", edit: "edited", del: "removed", draft: "draft" };
    $("#pairs").innerHTML = pairs.map((p) => `<li class="${p.state}"><b aria-hidden="true">${glyph[p.state]}</b>${esc(p.name)}<span class="sr">, ${word[p.state]}${p.note ? `, ${esc(p.note)}` : ""}</span></li>`).join("");
    renderRail(s);
  }
  function strandPath(sign, front) {
    const k = (HX.turns * 2 * Math.PI) / (HX.x1 - HX.x0);
    let d = "", pen = false;
    for (let x = HX.x0; x <= HX.x1; x += 4) {
      const th = k * (x - HX.x0) + helix.phase + (sign > 0 ? 0 : Math.PI);
      const y = HX.cy + HX.A * Math.sin(th), z = Math.cos(th);
      if ((z >= 0) === front) { d += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`; pen = true; } else pen = false;
    }
    return d;
  }
  function drawHelixFrame() {
    const N = helix.nodes;
    if (!N) return;
    N.back[0].setAttribute("d", strandPath(1, false)); N.back[1].setAttribute("d", strandPath(-1, false));
    N.front[0].setAttribute("d", strandPath(1, true)); N.front[1].setAttribute("d", strandPath(-1, true));
    const k = (HX.turns * 2 * Math.PI) / (HX.x1 - HX.x0);
    N.rungs.forEach((r) => {
      const th = k * (r.x - HX.x0) + helix.phase;
      const y1 = HX.cy + HX.A * Math.sin(th), y2 = HX.cy - HX.A * Math.sin(th), z = Math.cos(th);
      r.line.setAttribute("x1", r.x); r.line.setAttribute("x2", r.x); r.line.setAttribute("y1", y1); r.line.setAttribute("y2", y2);
      r.a.setAttribute("cx", r.x); r.a.setAttribute("cy", y1); r.a.setAttribute("r", (4.5 + 2.5 * z).toFixed(2));
      r.b.setAttribute("cx", r.x); r.b.setAttribute("cy", y2); r.b.setAttribute("r", (4.5 - 2.5 * z).toFixed(2));
    });
    if (N.scan) {
      const x = HX.x0 + (((performance.now() / 1800) % 1) * (HX.x1 - HX.x0 - 6));
      N.scan.setAttribute("x", reduced ? HX.x0 : x.toFixed(1));
    }
  }
  function animateHelix() {
    if (reduced) return;
    let last = performance.now();
    const tick = (t) => {
      const dt = t - last; last = t;
      if (helix.visible && !document.hidden) { helix.phase += dt * 0.00045; drawHelixFrame(); }
      helix.raf = requestAnimationFrame(tick);
    };
    helix.raf = requestAnimationFrame(tick);
    if ("IntersectionObserver" in window) new IntersectionObserver((ents) => ents.forEach((e) => (helix.visible = e.isIntersecting))).observe($("#helix"));
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
        const d = pct(scoreAfter) - pct(scoreBefore);
        rows.unshift(li(d >= 0 ? "add" : "del", d >= 0 ? "▲" : "▼", "Average score", `${pct(scoreBefore)} → ${pct(scoreAfter)}`, `${signed(d)} points on ${lg.cases || 20} unseen clients`));
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
      what.innerHTML = mutList(g.mutations);
      if (s.kind === "reject") {
        const gt = g.gate || {}, c = gt.compliance;
        learned.innerHTML = `<ul>${li("del", "✕", "Didn't survive", "", gt.reason || "failed the gate")}${c ? li(c.verdict === "approve" ? "add" : "del", c.verdict === "approve" ? "✓" : "✕", "Gemini review", cv(c), c.note) : ""}${gt.regression ? li(gt.regression.pass_rate >= 1 ? "add" : "del", gt.regression.pass_rate >= 1 ? "✓" : "✕", "Regression set", `${pct(gt.regression.pass_rate)}%`, "must stay at 100%") : ""}</ul>`;
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
    $("#score-num").textContent = s.scoreText ?? pct(s.score);
    $("#score-label").textContent = s.scoreLabel;
    const dl = $("#score-delta");
    if (s.delta) { dl.textContent = `${arrow(s.delta.v)} ${signed(s.delta.v)} ${s.delta.label}`; dl.className = `delta ${s.delta.v < 0 ? "neg" : "pos"}`; }
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
    renderHelix(s);
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
    [0.4, 0.6, 0.8, 1.0].forEach((t) => {
      el("line", { class: "grid", x1: L, x2: W - R, y1: ys(t), y2: ys(t) }, svg);
      el("text", { class: "axis", x: L - 8, y: ys(t) + 4, "text-anchor": "end" }, svg).textContent = pct(t);
    });
    const seen = (g) => s.chartVersions.has(g.version);
    const red = state.drift.find((d) => d.action === "rollback");
    if (red && s.driftSeen) {
      const k1 = vs.findIndex((g) => g.version === red.from_version);
      const fix = state.drift.find((d) => d.action === "shipped_fix");
      const k2 = fix ? vs.findIndex((g) => g.version === fix.to_version) : vs.length - 1;
      if (k1 >= 0) {
        const x1 = xs(k1), x2 = xs(Math.max(k2, k1 + 1)), mx = (x1 + x2) / 2;
        el("rect", { class: "drift-band", x: x1, y: Tp, width: x2 - x1, height: H - Tp - B, rx: 8 }, svg);
        el("circle", { class: "drift-pt", cx: mx, cy: ys(red.rolling_score), r: 6 }, svg);
        el("text", { class: "drift-lbl", x: mx, y: ys(red.rolling_score) + 22, "text-anchor": "middle" }, svg).textContent = `▼ drift ${pct(red.rolling_score)}`;
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
      el("circle", { class: `pt ${rej ? "rej" : ""} ${cur ? "cur" : ""}`, cx: xs(k), cy: ys(g.test.mean_score), r: cur ? 8 : 6 }, grp);
      el("text", { class: "vlbl", x: xs(k), y: H - B + 24, "text-anchor": "middle" }, grp).textContent = `v${g.version}`;
      if (rej) el("text", { class: "rej-lbl", x: xs(k), y: ys(g.test.mean_score) + 22, "text-anchor": "middle" }, grp).textContent = "✕ rejected";
      else if (on) el("text", { class: "axis", x: xs(k), y: ys(g.test.mean_score) - 14, "text-anchor": "middle" }, grp).textContent = pct(g.test.mean_score);
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
      ["gate", "Beat the parent on unseen clients, keep regression at 100%, pass Gemini review."],
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
    { id: "fetch", name: "Fetch.ai Agentverse", role: "Client chat", color: "amber", job: "Each client's agent is a uAgent on Agentverse. A client texts \"I got laid off\" and gets a recommendation back." },
    { id: "mongo", name: "MongoDB Atlas", role: "Memory and triggers", color: "jade", job: "Stores clients, runs, versions and drift events. Change streams fire a drift check when a life event lands; vector search finds similar past drift." },
    { id: "gemini", name: "Gemini", role: "Google DeepMind, compliance reviewer", color: "gold", wide: true, job: "An independent reviewer. It blocks any playbook change that weakens a policy rule before it can ship." },
    { id: "snap", name: "SubQ Snap", role: "Subquadratic, decision gates", color: "subq", job: "Scores every new life event in under a second: which rules are at risk, whether the playbook covers it, whether to re-run now. Gate F1 0.94 over 39 events, $0.04 per 1M input tokens. A second opinion on every drift window; the rules stay the source of truth." },
    { id: "subq", name: "SubQ Preview", role: "Subquadratic, long-context drift analyst", color: "subq", job: "When drift hits, it reads every run trace, client timeline and playbook version in one pass, without chunking or retrieval, and names the pattern. Muse writes the fix from that diagnosis." },
    { id: "muse", name: "Muse", role: "Meta Model API, agent and mentor", color: "muse", wide: true, job: "The model behind everything. As the agent it runs every client case; as the mentor it rewrites the playbook from failures." },
    { id: "pi", name: "Pi harness", role: "Coding-agent runtime", color: "mint", job: "Runs the agent: reads case files, calls tools, writes recommendation.json. The playbook is its only config." },
    { id: "fly", name: "Fly.io Machines", role: "Sandboxes", color: "text-2", job: "Each case runs in its own machine as an unprivileged user that can't read the checker." },
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
      const g = el("g", { class: `layer ${sel ? "" : "dim"}` }, svg);
      const b = box(ox, oy, 0, 0, z, PA, PA, PT);
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
      <span class="who"><i style="background:var(--${t.color})"></i>${esc(t.name)}</span><span class="role">${esc(t.role)}</span><span class="job">${esc(t.job)}</span></button></li>`).join("");
    $("#bento").onclick = (e) => { const b = e.target.closest("button[data-id]"); if (b) selectTech(b.dataset.id); };
  }
  function selectTech(id) {
    selTech = id;
    renderLayers();
    document.querySelectorAll("#bento button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.id === id));
  }
  function renderBench(rows, demo) {
    const color = { muse: "muse", subq: "subq", gemini: "gold" };
    const max = Math.max(...rows.map((r) => r.mean_score), 0.01);
    if (demo) $("#bench-sub").textContent += " Demo numbers until the runtime records a benchmark.";
    $("#bench").innerHTML = `<thead><tr><th>Model</th><th class="barcell"><span class="sr">Score bar</span></th><th>Score</th><th>Pass rate</th><th>Tokens per case</th><th>Seconds per case</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td><span class="m" style="color:var(--${color[r.model] || "text"})">${esc(r.label)}</span><span class="p">${esc(r.provider || "")}</span></td>
        <td class="barcell"><div class="b"><span style="width:${(r.mean_score / max) * 100}%;background:var(--${color[r.model] || "mint"})"></span></div></td>
        <td>${pct(r.mean_score)}</td><td>${pct(r.pass_rate)}%</td><td>${fmtTok(r.tokens)}</td><td>${Number(r.seconds).toFixed(1)}</td></tr>`).join("")}</tbody>`;
  }

  // ---------- clients ----------
  function renderClients(list) {
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
    const th = $("#theme");
    const syncTheme = () => { const light = document.documentElement.dataset.theme === "light"; th.textContent = light ? "Dark" : "Light"; th.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme"); };
    syncTheme();
    th.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("ballast-theme", next); } catch (_) { /* private mode */ }
      syncTheme();
      if (state.steps.length) show(state.i);
      renderLoop(); renderLayers();
    });
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
    const th = new URLSearchParams(location.search).get("theme");
    if (th === "light" || th === "dark") document.documentElement.dataset.theme = th;
    liveDot();
    setInterval(() => { if (!document.hidden) liveDot(); }, 20000);
    bind();
    bindHow();
    renderLayers();
    renderBento();
    try {
      const [ov, versions, drift, clients, analysis, bench, lin] = await Promise.all([
        get("/api/overview"), get("/api/versions"), get("/api/drift"), get("/api/clients"),
        get("/api/analysis").catch(() => []), get("/api/benchmark").catch(() => []), get("/api/lineage")]);
      state.versions = versions; state.drift = drift; state.analysis = analysis;
      lin.forEach((g) => { state.lineage[g.version] = g; });
      $("#source").hidden = ov.source !== "demo";
      state.steps = buildSteps(versions, drift, analysis);
      const kindAttr = (k) => (k === "green" ? "ship" : k);
      $("#steps").innerHTML = state.steps.map((s, k) => `<li><button data-i="${k}" data-kind="${kindAttr(s.kind)}"><i aria-hidden="true"></i>${esc(s.label)}</button></li>`).join("");
      renderClients(clients);
      if (bench.length) renderBench(bench, ov.source === "demo"); else $(".bench").hidden = true;
      const m = /#step-(\d+)/.exec(location.hash);
      show(m ? +m[1] - 1 : 0);
      animateHelix();
      let rt;
      addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => renderCurve(state.steps[state.i]), 150); });
    } catch (e) {
      $("#step-title").textContent = "Data didn't load";
      $("#step-body").textContent = `${e.message}. Reload the page.`;
    }
  }
  init();
})();
