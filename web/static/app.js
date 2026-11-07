/* ballast. v2: guided replay, loop diagram, exploded stack. Vanilla JS, no build. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => Math.round(x * 100);
  const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
  const fmtTok = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
  const HARD = new Set(["valid_output", "risk_band", "emergency_fund", "concentration", "cited"]);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DEMO = new URLSearchParams(location.search).get("demo") === "1";

  const state = { steps: [], i: 0, details: {}, versions: [], drift: [], analysis: [], playing: null, rendered: new Set(), painted: false };

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

  // ---------- isometric projection (one angle for every drawing) ----------
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

    const slabs = [];
    let light = "green", lastAnalysis = null;
    const steps = [];
    for (const e of evs) {
      const s = { light };
      if (e.type === "gen") {
        const g = e.g, p = byV[g.parent], score = g.test.mean_score;
        Object.assign(s, { version: g.version, score, scoreLabel: "average policy score on unseen clients",
          delta: base && g.version !== base.version ? { v: score - base.test.mean_score, label: "vs v0" } : null,
          diffVersion: g.version, viol: { kind: "version", version: g.version } });
        if (g.parent == null) {
          Object.assign(s, { kind: "base", label: `v${g.version} baseline`, title: `v${g.version}: the starting playbook`,
            body: "It reads the case and rebalances to target, with no habits for life events. On a layoff case it rebalanced to normal targets and left about 2.7 months of cash where 6 were needed. This is the bar every upgrade has to clear.",
            gate: gateBaseline(g), stamp: ["Baseline", "hold"] });
          slabs.push({ v: g.version, status: "ship", score });
        } else if (g.decision === "rejected") {
          const blocked = g.compliance && g.compliance.verdict === "block";
          Object.assign(s, { kind: "reject", label: `v${g.version} blocked`, title: `v${g.version} is blocked`,
            body: blocked ? `Muse proposed: “${g.changelog}” Gemini's compliance review stopped it. ${g.compliance.note}`
                          : `Muse proposed: “${g.changelog}” It didn't clear the gate (${g.reason}).`,
            gate: gateTraining(g, p), stamp: ["Rejected", "block"], tone: "alarm" });
          slabs.push({ v: g.version, status: "reject", score });
        } else if (g.mode === "drift") {
          Object.assign(s, { kind: "ship", label: `v${g.version} fix`, title: `v${g.version} fixes the drift`,
            body: `${g.changelog} It has to pass every drifted case and the full regression set before it goes live.`,
            gate: gateDriftFix(g), stamp: ["Shipped", "ship"], tone: "good" });
          if (light === "red") s.light = "yellow";
          slabs.push({ v: g.version, status: "ship", score });
        } else {
          const from = p ? pct(p.test.mean_score) : null;
          const lead = /layoff/i.test(g.changelog) ? "Muse read the layoff failures and wrote a layoff skill: raise cash to 6 months of expenses first, then rebalance. " : "";
          Object.assign(s, { kind: "ship", label: `v${g.version} ships`, title: `v${g.version} ships`,
            body: `${lead || g.changelog + " "}${from != null ? `Unseen clients go from ${from} to ${pct(score)}.` : ""}`,
            gate: gateTraining(g, p), stamp: ["Shipped", "ship"], tone: "good" });
          slabs.push({ v: g.version, status: "ship", score });
        }
      } else if (e.type === "analysis") {
        const a = e.a, top = a.patterns[0];
        lastAnalysis = a;
        Object.assign(s, { kind: "subq", label: "SubQ reads all runs", title: `SubQ reads all ${a.runs_read} runs at once`,
          body: `${a.summary} The worst pattern: ${top.condition} fails ${top.rule} ${pct(top.failure_rate)}% of the time.`,
          version: null, score: top.failure_rate, scoreLabel: `of runs fail ${top.rule} when: ${top.condition}`, tone: "subq",
          gate: gateAnalysis(a), stamp: ["Diagnosed", "subq"], viol: { kind: "patterns", list: a.patterns },
          diffNote: `${a.handoff}\n\nSubQ ${a.model ? `(${a.model}) ` : ""}read ${a.runs_read} runs, ${a.client_timelines} client timelines and ${a.playbook_versions} playbook versions: ${fmtTok(a.tokens_read)} tokens in one pass, ${a.seconds}s.`,
          ribbon: a });
        s.light = light;
      } else {
        const d = e.d, n = (d.case_ids || []).length;
        Object.assign(s, { version: d.to_version, score: d.rolling_score, scoreLabel: "rolling score on the latest live cases",
          delta: { v: d.rolling_score - d.baseline, label: "vs shipped baseline" }, viol: { kind: "drift", list: d.violations } });
        light = d.level; s.light = light;
        if (d.action === "rollback") {
          Object.assign(s, { kind: "red", label: "Drift caught", title: "Drift caught: rolled back",
            body: `New conditions hit v${d.from_version}: ${n} live cases broke rules it always passed. The light turns red and ballast. puts v${d.to_version} back in service right away.`,
            gate: gateContain(d), stamp: ["Rolled back", "block"], tone: "alarm", diffNote: `Rolled back from v${d.from_version} to v${d.to_version}. No playbook change yet.` });
          const sl = slabs.find((x) => x.v === d.from_version);
          if (sl) sl.status = "rolled";
        } else if (d.action === "realign") {
          Object.assign(s, { kind: "muse", label: "Muse writes a fix", title: "Muse writes a fix",
            body: `The ${n} drifted cases become tests. Muse writes a fix from ${lastAnalysis ? "SubQ's diagnosis" : "the violations"}. It gets 3 attempts before a person takes over.`,
            gate: gateRealign(d, lastAnalysis), stamp: ["Fixing", "muse"], tone: "alarm",
            diffNote: lastAnalysis ? `Muse's brief from SubQ:\n${lastAnalysis.patterns.map((p) => `· ${p.condition}: ${p.rule} fails ${pct(p.failure_rate)}%`).join("\n")}` : `Muse is reading ${n} drifted cases.`,
            candidate: true });
        } else if (d.action === "shipped_fix") {
          const g = byV[d.to_version];
          Object.assign(s, { kind: "green", label: "Aligned", title: "Aligned again",
            body: `v${d.to_version} is live. The rolling score is ${pct(d.rolling_score)}, against a baseline of ${pct(d.baseline)}. The drift became a skill the agent keeps.`,
            gate: g ? gateDriftFix(g) : gateRealign(d), stamp: ["Aligned", "ship"], tone: "good",
            diffVersion: d.to_version, viol: { kind: "version", version: d.to_version } });
        } else if (d.action === "escalated") {
          Object.assign(s, { kind: "red", label: "Escalated", title: "Escalated to a person",
            body: `Muse couldn't produce a passing fix in 3 attempts. v${d.to_version} stays live and an advisor is notified.`,
            gate: gateRealign(d), stamp: ["Escalated", "block"], tone: "alarm" });
        } else {
          Object.assign(s, { kind: d.level === "red" ? "red" : "muse", label: `Drift ${d.level}`, title: `Drift light: ${d.level}`,
            body: `Rolling score ${pct(d.rolling_score)} against a baseline of ${pct(d.baseline)}.`, gate: gateRealign(d), stamp: ["Watching", "hold"] });
        }
      }
      s.slabs = slabs.map((x) => ({ ...x }));
      s.chartVersions = new Set(slabs.map((x) => x.v));
      s.driftSeen = steps.some((x) => x.kind === "red") || s.kind === "red";
      steps.push(s);
    }
    return steps;
  }

  const chk = (ok, k, v, n) => ({ ok, k, v, n });
  const cv = (c) => (c ? (c.verdict === "approve" ? "Approved" : "Blocked") : "Skipped");
  function gateBaseline(g) {
    return [chk(null, "Beats parent on unseen clients", "Baseline", "every upgrade must beat this"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "golden clients that must always pass"),
      chk(null, "Gemini compliance review", "Not needed", "nothing changed yet")];
  }
  function gateTraining(g, p) {
    const gain = p ? g.test.mean_score - p.test.mean_score : 0, c = g.compliance;
    return [chk(gain >= 0.02, "Beats parent on unseen clients", sgn(gain), "needs +0.02 or more"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", cv(c), c ? c.note : "")];
  }
  function gateDriftFix(g) {
    const m = /(\d+)\/(\d+)/.exec(g.reason || ""), c = g.compliance;
    return [chk(true, "Passes the drifted cases", m ? `${m[1]} of ${m[2]}` : "Passed", "captured as new tests"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", cv(c), c ? c.note : "")];
  }
  function gateContain(d) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || ""),
      chk(true, "Contain", `Back to v${d.to_version}`, `v${d.from_version} pulled from service`),
      chk(true, "Capture", `${(d.case_ids || []).length} cases`, "added to the test set")];
  }
  function gateAnalysis(a) {
    return [chk("info", "Runs read", `${a.runs_read}`, `plus ${a.client_timelines} client timelines and ${a.playbook_versions} versions`),
      chk("info", "Context in one pass", `${fmtTok(a.tokens_read)} tokens`, "no chunking, no retrieval"),
      chk("info", "Patterns found", `${a.patterns.length}`, "handed to Muse with example traces")];
  }
  function gateRealign(d, a) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || "no new violations"),
      chk(a ? "info" : true, a ? "Diagnose" : "Contain", a ? `${a.patterns.length} patterns` : `v${d.to_version} live`, a ? "from SubQ's long-context pass" : "last known-good playbook"),
      chk(null, "Realign", "Muse, attempt 1", "up to 3 before a person steps in")];
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
    $(".stage").dataset.kind = s.kind;
    $(".score").dataset.tone = s.tone || "";
    $("#score-num").textContent = pct(s.score);
    $("#score-label").textContent = s.scoreLabel;
    const dl = $("#score-delta");
    if (s.delta) { dl.textContent = `${s.delta.v >= 0 ? "+" : "−"}${Math.abs(pct(s.delta.v))} points ${s.delta.label}`; dl.className = "delta" + (s.delta.v < 0 ? " neg" : ""); }
    else dl.textContent = "";
    $("#prev").disabled = state.i === 0;
    $("#next").textContent = state.i === steps.length - 1 ? "Start over" : "Next step";
    document.querySelectorAll("#steps button").forEach((b, k) => {
      if (k === state.i) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
      b.classList.toggle("done", k < state.i);
    });
    const cur = document.querySelector(`#steps button[data-i="${state.i}"]`);
    if (cur) { const row = $("#steps"); row.scrollTo({ left: cur.offsetLeft - row.clientWidth / 2 + cur.offsetWidth / 2, behavior: reduced ? "auto" : "smooth" }); }
    setLight(s.light);
    renderStack(s);
    renderGate(s);
    renderViol(s);
    renderDiff(s);
    renderCurve(s);
    history.replaceState(null, "", `${location.search}#step-${state.i + 1}`);
  }
  function setLight(level) {
    const l = $("#light");
    l.dataset.level = level;
    l.querySelector("b").textContent = level === "red" ? "Drift" : level === "yellow" ? "Verifying" : "Aligned";
  }

  // ---------- render: ballast stack ----------
  const A = 128, T = 26, GX = 300, GY = 292;
  function layout(slabs) {
    const shipped = slabs.filter((x) => x.status === "ship").length;
    const step = Math.min(T + 10, 230 / Math.max(1, shipped));
    let level = 0;
    const out = [];
    for (const sl of slabs) {
      if (sl.status === "ship") { out.push({ sl, dx: 0, z: level * step }); level++; }
      else if (sl.status === "reject") out.push({ sl, dx: -178, z: level * step });
      else out.push({ sl, dx: 178, z: Math.max(0, level - 0.5) * step + 14 });
    }
    return { draws: out, top: level * step };
  }
  function defs(svg) {
    const d = el("defs", {}, svg);
    const grad = (id, stops, x2 = 1, y2 = 1) => {
      const g = el("linearGradient", { id, x1: 0, y1: 0, x2, y2 }, d);
      stops.forEach(([o, c]) => el("stop", { offset: o, "stop-color": c }, g));
    };
    // hard color stops (Stripe-style bands) on slab tops
    grad("topShip", [["0", "#7DFFC9"], [".46", "#5CF2B3"], [".46", "#2FD997"], [".78", "#22C487"], [".78", "#1BB078"], ["1", "#169E6B"]]);
    grad("topRolled", [["0", "#FF9DB0"], [".5", "#FF7590"], [".5", "#FF4D6D"], ["1", "#E03556"]]);
    grad("beam", [["0", "rgba(160,140,255,0)"], ["1", "rgba(160,140,255,.55)"]], 0, 1);
    grad("scanG", [["0", "rgba(92,225,255,0)"], [".5", "rgba(92,225,255,.9)"], ["1", "rgba(92,225,255,0)"]], 1, 0);
    const pat = el("pattern", { id: "hatch", width: 7, height: 7, patternUnits: "userSpaceOnUse", patternTransform: "rotate(30)" }, d);
    el("rect", { width: 7, height: 7, fill: "#0F3426" }, pat);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 7, stroke: "#F5C451", "stroke-width": 2 }, pat);
    const f = el("filter", { id: "glow", x: "-30%", y: "-30%", width: "160%", height: "160%" }, d);
    el("feGaussianBlur", { stdDeviation: 4, result: "b" }, f);
    const m = el("feMerge", {}, f); el("feMergeNode", { in: "b" }, m); el("feMergeNode", { in: "SourceGraphic" }, m);
  }
  function floor(svg) {
    const g = el("g", {}, svg);
    const ext = 120, stepU = 32;
    for (let u = -ext; u <= A + ext; u += stepU) {
      const fade = 1 - Math.abs(u - A / 2) / (A / 2 + ext + 10);
      const [a1, b1] = iso(GX, GY, u, -ext, 0), [a2, b2] = iso(GX, GY, u, A + ext, 0);
      el("line", { class: "floor-line", x1: a1, y1: b1, x2: a2, y2: b2, opacity: fade.toFixed(2) }, g);
      const [c1, d1] = iso(GX, GY, -ext, u, 0), [c2, d2] = iso(GX, GY, A + ext, u, 0);
      el("line", { class: "floor-line", x1: c1, y1: d1, x2: c2, y2: d2, opacity: fade.toFixed(2) }, g);
    }
    // crosshairs at a few intersections (blueprint marks)
    [[-56, -56], [A + 56, -56], [-56, A + 56], [A + 88, A + 88]].forEach(([x, y]) => {
      const [cx, cy] = iso(GX, GY, x, y, 0);
      el("path", { class: "floor-cross", d: `M${cx - 6},${cy}h12M${cx},${cy - 6}v12` }, g);
    });
    // footprint plate under the stack
    el("polygon", { points: pts([iso(GX, GY, -14, -14, 0), iso(GX, GY, A + 14, -14, 0), iso(GX, GY, A + 14, A + 14, 0), iso(GX, GY, -14, A + 14, 0)]),
      fill: "rgba(108,255,192,.05)", stroke: "rgba(108,255,192,.35)", "stroke-width": 1 }, g);
  }
  function ribbon(svg, a) {
    // A long strip of every run, wrapped around the base of the stack, scanned in one pass.
    const g = el("g", {}, svg);
    const n = Math.min(240, a.runs_read || 240), half = Math.floor(n / 2);
    const off = A + 40, w = 22, len1 = A + 120, len2 = A + 120;
    let k = 0, seed = 11;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const red = (i) => rnd() < 0.22;
    for (let i = 0; i < half; i++, k++) {
      const x0 = -60 + (len1 * i) / half, x1 = -60 + (len1 * (i + 1)) / half - 0.6;
      el("polygon", { class: "ribbon-cell", points: pts([iso(GX, GY, x0, off, 0), iso(GX, GY, x1, off, 0), iso(GX, GY, x1, off + w, 0), iso(GX, GY, x0, off + w, 0)]),
        fill: red(k) ? "#FF4D6D" : "#16C784", opacity: 0.85 }, g);
    }
    for (let i = 0; i < n - half; i++, k++) {
      const y0 = -60 + (len2 * i) / (n - half), y1 = -60 + (len2 * (i + 1)) / (n - half) - 0.6;
      el("polygon", { class: "ribbon-cell", points: pts([iso(GX, GY, off, y0, 0), iso(GX, GY, off + w, y0, 0), iso(GX, GY, off + w, y1, 0), iso(GX, GY, off, y1, 0)]),
        fill: red(k) ? "#FF4D6D" : "#16C784", opacity: 0.85 }, g);
    }
    // the single pass: one cyan wash over the whole ribbon, plus a sweeping beam
    const wash = (pA, pB) => el("polygon", { points: pts(pA), fill: "rgba(92,225,255,.18)", stroke: "#5CE1FF", "stroke-width": 1.2, filter: "url(#glow)" }, g);
    wash([iso(GX, GY, -60, off, 0), iso(GX, GY, -60 + len1, off, 0), iso(GX, GY, -60 + len1, off + w, 0), iso(GX, GY, -60, off + w, 0)]);
    wash([iso(GX, GY, off, -60, 0), iso(GX, GY, off + w, -60, 0), iso(GX, GY, off + w, -60 + len2, 0), iso(GX, GY, off, -60 + len2, 0)]);
    if (!reduced) {
      const [sx, sy] = iso(GX, GY, -60, off, 0), [ex, ey] = iso(GX, GY, -60 + len1, off, 0);
      const beam = el("polygon", { class: "scan", points: pts([iso(GX, GY, -60, off - 6, 0), iso(GX, GY, -46, off - 6, 0), iso(GX, GY, -46, off + w + 6, 0), iso(GX, GY, -60, off + w + 6, 0)]), fill: "#5CE1FF", opacity: 0.7, filter: "url(#glow)" }, g);
      el("animateTransform", { attributeName: "transform", type: "translate", from: "0 0", to: `${ex - sx} ${ey - sy}`, dur: "1.6s", repeatCount: "indefinite" }, beam);
    }
    const [lx, ly] = iso(GX, GY, A + 80, off + w + 24, 0);
    const t = el("text", { x: lx, y: ly + 8, "text-anchor": "middle", fill: "#5CE1FF", style: "font:700 14px var(--ui)" }, g);
    t.textContent = `${n} runs, ${fmtTok(a.tokens_read)} tokens, one pass`;
  }
  function drawSlab(svg, ox, oy, z, sl, active, ghost) {
    if (ghost) {
      const b = box(ox, oy, 0, 0, z, A, A, T);
      const g = el("g", {}, svg);
      [b.top, b.left, b.right].forEach((p) => el("polygon", { class: "ghost-slab", points: pts(p) }, g));
      return;
    }
    const isNew = !state.rendered.has(`${sl.v}:${sl.status}`);
    const g = el("g", { class: "slab" }, svg);
    const b = box(ox, oy, 0, 0, z, A, A, T);
    const ship = sl.status === "ship", rej = sl.status === "reject", rolled = sl.status === "rolled";
    const face = rej ? ["url(#hatch)", "#0F3426", "#0B2A1F", "#F5C451"] : rolled ? ["url(#topRolled)", "#B3263E", "#7A1328", "#FF4D6D"] : ["url(#topShip)", "#0E8A5B", "#0A5C3D", "#6CFFC0"];
    el("polygon", { points: pts(b.left), fill: face[1] }, g);
    el("polygon", { points: pts(b.right), fill: face[2] }, g);
    el("polygon", { points: pts(b.top), fill: face[0] }, g);
    // engraved score groove on top
    const f = Math.max(0.05, Math.min(1, sl.score));
    el("polygon", { points: pts([iso(ox, oy, 16, A / 2 - 7, z + T), iso(ox, oy, 16 + (A - 32) * f, A / 2 - 7, z + T), iso(ox, oy, 16 + (A - 32) * f, A / 2 + 7, z + T), iso(ox, oy, 16, A / 2 + 7, z + T)]),
      fill: "#04110C", opacity: ship ? 0.35 : 0.25 }, g);
    const edge = el("g", { fill: "none", stroke: active ? "#F5C451" : face[3], "stroke-width": active ? 2.4 : 1.2, "stroke-linejoin": "round", opacity: active ? 1 : 0.75 }, g);
    if (active || rolled) edge.setAttribute("filter", "url(#glow)");
    if (rej) edge.setAttribute("stroke-dasharray", "5 4");
    [b.top, b.left, b.right].forEach((p) => el("polygon", { points: pts(p) }, edge));
    const [lx, ly] = iso(ox, oy, A, A, z + T / 2);
    const label = el("text", { x: (lx + 10).toFixed(1), y: (ly + 6).toFixed(1) }, g);
    el("tspan", { class: "big" }, label).textContent = `v${sl.v}`;
    el("tspan", { dx: 7 }, label).textContent = `${pct(sl.score)}`;
    if (rej) el("tspan", { dx: 7, fill: "#F5C451" }, label).textContent = "rejected";
    if (rolled) el("tspan", { dx: 7, fill: "#FF4D6D" }, label).textContent = "rolled back";
    if (isNew && !reduced && state.painted) {
      g.classList.add("entering");
      requestAnimationFrame(() => requestAnimationFrame(() => g.classList.remove("entering")));
    }
  }
  function renderStack(s) {
    const svg = $("#stack");
    svg.innerHTML = "";
    defs(svg);
    floor(svg);
    if (s.ribbon) ribbon(svg, s.ribbon);
    // wireframe ghosts of where the story ends up (Mercury-style background wireframes)
    const last = state.steps[state.steps.length - 1];
    const ghost = layout(last.slabs).draws.filter((d) => !s.slabs.some((x) => x.v === d.sl.v));
    ghost.sort((a, b) => (a.dx === 0) - (b.dx === 0) || a.z - b.z).forEach((d) => drawSlab(svg, GX + d.dx, GY, d.z, d.sl, false, true));
    const { draws, top } = layout(s.slabs);
    draws.sort((a, b) => (a.dx === 0) - (b.dx === 0) || a.z - b.z);
    for (const d of draws) drawSlab(svg, GX + d.dx, GY, d.z, d.sl, d.sl.v === s.version);
    if (s.candidate) {
      // Muse beam and the fix being written, hovering above the stack
      const zc = top + 62;
      const [bx, by] = iso(GX, GY, A / 2, A / 2, zc + T);
      el("polygon", { points: `${bx - 70},0 ${bx + 70},0 ${bx + 36},${by} ${bx - 36},${by}`, fill: "url(#beam)", opacity: 0.6 }, svg);
      const b = box(GX, GY, 0, 0, zc, A, A, T);
      const g = el("g", { fill: "rgba(160,140,255,.12)", stroke: "#A08CFF", "stroke-width": 1.6, "stroke-dasharray": "6 4", filter: "url(#glow)" }, svg);
      [b.left, b.right, b.top].forEach((p) => el("polygon", { points: pts(p) }, g));
      const [lx, ly] = iso(GX, GY, A, A, zc + T / 2);
      const t = el("text", { x: lx + 10, y: ly + 6, fill: "#A08CFF", style: "font:700 14px var(--ui)" }, svg);
      t.textContent = "Muse drafting v5";
    }
    state.rendered = new Set(s.slabs.map((x) => `${x.v}:${x.status}`));
    state.painted = true;
    $("#stack-cap").textContent =
      s.kind === "subq" ? "Every run wraps the base as one ribbon. SubQ reads all of it in a single pass." :
      s.kind === "red" ? "The drifted version slides off. The last good one carries the load." :
      s.kind === "muse" ? "Muse drafts the fix above the stack. It only lands if it passes the gate." :
      s.kind === "reject" ? "A rejected candidate never joins the stack." :
      "Each slab is a playbook version that passed the gate. Outlines show what's coming.";
  }

  // ---------- render: gate / evidence / curve ----------
  function renderGate(s) {
    $("#gate").innerHTML = s.gate.map((c) => {
      const cls = c.ok === true ? "ok" : c.ok === false ? "no" : c.ok === "info" ? "info" : "";
      const sym = c.ok === true ? "✓" : c.ok === false ? "✕" : c.ok === "info" ? "i" : "–";
      return `<li class="${c.ok == null ? "pending" : ""}">
        <span class="k"><span class="mark ${cls}" aria-hidden="true"><span>${sym}</span></span>${esc(c.k)}</span>
        <span class="v">${esc(c.v)}</span><span class="n">${esc(c.n)}</span></li>`;
    }).join("");
    const st = $("#stamp");
    st.textContent = s.stamp[0];
    st.className = `stamp ${s.stamp[1]}`;
    if (!reduced) { void st.offsetWidth; st.classList.add("pop"); }
  }
  function renderViol(s) {
    const ul = $("#viol");
    if (s.viol.kind === "patterns") {
      $("#viol-sub").textContent = "Systematic patterns SubQ found across every run";
      ul.innerHTML = s.viol.list.map((p) => `<li class="pat">
        <span class="rule">${esc(p.rule)}<span class="sev">${esc(p.runs)} runs</span></span><span class="cnt">${pct(p.failure_rate)}%</span>
        <span class="bar"><span style="width:${pct(p.failure_rate)}%"></span></span>
        <span class="detail">${esc(p.condition)}</span></li>`).join("");
      return;
    }
    if (s.viol.kind === "drift") {
      $("#viol-sub").textContent = "Hard violations on live cases that tripped the drift light";
      ul.innerHTML = s.viol.list.length ? s.viol.list.map((x) => `<li class="${x.severity === "hard" ? "hard" : ""}">
        <span class="rule">${esc(x.rule)}<span class="sev">${esc(x.severity)}</span></span><span></span>
        <span class="detail">${esc(x.detail)}</span></li>`).join("") : `<li class="empty">No violations.</li>`;
      return;
    }
    const v = state.versions.find((g) => g.version === s.viol.version), det = state.details[s.viol.version];
    const counts = Object.entries(v?.violations_by_rule || {}).sort((a, b) => b[1] - a[1]);
    $("#viol-sub").textContent = `Playbook v${s.viol.version} on 20 unseen clients: cases with each violation`;
    const max = Math.max(1, ...counts.map((c) => c[1]));
    ul.innerHTML = counts.length ? counts.map(([rule, n]) => {
      const ex = det?.sample_violations?.find((x) => x.rule === rule);
      return `<li class="${HARD.has(rule) ? "hard" : ""}">
        <span class="rule">${esc(rule)}<span class="sev">${HARD.has(rule) ? "hard" : "soft"}</span></span><span class="cnt">${n}</span>
        <span class="bar"><span style="width:${(n / max) * 100}%"></span></span>
        ${ex ? `<span class="detail">${esc(ex.case_id)}: ${esc(ex.detail)}</span>` : ""}</li>`;
    }).join("") : `<li class="empty">No violations on unseen clients.</li>`;
  }
  function renderDiff(s) {
    const pre = $("#diff");
    if (s.diffNote && s.kind !== "green") {
      $("#diff-sub").textContent = s.kind === "subq" ? "What SubQ hands to Muse" : s.kind === "muse" ? "Muse's brief" : "No new playbook at this step";
      pre.innerHTML = `<span class="note">${esc(s.diffNote)}</span>`;
      return;
    }
    const d = state.details[s.diffVersion];
    if (!d) { pre.innerHTML = `<span class="ctx">Playbook v${esc(s.diffVersion)} isn't available.</span>`; return; }
    $("#diff-sub").textContent = d.parent == null ? `Playbook v${d.version}, the starting point` : `v${d.parent} to v${d.version}: ${d.changelog}`;
    const lines = d.parent == null ? d.yaml.split("\n").map((l) => " " + l) : d.diff.filter((l) => !l.startsWith("---") && !l.startsWith("+++"));
    pre.innerHTML = lines.map((l) => {
      const c = l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "@" ? "hunk" : "ctx";
      return `<span class="${c}">${esc(c === "hunk" ? "…" : l.slice(1)) || " "}</span>`;
    }).join("");
  }
  function renderCurve(s) {
    const svg = $("#curve");
    svg.innerHTML = "";
    const W = Math.round(Math.max(340, Math.min(720, svg.clientWidth || 720))), H = W < 500 ? 240 : 260, L = 36, R = 16, Tp = 26, B = 40;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const d0 = el("defs", {}, svg), lg = el("linearGradient", { id: "curveFill", x1: 0, y1: 0, x2: 0, y2: 1 }, d0);
    el("stop", { offset: 0, "stop-color": "rgba(108,255,192,.28)" }, lg); el("stop", { offset: 1, "stop-color": "rgba(108,255,192,0)" }, lg);
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
        el("circle", { cx: mx, cy: ys(red.rolling_score), r: 6, fill: "#FF4D6D", filter: "drop-shadow(0 0 6px #FF4D6D)" }, svg);
        el("text", { class: "drift-lbl", x: mx, y: ys(red.rolling_score) + 22, "text-anchor": "middle" }, svg).textContent = `drift ${pct(red.rolling_score)}`;
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
      if (rej) el("text", { class: "rej-lbl", x: xs(k), y: ys(g.test.mean_score) + 22, "text-anchor": "middle" }, grp).textContent = "rejected";
      else if (on) el("text", { class: "axis", x: xs(k), y: ys(g.test.mean_score) - 14, "text-anchor": "middle" }, grp).textContent = pct(g.test.mean_score);
    });
  }

  // ---------- how it works: loop diagram ----------
  const NODES = {
    case: { c: 0, r: 0, name: "Client case", color: "#E8FFF4" },
    agent: { c: 2, r: 0, name: "Pi agent on Muse", color: "#A08CFF" },
    checker: { c: 4, r: 0, name: "Policy checker", color: "#6CFFC0" },
    rollback: { c: 6, r: 0, name: "Rollback", color: "#FF4D6D" },
    subq: { c: 6, r: 2, name: "SubQ analyst", color: "#5CE1FF" },
    mentor: { c: 4, r: 2, name: "Muse mentor", color: "#A08CFF" },
    gate: { c: 2, r: 2, name: "Ship gate", color: "#F5C451" },
    live: { c: 0, r: 2, name: "Live playbook", color: "#6CFFC0" },
  };
  const LOOPS = {
    improve: [
      ["case", "Profile, holdings, market prices and any new life events."],
      ["agent", "Pi runs Muse in a Fly sandbox. It reads the case and writes a cited recommendation."],
      ["checker", "Fixed rules the agent can't see or edit score every recommendation."],
      ["mentor", "Muse reads up to 8 failures and rewrites the playbook, at most 3 changes."],
      ["gate", "Beat the parent on unseen clients, keep regression at 100%, pass Gemini review."],
      ["live", "The new version serves every client, and the loop runs again."],
    ],
    drift: [
      ["case", "A new life event lands in MongoDB. A change stream triggers a drift check."],
      ["agent", "The live playbook runs on the new case."],
      ["checker", "A hard rule it always passed now fails. The light turns red."],
      ["rollback", "The last known-good playbook goes back in service at once."],
      ["subq", "SubQ reads every run, timeline and version in one pass and names the pattern."],
      ["mentor", "Muse writes a fix from SubQ's diagnosis. The drifted cases become tests."],
      ["gate", "The fix must pass the drifted cases and the full regression set."],
      ["live", "Back to green. After 3 failed attempts, a person takes over."],
    ],
  };
  const how = { mode: "improve", hop: 0, timer: null, raf: null };
  const LU = 84, LOX = 236, LOY = 64, NA = 54, NT = 18;
  const nodePos = (k, z = 0) => iso(LOX, LOY, NODES[k].c * LU + NA / 2, NODES[k].r * LU + NA / 2, z);

  function renderLoop() {
    const svg = $("#loop");
    svg.setAttribute("viewBox", "0 0 760 500");
    svg.innerHTML = "";
    const d = el("defs", {}, svg);
    const f = el("filter", { id: "glow2", x: "-40%", y: "-40%", width: "180%", height: "180%" }, d);
    el("feGaussianBlur", { stdDeviation: 5, result: "b" }, f);
    const m = el("feMerge", {}, f); el("feMergeNode", { in: "b" }, m); el("feMergeNode", { in: "SourceGraphic" }, m);
    // platform
    const pad = 40;
    el("polygon", { points: pts([iso(LOX, LOY, -pad, -pad, -6), iso(LOX, LOY, 6 * LU + NA + pad, -pad, -6), iso(LOX, LOY, 6 * LU + NA + pad, 2 * LU + NA + pad, -6), iso(LOX, LOY, -pad, 2 * LU + NA + pad, -6)]),
      fill: "rgba(108,255,192,.035)", stroke: "rgba(108,255,192,.22)" }, svg);
    for (let u = 0; u <= 6 * LU + NA; u += 42) {
      const [a1, b1] = iso(LOX, LOY, u, -pad, -6), [a2, b2] = iso(LOX, LOY, u, 2 * LU + NA + pad, -6);
      el("line", { class: "floor-line", x1: a1, y1: b1, x2: a2, y2: b2 }, svg);
    }
    const path = LOOPS[how.mode].map((x) => x[0]);
    const red = how.mode === "drift";
    // edges
    const edges = [];
    for (let i = 0; i < path.length; i++) {
      const a = path[i], b = path[(i + 1) % path.length];
      if (i === path.length - 1 && how.mode === "drift") break;
      const [x1, y1] = nodePos(a), [x2, y2] = nodePos(b);
      const on = i < how.hop;
      const p = el("path", { class: `edge-path ${on ? "on" : ""} ${on && red && i >= 2 && i <= 3 ? "red" : ""}`, d: `M${x1},${y1}L${x2},${y2}` }, svg);
      edges.push({ p, x1, y1, x2, y2 });
    }
    // nodes, back to front
    Object.entries(NODES).sort((a, b) => (a[1].c + a[1].r) - (b[1].c + b[1].r)).forEach(([k, n]) => {
      const inPath = path.includes(k), cur = path[how.hop] === k, visited = path.slice(0, how.hop + 1).includes(k);
      const g = el("g", { class: cur ? "on" : "", opacity: inPath ? 1 : 0.22 }, svg);
      const b = box(LOX, LOY, n.c * LU, n.r * LU, cur ? 10 : 0, NA, NA, NT);
      el("polygon", { points: pts(b.left), fill: visited ? n.color : "#0F3426", opacity: visited ? 0.55 : 1 }, g);
      el("polygon", { points: pts(b.right), fill: visited ? n.color : "#0B2A1F", opacity: visited ? 0.35 : 1 }, g);
      el("polygon", { points: pts(b.top), fill: visited ? n.color : "#174A37", opacity: visited ? 0.9 : 1 }, g);
      const e = el("g", { fill: "none", stroke: n.color, "stroke-width": cur ? 2.4 : 1.2 }, g);
      if (cur) e.setAttribute("filter", "url(#glow2)");
      [b.top, b.left, b.right].forEach((p) => el("polygon", { points: pts(p) }, e));
      const [tx, ty] = iso(LOX, LOY, n.c * LU + NA, n.r * LU + NA, 0);
      const t = el("text", { x: tx, y: ty + 26, "text-anchor": "middle", class: cur ? "on" : "" }, g);
      t.textContent = n.name;
      if (cur) t.setAttribute("fill", n.color);
    });
    // packet travelling along the current edge
    if (how.hop > 0 && edges[how.hop - 1]) {
      const e = edges[how.hop - 1];
      const dot = el("circle", { class: "packet", r: 6, cx: e.x2, cy: e.y2 }, svg);
      if (!reduced) {
        cancelAnimationFrame(how.raf);
        const t0 = performance.now();
        const tick = (t) => {
          const k = Math.min(1, (t - t0) / 650);
          dot.setAttribute("cx", e.x1 + (e.x2 - e.x1) * k);
          dot.setAttribute("cy", e.y1 + (e.y2 - e.y1) * k);
          if (k < 1) how.raf = requestAnimationFrame(tick);
        };
        how.raf = requestAnimationFrame(tick);
      }
    }
    // step list
    $("#how-steps").innerHTML = LOOPS[how.mode].map(([k, txt], i) => `<li class="${i === how.hop ? "cur" : ""}" data-h="${i}"><b>${esc(NODES[k].name)}</b><span>${esc(txt)}</span></li>`).join("");
  }
  function hop(n) { how.hop = (n + LOOPS[how.mode].length) % LOOPS[how.mode].length; renderLoop(); }
  function setMode(m) {
    how.mode = m; how.hop = 0;
    $("#tab-improve").setAttribute("aria-selected", m === "improve");
    $("#tab-drift").setAttribute("aria-selected", m === "drift");
    $("#tab-improve").tabIndex = m === "improve" ? 0 : -1;
    $("#tab-drift").tabIndex = m === "drift" ? 0 : -1;
    $("#how-panel").setAttribute("aria-labelledby", m === "improve" ? "tab-improve" : "tab-drift");
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
    $("#how-steps").addEventListener("click", (e) => { const li = e.target.closest("li"); if (li) { stopHowAuto(); hop(+li.dataset.h); } });
    if (!reduced && "IntersectionObserver" in window) {
      let started = false;
      new IntersectionObserver((ents) => {
        ents.forEach((en) => {
          if (en.isIntersecting && !started) { started = true; how.timer = setInterval(() => hop(how.hop + 1), 2200); }
          if (!en.isIntersecting) stopHowAuto();
        });
      }, { threshold: 0.4 }).observe($("#how-panel"));
    }
    renderLoop();
  }

  // ---------- stack: exploded layers + bento ----------
  const TECH = [
    { id: "fetch", name: "Fetch.ai Agentverse", role: "Client chat", color: "#FFB547", job: "Each client's agent is a uAgent on Agentverse. The client texts “I got laid off” and gets a recommendation back." },
    { id: "mongo", name: "MongoDB Atlas", role: "Memory and triggers", color: "#16C784", job: "Stores clients, runs, versions and drift events. Change streams fire a drift check when a life event lands; vector search finds similar past drift." },
    { id: "gemini", name: "Gemini", role: "Google DeepMind, compliance reviewer", color: "#F5C451", job: "An independent reviewer. It blocks any playbook change that weakens a policy rule before it can ship." },
    { id: "subq", name: "SubQ", role: "Subquadratic, long-context drift analyst", color: "#5CE1FF", wide: true, job: "When drift hits, SubQ reads every run trace, client timeline and playbook version in one pass, with no chunking or retrieval, and names the systematic pattern. Muse writes the fix from that diagnosis." },
    { id: "muse", name: "Muse", role: "Meta Model API, agent and mentor", color: "#A08CFF", wide: true, job: "The model behind everything. It runs every client case as the agent, and as the mentor it rewrites the playbook from failures." },
    { id: "pi", name: "Pi harness", role: "Coding-agent runtime", color: "#6CFFC0", job: "Runs the agent: reads case files, calls tools, writes recommendation.json. The playbook, a prompt plus skills, is its only config." },
    { id: "fly", name: "Fly.io Machines", role: "Sandboxes", color: "#C9E8DA", job: "Each case runs in its own machine as an unprivileged user that can't read the checker." },
  ];
  let selTech = "subq";
  function renderLayers() {
    const svg = $("#layers");
    svg.innerHTML = "";
    const d = el("defs", {}, svg);
    const f = el("filter", { id: "glow3", x: "-30%", y: "-30%", width: "160%", height: "160%" }, d);
    el("feGaussianBlur", { stdDeviation: 5, result: "b" }, f);
    const m = el("feMerge", {}, f); el("feMergeNode", { in: "b" }, m); el("feMergeNode", { in: "SourceGraphic" }, m);
    const PA = 118, PT = 10, gap = 66, ox = 190, oy = 30 + 6 * gap;
    // vertical guide lines through the exploded stack
    [[0, 0], [PA, 0], [0, PA], [PA, PA]].forEach(([x, y]) => {
      const [a1, b1] = iso(ox, oy, x, y, 0), [a2, b2] = iso(ox, oy, x, y, 6 * gap + PT);
      el("line", { x1: a1, y1: b1, x2: a2, y2: b2, stroke: "rgba(108,255,192,.18)", "stroke-dasharray": "3 5" }, svg);
    });
    const order = [...TECH].reverse(); // bottom first
    order.forEach((t, i) => {
      const z = i * gap, sel = t.id === selTech;
      const g = el("g", { class: `layer ${sel ? "sel" : selTech ? "dim" : ""}`, "data-id": t.id, tabindex: -1 }, svg);
      const b = box(ox, oy, 0, 0, z, PA, PA, PT);
      el("polygon", { points: pts(b.left), fill: t.color, opacity: sel ? 0.75 : 0.35 }, g);
      el("polygon", { points: pts(b.right), fill: t.color, opacity: sel ? 0.5 : 0.22 }, g);
      el("polygon", { points: pts(b.top), fill: t.color, "fill-opacity": sel ? 0.28 : 0.1, stroke: t.color, "stroke-width": sel ? 2 : 1, filter: sel ? "url(#glow3)" : "" }, g);
      if (t.id === "subq") {
        // long-context strip across the plate: a hint of every run read at once
        for (let k = 0; k < 40; k++) {
          const x0 = 12 + (k * (PA - 24)) / 40;
          el("polygon", { points: pts([iso(ox, oy, x0, PA / 2 - 10, z + PT), iso(ox, oy, x0 + 3, PA / 2 - 10, z + PT), iso(ox, oy, x0 + 3, PA / 2 + 10, z + PT), iso(ox, oy, x0, PA / 2 + 10, z + PT)]), fill: k % 7 === 3 ? "#FF4D6D" : "#5CE1FF", opacity: 0.8 }, g);
        }
      }
      const [tx, ty] = iso(ox, oy, PA, 0, z + PT / 2);
      el("line", { x1: tx + 4, y1: ty, x2: tx + 22, y2: ty, stroke: t.color, opacity: sel ? 1 : 0.5 }, g);
      const lab = el("text", { x: tx + 28, y: ty + 4, fill: sel ? t.color : "" }, g);
      lab.textContent = t.name;
      const sub = el("text", { class: "sub", x: tx + 28, y: ty + 21 }, g);
      sub.textContent = t.role.split(",")[0];
      g.addEventListener("click", () => selectTech(t.id));
    });
  }
  function renderBento() {
    $("#bento").innerHTML = TECH.map((t) => `<li class="${t.wide ? "wide" : ""}"><button data-id="${t.id}" aria-pressed="${t.id === selTech}" style="--c:${t.color}">
      <span class="who"><i style="background:${t.color};box-shadow:0 0 10px ${t.color}"></i>${esc(t.name)}</span>
      <span class="role">${esc(t.role)}</span><span class="job">${esc(t.job)}</span></button></li>`).join("");
    $("#bento").onclick = (e) => { const b = e.target.closest("button[data-id]"); if (b) selectTech(b.dataset.id); };
  }
  function selectTech(id) {
    selTech = id;
    renderLayers();
    document.querySelectorAll("#bento button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.id === id));
  }

  function renderBench(rows) {
    const color = { muse: "#A08CFF", subq: "#5CE1FF", gemini: "#F5C451" };
    const max = Math.max(...rows.map((r) => r.mean_score), 0.01);
    $("#bench").innerHTML = `<thead><tr><th>Model</th><th class="barcell"><span class="sr">Score bar</span></th><th>Score</th><th>Pass rate</th><th>Tokens per case</th><th>Seconds per case</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td><span class="m" style="color:${color[r.model] || "#E8FFF4"}">${esc(r.label)}</span><span class="p">${esc(r.provider || "")}</span></td>
        <td class="barcell"><div class="b"><span style="width:${(r.mean_score / max) * 100}%;background:${color[r.model] || "#6CFFC0"};box-shadow:0 0 10px ${color[r.model] || "#6CFFC0"}"></span></div></td>
        <td>${pct(r.mean_score)}</td><td>${pct(r.pass_rate)}%</td><td>${fmtTok(r.tokens)}</td><td>${r.seconds}s</td></tr>`).join("")}</tbody>`;
  }

  // ---------- clients ----------
  function renderClients(list) {
    $("#clients").innerHTML = list.map((c) => `<li><button data-id="${esc(c.client_id)}">
      <span class="nm">${esc(c.name)}</span><span class="sc ${c.passed === false ? "bad" : ""}">${c.score != null ? pct(c.score) : "–"}</span>
      <span class="meta">Age ${esc(c.age)}, risk ${esc(c.risk_score)} ${c.events.map((e) => `<span class="chip">${esc(e.type.replace("_", " "))}</span>`).join("")}</span>
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
        up.monthly_contribution != null ? `Raise monthly contribution to $${up.monthly_contribution.toLocaleString()}` : null,
        ...(rec.flags || []).map((f) => `Flag for review: ${f.replace(/_/g, " ")}`),
      ].filter(Boolean);
      const last = c.history[c.history.length - 1];
      body.innerHTML = `
        <h3 id="sheet-title">${esc(c.name)}</h3>
        <p class="sub">Age ${esc(c.age)}, risk score ${esc(c.risk_score)}, served by playbook v${esc(c.agent_version)}</p>
        ${c.events.length ? `<p style="margin-top:10px">${c.events.map((e) => `<span class="chip">${esc(e.type.replace("_", " "))} on ${esc(e.date)}</span>`).join(" ")}</p>` : ""}
        <h4>Latest recommendation</h4>
        ${trades.length ? `<ul class="trades">${trades.map((t) => `<li><span class="act ${t.action}">${t.action === "sell" ? "Sell" : "Buy"}</span><span>${esc(t.symbol)}</span>
          <span class="amt">$${Number(t.amount_usd).toLocaleString()}</span><span class="why">${esc(why[t.reason_ref] || t.reason_ref)}</span></li>`).join("")}</ul>`
          : `<p class="sub">No trades. ${esc(rec.no_action_reason || "")}</p>`}
        ${updates.length ? `<h4>Profile changes</h4><ul>${updates.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
        <h4>This client's score by playbook version</h4>
        <div class="hist" role="img" aria-label="Score by version">${c.history.map((h) => `<div class="${h.passed ? "" : "fail"}" style="height:${Math.max(6, h.score * 100)}%"><span>v${h.version}</span></div>`).join("")}</div>
        ${last && last.violations.length ? `<h4>Open issues</h4><ul>${last.violations.map((x) => `<li>${esc(x.rule)}: ${esc(x.detail)}</li>`).join("")}</ul>` : `<p class="sub">Passes every policy check on the current playbook.</p>`}`;
    } catch (e) {
      body.innerHTML = `<h3 id="sheet-title">Client didn't load</h3><p class="sub">${esc(e.message)}. Close this and try again.</p>`;
    }
  }

  // ---------- controls ----------
  function stopPlay() { clearInterval(state.playing); state.playing = null; $("#play").setAttribute("aria-pressed", "false"); $("#play").textContent = "Play"; }
  function bind() {
    $("#next").addEventListener("click", () => { stopPlay(); show(state.i === state.steps.length - 1 ? 0 : state.i + 1); });
    $("#prev").addEventListener("click", () => { stopPlay(); show(state.i - 1); });
    $("#play").addEventListener("click", () => {
      if (state.playing) return stopPlay();
      if (state.i === state.steps.length - 1) show(0);
      $("#play").setAttribute("aria-pressed", "true"); $("#play").textContent = "Pause";
      state.playing = setInterval(() => { if (state.i >= state.steps.length - 1) stopPlay(); else show(state.i + 1); }, 5000);
    });
    $("#steps").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { stopPlay(); show(+b.dataset.i); } });
    document.addEventListener("keydown", (e) => {
      if ($("#sheet").open || e.target.closest("input, textarea, [role=tablist]")) return;
      if (e.key === "ArrowRight") { stopPlay(); show(state.i + 1); }
      if (e.key === "ArrowLeft") { stopPlay(); show(state.i - 1); }
    });
    $("#clients").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) openClient(b.dataset.id); });
    $("#sheet-close").addEventListener("click", () => $("#sheet").close());
    $("#sheet").addEventListener("click", (e) => { if (e.target === $("#sheet")) $("#sheet").close(); });
  }

  async function liveDot() {
    try {
      const r = await fetch("/api/live/status");
      if (!r.ok) return;
      const s = await r.json();
      const a = document.querySelector(".live-link");
      a.classList.toggle("on", !!s.active);
      a.title = s.active ? "A training run is in progress" : s.last_activity ? "No runs in the last 2 minutes" : "No training run yet";
    } catch (_) { /* the live view is optional on this page */ }
  }

  async function init() {
    liveDot();
    setInterval(() => { if (!document.hidden) liveDot(); }, 20000);
    bind();
    bindHow();
    renderLayers();
    renderBento();
    try {
      const [ov, versions, drift, clients, analysis, bench] = await Promise.all([
        get("/api/overview"), get("/api/versions"), get("/api/drift"), get("/api/clients"),
        get("/api/analysis").catch(() => []), get("/api/benchmark").catch(() => [])]);
      state.versions = versions; state.drift = drift; state.analysis = analysis;
      $("#source").hidden = ov.source !== "demo";
      const det = await Promise.all(versions.map((g) => get(`/api/versions/${g.version}`).catch(() => null)));
      det.forEach((d) => { if (d) state.details[d.version] = d; });
      state.steps = buildSteps(versions, drift, analysis);
      const kindAttr = (k) => (k === "green" ? "ship" : k);
      $("#steps").innerHTML = state.steps.map((s, k) => `<li><button data-i="${k}" data-kind="${kindAttr(s.kind)}"><i aria-hidden="true"></i>${esc(s.label)}</button></li>`).join("");
      renderClients(clients);
      if (bench.length) renderBench(bench); else $(".bench").hidden = true;
      const m = /#step-(\d+)/.exec(location.hash);
      show(m ? +m[1] - 1 : 0);
      let rt;
      addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => renderCurve(state.steps[state.i]), 150); });
    } catch (e) {
      $("#step-title").textContent = "Data didn't load";
      $("#step-body").textContent = `${e.message}. Check that the API is running, then reload.`;
    }
  }
  init();
})();
