/* Ballast: guided replay of a self-improving portfolio agent. Vanilla JS, no build. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => Math.round(x * 100);
  const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
  const HARD = new Set(["valid_output", "risk_band", "emergency_fund", "concentration", "cited"]);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = { steps: [], i: 0, details: {}, versions: [], drift: [], playing: null, rendered: new Set() };

  const DEMO = new URLSearchParams(location.search).get("demo") === "1";
  async function get(p) {
    const r = await fetch(DEMO ? `${p}${p.includes("?") ? "&" : "?"}demo=1` : p);
    if (!r.ok) throw new Error(`${p} returned ${r.status}`);
    return r.json();
  }

  // ---------- step model ----------
  function buildSteps(versions, drift) {
    const byV = Object.fromEntries(versions.map((g) => [g.version, g]));
    const base = byV[0] || versions[0];
    const evs = [
      ...versions.map((g) => ({ t: g.created_at, type: "gen", g })),
      ...drift.filter((d) => d.action !== "none").map((d) => ({ t: d.time, type: "drift", d })),
    ].sort((a, b) => String(a.t).localeCompare(String(b.t)));

    const slabs = [];
    let light = "green";
    const steps = [];
    for (const e of evs) {
      const s = { light, slabs: null, chartVersions: null };
      if (e.type === "gen") {
        const g = e.g, p = byV[g.parent];
        const score = g.test.mean_score;
        s.version = g.version;
        s.score = score; s.scoreLabel = "average policy score on unseen clients";
        s.delta = base && g.version !== base.version ? { v: score - base.test.mean_score, label: "vs v0" } : null;
        s.diffVersion = g.version;
        s.viol = { kind: "version", version: g.version };
        if (g.parent == null) {
          Object.assign(s, { kind: "base", label: `v${g.version} baseline`, title: `v${g.version}: the starting playbook`,
            body: `${g.changelog || "The first playbook."} It has no habits for life events yet, so this is the bar every upgrade has to clear.`,
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
          Object.assign(s, { kind: "ship", label: `v${g.version} ships`, title: `v${g.version} ships`,
            body: `${g.changelog}${from != null ? ` Unseen clients go from ${from} to ${pct(score)}.` : ""}`,
            gate: gateTraining(g, p), stamp: ["Shipped", "ship"], tone: "good" });
          slabs.push({ v: g.version, status: "ship", score });
        }
      } else {
        const d = e.d;
        s.version = d.to_version;
        s.score = d.rolling_score; s.scoreLabel = "rolling score on the latest live cases";
        s.delta = { v: d.rolling_score - d.baseline, label: "vs shipped baseline" };
        s.viol = { kind: "drift", list: d.violations };
        light = d.level; s.light = light;
        const n = (d.case_ids || []).length;
        if (d.action === "rollback") {
          Object.assign(s, { kind: "red", label: "Drift caught", title: "Drift caught",
            body: `New conditions hit v${d.from_version}: ${n} live cases broke rules it always passed. Ballast rolls back to v${d.to_version} right away.`,
            gate: gateContain(d), stamp: ["Rolled back", "block"], tone: "alarm", diffNote: `Rolled back from v${d.from_version} to v${d.to_version}. The playbook hasn't changed yet.` });
          const sl = slabs.find((x) => x.v === d.from_version);
          if (sl) sl.status = "rolled";
        } else if (d.action === "realign") {
          Object.assign(s, { kind: "muse", label: "Muse realigns", title: "Muse writes a fix",
            body: `The ${n} drifted cases become tests. Muse reads their violations and rewrites the playbook. After 3 failed attempts, a person takes over.`,
            gate: gateRealign(d), stamp: ["Fixing", "hold"], tone: "alarm", diffNote: `Muse is reading ${n} drifted cases.` });
        } else if (d.action === "shipped_fix") {
          const g = byV[d.to_version];
          Object.assign(s, { kind: "green", label: "Aligned", title: "Aligned again",
            body: `v${d.to_version} is live. The rolling score is ${pct(d.rolling_score)}, against a baseline of ${pct(d.baseline)}. The drift became a lesson the agent keeps.`,
            gate: g ? gateDriftFix(g) : gateRealign(d), stamp: ["Aligned", "ship"], tone: "good" });
          s.diffVersion = d.to_version;
          s.viol = { kind: "version", version: d.to_version };
        } else if (d.action === "escalated") {
          Object.assign(s, { kind: "red", label: "Escalated", title: "Escalated to a person",
            body: `Muse couldn't produce a fix that passes in 3 attempts. v${d.to_version} stays live and an advisor is notified.`,
            gate: gateRealign(d), stamp: ["Escalated", "block"], tone: "alarm" });
        } else {
          Object.assign(s, { kind: d.level === "red" ? "red" : "muse", label: `Drift ${d.level}`, title: `Drift indicator: ${d.level}`,
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
  function gateBaseline(g) {
    return [chk(null, "Beats parent on unseen clients", "Baseline", "every upgrade must beat this"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "golden clients that must always pass"),
      chk(null, "Gemini compliance review", "Not needed", "nothing changed yet")];
  }
  function gateTraining(g, p) {
    const gain = p ? g.test.mean_score - p.test.mean_score : 0;
    const c = g.compliance;
    return [chk(gain >= 0.02, "Beats parent on unseen clients", sgn(gain), "needs +0.02 or more"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", c ? (c.verdict === "approve" ? "Approved" : "Blocked") : "Skipped", c ? c.note : "")];
  }
  function gateDriftFix(g) {
    const m = /(\d+)\/(\d+)/.exec(g.reason || "");
    const c = g.compliance;
    return [chk(true, "Passes the drifted cases", m ? `${m[1]} of ${m[2]}` : "Passed", "captured as new tests"),
      chk(g.regression.pass_rate >= 1, "Regression set", `${pct(g.regression.pass_rate)}%`, "must stay at 100%"),
      chk(c ? c.verdict === "approve" : null, "Gemini compliance review", c ? (c.verdict === "approve" ? "Approved" : "Blocked") : "Skipped", c ? c.note : "")];
  }
  function gateContain(d) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || ""),
      chk(true, "Contain", `Back to v${d.to_version}`, `v${d.from_version} pulled from service`),
      chk(true, "Capture", `${(d.case_ids || []).length} cases`, "added to the test set")];
  }
  function gateRealign(d) {
    return [chk(false, "Detect", d.level === "red" ? "Red" : "Yellow", d.violations[0]?.detail || "no new violations"),
      chk(true, "Contain", `v${d.to_version} live`, "last known-good playbook"),
      chk(null, "Realign", "Muse, attempt 1", "up to 3 before a person steps in")];
  }

  // ---------- render: step ----------
  function show(i, { focus = false } = {}) {
    const steps = state.steps;
    if (!steps.length) return;
    state.i = Math.max(0, Math.min(steps.length - 1, i));
    const s = steps[state.i];
    $("#step-count").textContent = `Step ${state.i + 1} of ${steps.length}`;
    $("#step-title").textContent = s.title;
    $("#step-body").textContent = s.body;
    const sc = $(".score");
    sc.dataset.tone = s.tone || "";
    $("#score-num").textContent = pct(s.score);
    $("#score-label").textContent = s.scoreLabel;
    const dl = $("#score-delta");
    if (s.delta) { dl.textContent = `${s.delta.v >= 0 ? "+" : "−"}${Math.abs(pct(s.delta.v))} points ${s.delta.label}`; dl.className = "delta" + (s.delta.v < 0 ? " neg" : ""); }
    else { dl.textContent = ""; }
    $("#prev").disabled = state.i === 0;
    $("#next").textContent = state.i === steps.length - 1 ? "Start over" : "Next step";
    document.querySelectorAll("#steps button").forEach((b, k) => {
      b.toggleAttribute("aria-current", k === state.i);
      if (k === state.i) b.setAttribute("aria-current", "step");
      b.classList.toggle("done", k < state.i);
      if (k === state.i && b.scrollIntoView) b.scrollIntoView({ block: "nearest", inline: "center", behavior: reduced ? "auto" : "smooth" });
    });
    setLight(s.light);
    renderStack(s);
    renderGate(s);
    renderViol(s);
    renderDiff(s);
    renderCurve(s);
    history.replaceState(null, "", `#step-${state.i + 1}`);
    if (focus) $("#step-title").focus?.();
  }

  function setLight(level) {
    const el = $("#light");
    el.dataset.level = level;
    el.querySelector("b").textContent = level === "red" ? "Drift" : level === "yellow" ? "Verifying" : "Aligned";
  }

  // ---------- render: isometric stack ----------
  const C = 0.866, S = 0.5, A = 118, T = 26;
  function iso(ox, oy, x, y, z) { return [ox + (x - y) * C, oy + (x + y) * S - z]; }
  const pts = (arr) => arr.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }

  function renderStack(s) {
    const svg = $("#stack");
    svg.setAttribute("viewBox", "0 0 560 500");
    svg.innerHTML = "";
    const defs = el("defs", {}, svg);
    const pat = el("pattern", { id: "hatch", width: 7, height: 7, patternUnits: "userSpaceOnUse", patternTransform: "rotate(35)" }, defs);
    el("rect", { width: 7, height: 7, fill: "var(--plate)" }, pat);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 7, stroke: "var(--seal)", "stroke-width": 2.2 }, pat);

    // ground plate
    const gx = 280, gy = 352;
    el("polygon", { points: pts([iso(gx, gy, -26, -26, -8), iso(gx, gy, A + 26, -26, -8), iso(gx, gy, A + 26, A + 26, -8), iso(gx, gy, -26, A + 26, -8)]),
      fill: "var(--plate)", stroke: "var(--line)" }, svg);

    const shipped = s.slabs.filter((x) => x.status === "ship").length;
    const step = Math.min(T + 9, 300 / Math.max(1, shipped));
    let level = 0;
    const draws = [];
    for (const sl of s.slabs) {
      if (sl.status === "ship") { draws.push({ sl, dx: 0, z: level * step }); level++; }
      else if (sl.status === "reject") draws.push({ sl, dx: -158, z: level * step });
      else draws.push({ sl, dx: 158, z: Math.max(0, level - 0.4) * step + 18 });
    }
    // paint back-to-front: side slabs first, then stack bottom-up
    draws.sort((a, b) => (a.dx === 0) - (b.dx === 0) || a.z - b.z);
    for (const d of draws) drawSlab(svg, gx + d.dx, gy, d.z, d.sl, d.sl.v === s.version);
    state.rendered = new Set(s.slabs.map((x) => `${x.v}:${x.status}`));
    state.painted = true;
    $("#stack-cap").textContent = s.kind === "red" ? "The drifted version slides off the stack. The last good one carries the load."
      : s.kind === "reject" ? "A rejected candidate never joins the stack."
      : "Each slab is a playbook version that passed the gate.";
  }

  function drawSlab(svg, ox, oy, z, sl, active) {
    const isNew = !state.rendered.has(`${sl.v}:${sl.status}`);
    const g = el("g", { class: `slab ${sl.status === "reject" ? "rejected" : sl.status === "rolled" ? "rolled" : ""} ${active ? "active" : ""}` }, svg);
    const top = [iso(ox, oy, 0, 0, z + T), iso(ox, oy, A, 0, z + T), iso(ox, oy, A, A, z + T), iso(ox, oy, 0, A, z + T)];
    const left = [iso(ox, oy, 0, A, z), iso(ox, oy, A, A, z), iso(ox, oy, A, A, z + T), iso(ox, oy, 0, A, z + T)];
    const right = [iso(ox, oy, A, 0, z), iso(ox, oy, A, A, z), iso(ox, oy, A, A, z + T), iso(ox, oy, A, 0, z + T)];
    el("polygon", { class: "left", points: pts(left) }, g);
    el("polygon", { class: "right", points: pts(right) }, g);
    el("polygon", { class: "top", points: pts(top) }, g);
    // engraved score bar on the top face: fill proportional to score
    const f = Math.max(0.04, Math.min(1, sl.score));
    const bar = [iso(ox, oy, 14, A / 2 - 7, z + T), iso(ox, oy, 14 + (A - 28) * f, A / 2 - 7, z + T), iso(ox, oy, 14 + (A - 28) * f, A / 2 + 7, z + T), iso(ox, oy, 14, A / 2 + 7, z + T)];
    el("polygon", { points: pts(bar), fill: "var(--ink)", opacity: sl.status === "ship" ? 0.28 : 0.15 }, g);
    [top, left, right].forEach((p) => el("polygon", { class: "edge", points: pts(p) }, g));
    const [lx, ly] = iso(ox, oy, A, A, z + T / 2);
    const label = el("text", { x: (lx + 10).toFixed(1), y: (ly + 5).toFixed(1) }, g);
    const t1 = el("tspan", { class: "big" }, label); t1.textContent = `v${sl.v}`;
    const t2 = el("tspan", { dx: 6 }, label); t2.textContent = `${pct(sl.score)}`;
    if (sl.status === "reject") { const t3 = el("tspan", { dx: 6, fill: "var(--seal)" }, label); t3.textContent = "rejected"; }
    if (sl.status === "rolled") { const t3 = el("tspan", { dx: 6, fill: "var(--alarm)" }, label); t3.textContent = "rolled back"; }
    if (isNew && !reduced && state.painted) {
      g.classList.add("entering");
      requestAnimationFrame(() => requestAnimationFrame(() => g.classList.remove("entering")));
    }
  }

  // ---------- render: gate ----------
  function renderGate(s) {
    $("#gate").innerHTML = s.gate.map((c) => `
      <li class="${c.ok == null ? "pending" : ""}">
        <span class="k"><span class="mark ${c.ok === true ? "ok" : c.ok === false ? "no" : ""}" aria-hidden="true">${c.ok === true ? "✓" : c.ok === false ? "✕" : "–"}</span>${esc(c.k)}</span>
        <span class="v">${esc(c.v)}</span>
        <span class="n">${esc(c.n)}</span>
      </li>`).join("");
    const st = $("#stamp");
    st.textContent = s.stamp[0];
    st.className = `stamp ${s.stamp[1]}`;
    if (!reduced) { void st.offsetWidth; st.classList.add("pop"); }
  }

  // ---------- render: violations ----------
  function renderViol(s) {
    const ul = $("#viol");
    if (s.viol.kind === "drift") {
      $("#viol-sub").textContent = "Hard violations on live cases that triggered the drift check";
      ul.innerHTML = s.viol.list.length ? s.viol.list.map((x) => `
        <li class="${x.severity === "hard" ? "hard" : ""}"><span class="rule">${esc(x.rule)}<span class="sev">${esc(x.severity)}</span></span><span></span>
        <span class="detail">${esc(x.detail)}</span></li>`).join("") : `<li class="empty">No violations.</li>`;
      return;
    }
    const v = state.versions.find((g) => g.version === s.viol.version);
    const det = state.details[s.viol.version];
    const counts = Object.entries(v?.violations_by_rule || {}).sort((a, b) => b[1] - a[1]);
    $("#viol-sub").textContent = `Playbook v${s.viol.version} on unseen clients: cases with each violation`;
    const max = Math.max(1, ...counts.map((c) => c[1]));
    ul.innerHTML = counts.length ? counts.map(([rule, n]) => {
      const ex = det?.sample_violations?.find((x) => x.rule === rule);
      return `<li class="${HARD.has(rule) ? "hard" : ""}">
        <span class="rule">${esc(rule)}<span class="sev">${HARD.has(rule) ? "hard" : "soft"}</span></span>
        <span class="cnt">${n}</span>
        <span class="bar"><span style="width:${(n / max) * 100}%"></span></span>
        ${ex ? `<span class="detail">${esc(ex.case_id)}: ${esc(ex.detail)}</span>` : ""}</li>`;
    }).join("") : `<li class="empty">No violations on unseen clients.</li>`;
  }

  // ---------- render: diff ----------
  function renderDiff(s) {
    const pre = $("#diff");
    if (s.diffNote && s.kind !== "green") { $("#diff-sub").textContent = "No new playbook at this step"; pre.innerHTML = `<span class="ctx">${esc(s.diffNote)}</span>`; return; }
    const d = state.details[s.diffVersion];
    if (!d) { pre.innerHTML = `<span class="ctx">Loading playbook v${s.diffVersion}.</span>`; return; }
    $("#diff-sub").textContent = d.parent == null ? `Playbook v${d.version}, the starting point` : `v${d.parent} to v${d.version}: ${d.changelog}`;
    const lines = d.parent == null ? d.yaml.split("\n").map((l) => " " + l) : d.diff.filter((l) => !l.startsWith("---") && !l.startsWith("+++"));
    pre.innerHTML = lines.map((l) => {
      const c = l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "@" ? "hunk" : "ctx";
      const txt = c === "hunk" ? "…" : l.slice(1);
      return `<span class="${c}">${esc(txt) || " "}</span>`;
    }).join("");
  }

  // ---------- render: curve ----------
  function renderCurve(s) {
    const svg = $("#curve");
    svg.innerHTML = "";
    const W = Math.round(Math.max(340, Math.min(720, svg.clientWidth || 720))), H = W < 500 ? 240 : 260, L = 36, R = 16, Tp = 24, B = 40;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const vs = state.versions;
    if (!vs.length) return;
    const xs = (k) => L + (k * (W - L - R)) / Math.max(1, vs.length - 1);
    const lo = 0.4, hi = 1.0;
    const ys = (v) => Tp + (1 - (v - lo) / (hi - lo)) * (H - Tp - B);
    [0.4, 0.6, 0.8, 1.0].forEach((t) => {
      el("line", { class: "grid", x1: L, x2: W - R, y1: ys(t), y2: ys(t) }, svg);
      el("text", { class: "axis", x: L - 8, y: ys(t) + 4, "text-anchor": "end" }, svg).textContent = pct(t);
    });
    const seen = (g) => s.chartVersions.has(g.version);
    // drift band between rolled-back version and the fix
    const red = state.drift.find((d) => d.action === "rollback");
    if (red && s.driftSeen) {
      const k1 = vs.findIndex((g) => g.version === red.from_version);
      const fix = state.drift.find((d) => d.action === "shipped_fix");
      const k2 = fix ? vs.findIndex((g) => g.version === fix.to_version) : vs.length - 1;
      if (k1 >= 0) {
        const x1 = xs(k1), x2 = xs(Math.max(k2, k1 + 1));
        el("rect", { class: "drift-band", x: x1, y: Tp, width: x2 - x1, height: H - Tp - B, rx: 6 }, svg);
        const mx = (x1 + x2) / 2;
        el("circle", { cx: mx, cy: ys(Math.max(lo, red.rolling_score)), r: 6, fill: "var(--alarm)" }, svg);
        el("text", { class: "drift-lbl", x: mx, y: ys(Math.max(lo, red.rolling_score)) + 22, "text-anchor": "middle" }, svg).textContent = `drift ${pct(red.rolling_score)}, rolled back`;
      }
    }
    const ship = vs.map((g, k) => ({ g, k })).filter((o) => o.g.decision === "shipped");
    const shown = ship.filter((o) => seen(o.g));
    if (shown.length) {
      const d = shown.map((o, j) => `${j ? "L" : "M"}${xs(o.k).toFixed(1)},${ys(o.g.test.mean_score).toFixed(1)}`).join("");
      const last = shown[shown.length - 1];
      el("path", { class: "area", d: `${d}L${xs(last.k)},${H - B}L${xs(shown[0].k)},${H - B}Z` }, svg);
      el("path", { class: "ln", d }, svg);
    }
    vs.forEach((g, k) => {
      const on = seen(g);
      const grp = el("g", { class: on ? "" : "future" }, svg);
      const rej = g.decision === "rejected";
      el("circle", { class: `pt ${rej ? "rej" : ""} ${g.version === s.version ? "cur" : ""}`, cx: xs(k), cy: ys(g.test.mean_score), r: g.version === s.version ? 8 : 6 }, grp);
      el("text", { class: "vlbl", x: xs(k), y: H - B + 22, "text-anchor": "middle" }, grp).textContent = `v${g.version}`;
      if (rej) el("text", { class: "rej-lbl", x: xs(k), y: ys(g.test.mean_score) + 22, "text-anchor": "middle" }, grp).textContent = "rejected";
      else if (on) el("text", { class: "axis", x: xs(k), y: ys(g.test.mean_score) - 14, "text-anchor": "middle" }, grp).textContent = pct(g.test.mean_score);
    });
  }

  // ---------- rosette (banknote guilloché) ----------
  function rosette() {
    const svg = $("#rosette");
    const paths = [];
    for (let ring = 0; ring < 3; ring++) {
      const R = 110 + ring * 42, amp = 14 + ring * 6, n = 9 + ring * 4;
      for (let k = 0; k < 14; k++) {
        const ph = (k / 14) * Math.PI * 2 / n * 2;
        let d = "";
        for (let a = 0; a <= 360; a += 2) {
          const t = (a * Math.PI) / 180;
          const r = R + amp * Math.sin(n * t + ph);
          d += `${a ? "L" : "M"}${(r * Math.cos(t)).toFixed(1)},${(r * Math.sin(t)).toFixed(1)}`;
        }
        paths.push(`<path d="${d}Z"/>`);
      }
    }
    svg.innerHTML = paths.join("");
  }

  // ---------- clients ----------
  function renderClients(list) {
    $("#clients").innerHTML = list.map((c) => `
      <li><button data-id="${esc(c.client_id)}">
        <span class="nm">${esc(c.name)}</span>
        <span class="sc ${c.passed === false ? "bad" : ""}">${c.score != null ? pct(c.score) : "–"}</span>
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
      const trades = rec.trades || [];
      const up = rec.profile_updates || {};
      const updates = [
        ...(up.goals_add || []).map((g) => `Add ${g.type} goal for ${g.target_year}`),
        up.monthly_contribution != null ? `Raise monthly contribution to $${up.monthly_contribution.toLocaleString()}` : null,
        ...(rec.flags || []).map((f) => `Flag for review: ${f.replace(/_/g, " ")}`),
      ].filter(Boolean);
      const last = c.history[c.history.length - 1];
      body.innerHTML = `
        <h3 id="sheet-title">${esc(c.name)}</h3>
        <p class="sub">Age ${esc(c.age)}, risk score ${esc(c.risk_score)}, served by playbook v${esc(c.agent_version)}</p>
        ${c.events.length ? `<p>${c.events.map((e) => `<span class="chip">${esc(e.type.replace("_", " "))} on ${esc(e.date)}</span>`).join(" ")}</p>` : ""}
        <h4>Latest recommendation</h4>
        ${trades.length ? `<ul class="trades">${trades.map((t) => `
          <li><span class="act ${t.action}">${t.action === "sell" ? "Sell" : "Buy"}</span><span>${esc(t.symbol)}</span>
          <span class="amt">$${Number(t.amount_usd).toLocaleString()}</span>
          <span class="why">${esc(why[t.reason_ref] || t.reason_ref)}</span></li>`).join("")}</ul>`
          : `<p class="sub">No trades. ${esc(rec.no_action_reason || "")}</p>`}
        ${updates.length ? `<h4>Profile changes</h4><ul>${updates.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
        <h4>This client's score by playbook version</h4>
        <div class="hist" role="img" aria-label="Score by version">${c.history.map((h) => `<div class="${h.passed ? "" : "fail"}" style="height:${Math.max(6, h.score * 100)}%"><span>v${h.version}</span></div>`).join("")}</div>
        ${last && last.violations.length ? `<h4>Open issues</h4><ul>${last.violations.map((x) => `<li>${esc(x.rule)}: ${esc(x.detail)}</li>`).join("")}</ul>` : `<p class="sub" style="margin-top:30px">Passes every policy check on the current playbook.</p>`}`;
    } catch (e) {
      body.innerHTML = `<h3 id="sheet-title">Client not loaded</h3><p class="sub">${esc(e.message)}. Close this and try again.</p>`;
    }
  }

  // ---------- controls ----------
  function stopPlay() {
    clearInterval(state.playing); state.playing = null;
    $("#play").setAttribute("aria-pressed", "false"); $("#play").textContent = "Play replay";
  }
  function bind() {
    $("#next").addEventListener("click", () => { stopPlay(); show(state.i === state.steps.length - 1 ? 0 : state.i + 1); });
    $("#prev").addEventListener("click", () => { stopPlay(); show(state.i - 1); });
    $("#play").addEventListener("click", () => {
      if (state.playing) return stopPlay();
      if (state.i === state.steps.length - 1) show(0);
      $("#play").setAttribute("aria-pressed", "true"); $("#play").textContent = "Pause";
      state.playing = setInterval(() => { if (state.i >= state.steps.length - 1) stopPlay(); else show(state.i + 1); }, 4500);
    });
    $("#steps").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { stopPlay(); show(+b.dataset.i); } });
    document.addEventListener("keydown", (e) => {
      if ($("#sheet").open || e.target.closest("input, textarea")) return;
      if (e.key === "ArrowRight") { stopPlay(); show(state.i + 1); }
      if (e.key === "ArrowLeft") { stopPlay(); show(state.i - 1); }
    });
    $("#clients").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) openClient(b.dataset.id); });
    $("#sheet-close").addEventListener("click", () => $("#sheet").close());
    $("#sheet").addEventListener("click", (e) => { if (e.target === $("#sheet")) $("#sheet").close(); });
  }

  async function init() {
    const th = new URLSearchParams(location.search).get("theme");
    if (th === "light" || th === "dark") document.documentElement.dataset.theme = th;
    rosette();
    bind();
    try {
      const [ov, versions, drift, clients] = await Promise.all([get("/api/overview"), get("/api/versions"), get("/api/drift"), get("/api/clients")]);
      state.versions = versions; state.drift = drift;
      $("#source").hidden = ov.source !== "demo";
      const det = await Promise.all(versions.map((g) => get(`/api/versions/${g.version}`).catch(() => null)));
      det.forEach((d) => { if (d) state.details[d.version] = d; });
      state.steps = buildSteps(versions, drift);
      $("#steps").innerHTML = state.steps.map((s, k) => `<li><button data-i="${k}" data-kind="${s.kind === "green" ? "ship" : s.kind}"><i aria-hidden="true"></i>${esc(s.label)}</button></li>`).join("");
      renderClients(clients);
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
