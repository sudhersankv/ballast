/* ballast. /architecture: glossary filter, stepped loop diagrams, handler grid + system map. Vanilla JS. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const tok = (n) => getComputedStyle(document.documentElement).getPropertyValue(`--${n}`).trim();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const el = (tag, attrs = {}, parent) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (parent) parent.appendChild(n); return n; };
  const f3 = (x) => (x == null ? "-" : Number(x).toFixed(3));
  const R = { board: null, journeys: [] };

  // ---------- 1. live numbers ----------
  function renderNums() {
    const b = R.board, vs = (b && b.versions) || [];
    const v0 = vs.find((v) => v.version === 0), v1 = vs.find((v) => v.version === 1);
    const sums = R.journeys.map((j) => j.summary).filter(Boolean);
    const mean = (k) => sums.length ? sums.reduce((a, s) => a + Number(s[k] || 0), 0) / sums.length : null;
    const tape = (x) => `<div class="tape" aria-hidden="true"><span class="fill" style="width:${Math.max(0, Math.min(100, x * 100)).toFixed(1)}%"></span></div>`;
    const row = (k, x, right) => `<div class="bd-row"><span>${k}</span>${tape(x)}<b>${f3(x)}</b><em>${right}</em></div>`;
    $("#a-nums").innerHTML = `
      <div class="bd-head"><span>From the live system</span><span>${esc(b?.db || "ballast_muse")}</span></div>
      <div class="bd-rows">
        ${v0 ? row("v0 test", v0.test.mean, `${v0.test.passed}/${v0.test.n}`) : ""}
        ${v1 ? row(`v1 test`, v1.test.mean, `${v1.test.passed}/${v1.test.n} ${v1.decision === "rejected" ? "✕" : "✓"}`) : ""}
        ${row("Snap gate F1", 0.94, "39 ev")}
        ${sums.length ? row("holdout, generic", mean("holdout_mean_start"), `${sums.length} cl`) + row("holdout, own agent", mean("holdout_mean_final"), `${sums.length} cl`) : ""}
      </div>
      <p class="bd-note">${v1 ? `v1 ${v1.decision}: ${esc(v1.reason || "")}. ` : ""}Journey rows average the clients' holdout scores (generic playbook vs the client's own agent).</p>`;
  }

  // ---------- 4. glossary ----------
  const GLOSS = [
    ["Client case", "One client at one point in time: four files — profile (client.json), holdings (holdings.json), market prices and 4 years of history (market.json), and life events since the last review (events.json)."],
    ["Agent", "The AI that reviews a case and writes recommendation.json: trades, target mix, reasons, profile updates (e.g. raise the monthly contribution), and flags for a human."],
    ["Harness", "The program that runs the agent: gives it the case files, a few tools (read files, run a calculator script, write a file), a turn limit and a time limit. We use the Pi coding-agent harness."],
    ["Playbook", "The agent's instructions: a short prompt, a set of skills (step-by-step habits for specific situations), a turn limit, and the lessons it has learned. The only thing that ever changes."],
    ["Skill", "One named habit inside the playbook, e.g. emergency-fund-priority: \"when there is a layoff, raise cash to six months first.\""],
    ["Lesson", "A plain-language sentence describing what the agent learned, with the root cause, the triggering event, and the rule it fixes."],
    ["Rule", "A fixed policy check, e.g. \"cash must cover 3 months of expenses, 6 after a layoff.\" Hard rules must pass; soft rules lower the score."],
    ["Checker", "The code that grades a recommendation against the 10 rules. Gives a score (0–1) and a list of violations with numbers."],
    ["Backtest", "Replays the 12 months of real market history after the review date (which the agent never saw) to see what the recommendation would have done: return, worst drop, whether the client ran out of cash and had to sell."],
    ["Mentor", "The AI that reads failures and writes the next playbook. It must name the root cause and the event that triggered it."],
    ["Gate", "The set of checks a new playbook must pass before it ships."],
    ["Version / generation", "Each playbook gets a number: v0, v1, v2… One round of \"test, learn, gate\" is a generation."],
    ["Practice / test / regression / drift", "Groups of cases. The mentor only ever sees practice failures. Test decides shipping. Regression must not break. Drift is held back to test what happens when the world changes."],
    ["Client journey", "One client reviewed every quarter for 2.5 years (10 checkpoints), through a real market period, with life events along the way. The first 5 are for learning, the last 5 (holdout) prove it."],
    ["Drift", "The agent starting to fail on rules it used to pass, usually because something new happened."],
    ["Rollback", "Switching back to the last version that was proven good."],
    ["Snap gate", "A fast yes/no check (from SubQ's decision model) on each new life event: which rules are at risk, and does the playbook cover this?"],
    ["Control arm", "A deliberate fake: the mentor is fed shuffled failures. If its changes still \"helped,\" our improvements would be luck. They shouldn't."],
  ];
  const CODEISH = /\b([a-z_]+\.(json|py)|emergency-fund-priority|v\d)\b/g;
  function renderGloss() {
    const q = $("#gloss-q").value.trim().toLowerCase();
    const hits = GLOSS.filter(([t, d]) => !q || t.toLowerCase().includes(q) || d.toLowerCase().includes(q));
    $("#gloss").innerHTML = hits.map(([t, d]) => `<div class="g-item"><dt class="mono">${esc(t)}</dt><dd>${esc(d).replace(CODEISH, '<span class="mono">$1</span>')}</dd></div>`).join("")
      || `<p class="muted">No term matches "${esc(q)}". Clear the filter to see all ${GLOSS.length}.</p>`;
    $("#gloss-n").textContent = `${hits.length} of ${GLOSS.length}`;
  }

  // ---------- 5. the four loops ----------
  const A = (k, v) => ({ k, v });
  function loops() {
    const v0 = R.board?.versions?.find((v) => v.version === 0), v1 = R.board?.versions?.find((v) => v.version === 1);
    const j = R.journeys.find((x) => (x.lessons || []).length) || R.journeys[0];
    const jl = j && j.lessons && j.lessons[0];
    const jcp = j && jl && j.checkpoints.find((c) => c.id === jl.at);
    const sm = j && j.summary;
    return [
      { id: "a", tab: "5a One client review", title: "One client review (the inner loop)",
        nodes: [["case", 0, 0, "case files", "4 JSON files"], ["folder", 1, 0, "fresh folder", "+ portfolio.py"], ["pb", 0, 1, "playbook", "prompt + skills"], ["sys", 1, 1, "system prompt", "1 file per skill"],
          ["agent", 2, 0, "Pi + Muse", "sandbox"], ["rec", 3, 0, "rec.json", "recommendation"], ["check", 3, 1, "checker", "10 rules"], ["bt", 4, 1, "backtest", "12 held-out mo"], ["db", 5, 0, "MongoDB", "runs"], ["live", 5, 1, "live view", "/live"]],
        edges: [["case", "folder"], ["folder", "agent"], ["pb", "sys"], ["sys", "agent"], ["agent", "rec"], ["rec", "check"], ["check", "bt"], ["rec", "db"], ["bt", "db"], ["db", "live"]],
        steps: [
          ["Prepare the case.", "The four case files are copied into a fresh, empty folder, plus a small calculator script (portfolio.py) the agent can use to see current weights and test its trades.", ["case", "folder"], A("work dir", "client.json  holdings.json  market.json  events.json\ntools/portfolio.py")],
          ["Build the agent's instructions.", "The playbook is turned into a system prompt plus one file per skill.", ["pb", "sys"], A("harness files", "prompt.md\nskills/case-review/SKILL.md\nskills/recommendation-format/SKILL.md")],
          ["Run the agent.", "The harness starts Muse inside the sandbox. The agent reads the files, runs the calculator, writes a draft, checks it, and saves recommendation.json. We stop it after 20 turns or 3 minutes. Every step it takes is recorded.", ["agent", "rec"], A("real run r-6ac32ca8", "turn 0  read  skills/case-review/SKILL.md\nturn 1  bash  python tools/portfolio.py allocation holdings.json\n...\n9 turns, 35.2k tokens, 83.5 s")],
          ["Grade it.", "The checker runs the 10 rules and produces a score and violations, e.g. emergency_fund: cash 2.7 months, needs 6 after layoff.", ["check"], A("checker output", "score 0.833  passed false\nemergency_fund (hard): cash 2.7 months, needs 6 after layoff")],
          ["Backtest it.", "The trades are applied and the portfolio is marked to market over the next 12 real months. If the client is unemployed, living costs come out of cash; if cash runs out, investments are sold (a forced sale).", ["bt"], A("real backtest j-001/t04", "start $320,897  end $229,949\nreturn -28.3%  max drawdown -35.4%\nmin cash 2.89 months  emergency_fund_breached true\nforced sale $0")],
          ["Save everything.", "The run, the trace, the score, the violations and the backtest go into the database. The live view shows it within seconds.", ["db", "live"], A("runs document", "{ run_id, playbook_version, case_id, set, model,\n  score, passed, violations, results, steps, backtest }")],
        ] },
      { id: "b", tab: "5b Getting better", title: "Getting better (the training loop)",
        nodes: [["prac", 0, 0, "practice", "20 clients"], ["fail", 1, 0, "failures", "up to 8"], ["mentor", 2, 0, "mentor", "Muse Wonder"], ["valid", 3, 0, "validate", "format, ≤3 changes"],
          ["gem", 4, 0, "compliance", "Gemini"], ["test", 4, 1, "unseen test", "20 × 3"], ["reg", 3, 1, "regression", "10 clients"], ["gate", 5, 1, "gate", "+0.02, no flips"], ["ship", 5, 0, "ship / reject", "logged"]],
        edges: [["prac", "fail"], ["fail", "mentor"], ["mentor", "valid"], ["valid", "gem"], ["gem", "test"], ["gem", "reg"], ["test", "gate"], ["reg", "gate"], ["gate", "ship"]],
        steps: [
          ["", "Run the current playbook on 20 practice clients.", ["prac"], A("real v0 practice", v0 ? `${v0.practice.passed}/${v0.practice.n} passed, mean ${f3(v0.practice.mean)}` : "waiting for the first generation")],
          ["", "Hand up to 8 failures to the mentor. For each, it sees the client's events, the trades the agent made, and the exact violation.", ["fail", "mentor"], A("one failure, as the mentor sees it", "events: layoff\ntrades: sell US_EQ 12,000 -> buy BOND 12,000\nviolation: emergency_fund: cash 2.9 months, needs 3")],
          ["", "The mentor diagnoses the root cause, maps it to the triggering event, and writes a new playbook: at most 3 changes, with a new lesson. It may not mention specific clients or invent thresholds.", ["mentor"], A("new lesson", jl ? `"${jl.lesson}"\nroot cause: ${jl.root_cause}\nrule: ${jl.rule}  skill: ${jl.skill}` : "\"After a layoff, I build six months of cash before rebalancing anything else.\"")],
          ["Validate", "the new playbook (format, change count, no client names, lessons kept).", ["valid"], A("validation", "parses: yes\nchanges: 2 of 3 allowed\nclient ids: none\nlessons kept: all")],
          ["Compliance review:", "Gemini compares old and new and blocks anything that loosens client protection.", ["gem"], A("verdict (real example)", "BLOCK: the Muse change hard-coded \"$600 monthly contribution\",\ncopied from one client's violation (overfitting to a single case)")],
          ["", "Run the candidate on 20 unseen test clients (3 times each, to separate real gains from luck) and on the 10 regression clients.", ["test", "reg"], A("real v1 candidate", v1 ? `test ${v1.test.passed}/${v1.test.n}, mean ${f3(v1.test.mean)}\nregression ${v1.regression ? `${v1.regression.passed}/${v1.regression.n}, mean ${f3(v1.regression.mean)}` : "-"}` : "waiting for a candidate")],
          ["Gate:", "ship only if the test score rises by at least 0.02 with confidence, no client that passed now fails, the backtest shows no more cash breaches or forced sales, and the reviewer approved. Otherwise reject, and log why.", ["gate", "ship"], A("real gate decision", v1 && v0 ? `v1 ${v1.decision.toUpperCase()}\ntest ${f3(v0.test.mean)} -> ${f3(v1.test.mean)} (${v1.test.mean - v0.test.mean >= 0 ? "+" : "-"}${Math.abs(v1.test.mean - v0.test.mean).toFixed(3)})\nreason: ${v1.reason || "-"}` : "pending")],
          ["Repeat.", "", ["prac"], A("next generation", "the shipped playbook becomes the parent")],
        ] },
      { id: "c", tab: "5c Each client's own agent", title: "Each client's own agent (the journey loop)",
        nodes: [["gen", 0, 1, "generic playbook", "start"], ["train", 1, 0, "t01–t05", "train checkpoints"], ["run", 2, 0, "run, grade", "+ backtest"], ["fix", 3, 0, "mentor fix", "for this client"],
          ["verify", 4, 0, "keep if", "passes earlier too"], ["hold", 1, 2, "t06–t10", "holdout future"], ["both", 3, 2, "generic vs own", "same checkpoints"], ["proof", 5, 2, "proof", "difference"]],
        edges: [["gen", "train"], ["train", "run"], ["run", "fix"], ["fix", "verify"], ["gen", "hold"], ["verify", "hold"], ["hold", "both"], ["both", "proof"]],
        steps: [
          ["", "Start the client with the generic playbook.", ["gen"], A("client", j ? `${j.persona.name}, ${j.persona.age ?? ""}, ${j.persona.occupation}, risk ${j.persona.risk_score}\n${j.regime_text || ""}` : "-")],
          ["", "Walk through their first 5 quarterly checkpoints in order. At each, run the agent, grade and backtest it.", ["train", "run"], A("checkpoint", jcp ? `${j.journey_id}/${jcp.id}  as of ${jcp.date}\n${jcp.baseline?.violation || "clean"}\nbacktest: min cash ${jcp.baseline?.backtest?.min_cash_coverage_months ?? "-"} months` : "-")],
          ["", "When it fails, the mentor writes a fix for this client, with a lesson. The fix is kept only if it passes this checkpoint and still passes every earlier one.", ["fix", "verify"], A("lesson learned", jl ? `at ${jl.at}: "${jl.lesson}"` : "no lesson yet")],
          ["", "On the last 5 checkpoints (the client's future, never shown to the mentor), run both the generic agent and the client's own agent. The difference is the proof that this client's agent is better aligned.", ["hold", "both", "proof"], A("real holdout result", sm ? `generic   ${sm.holdout_pass_start}  mean ${f3(sm.holdout_mean_start)}\nown agent ${sm.holdout_pass_final}  mean ${f3(sm.holdout_mean_final)}` : "holdout not reached yet")],
        ] },
      { id: "d", tab: "5d Catching drift", title: "Catching drift (the safety loop)",
        nodes: [["ev", 0, 0, "life event", "life_events"], ["cs", 1, 0, "change stream", "MongoDB"], ["snap", 2, 0, "Snap gate", "SubQ Snap"], ["rerun", 3, 0, "re-run", "client's agent"],
          ["light", 4, 0, "drift light", "red"], ["roll", 5, 0, "rollback", "last good"], ["ana", 5, 1, "analyst", "SubQ Preview"], ["mfix", 4, 1, "mentor fix", "from diagnosis"], ["gate", 3, 1, "gate", "drifted + regression"], ["human", 2, 1, "escalate", "after 3 tries"]],
        edges: [["ev", "cs"], ["cs", "snap"], ["snap", "rerun"], ["rerun", "light"], ["light", "roll"], ["roll", "ana"], ["ana", "mfix"], ["mfix", "gate"], ["gate", "human"]],
        steps: [
          ["", "A new life event lands in the database (e.g. \"I got laid off\").", ["ev"], A("life_events insert", "{ client_id: \"c-021\", type: \"layoff\", date: \"2026-11-07\" }")],
          ["", "The database fires a change stream event instantly.", ["cs"], A("change stream", "operationType: insert  ns: ballast.life_events")],
          ["", "The Snap gate asks, in under a second: which rules does this put at risk, and does the current playbook cover it?", ["snap"], A("Snap output (real calibration)", "emergency_fund risk 0.999\nplaybook covers it 0.017\nrerun_now true  urgency 3  0.78 s  1.4K tokens\ngate F1 0.94 (precision 0.98, recall 0.90) over 39 events")],
          ["", "If a rule is at risk and the playbook doesn't cover it, the client's agent is re-run immediately.", ["rerun"], A("re-run", "c-021 re-run on the live playbook before any recommendation goes out")],
          ["", "If a rule the agent used to always pass now fails, the drift light goes red, and the system rolls back to the last good version.", ["light", "roll"], A("drift event", "level red  rolling 0.580 vs baseline 0.890\naction rollback  v4 -> v3")],
          ["", "A long-context analyst reads every run, every client timeline and every playbook version in one pass, and names the pattern (e.g. \"layoff plus a concentrated stock fails the cash rule 70% of the time\").", ["ana"], A("pattern", "emergency_fund 0.70  layoff + single-stock, after a market drop\nrisk_band 0.62  inheritance over 25% of portfolio")],
          ["", "The mentor writes a fix from that diagnosis. It ships only if it passes the drifted cases and the regression set. After 3 failed attempts, it escalates to a human.", ["mfix", "gate", "human"], A("fix", "attempt 1 of 3\nmust pass 10/10 drifted cases and hold regression")],
        ] },
    ];
  }
  const L = { i: 0, step: 0, defs: [] };
  function renderLoopTabs() {
    $("#loop-tabs").innerHTML = L.defs.map((d, k) => `<button role="tab" id="lt-${d.id}" aria-selected="${k === L.i}" aria-controls="loopbox" tabindex="${k === L.i ? 0 : -1}">${esc(d.tab)}</button>`).join("");
    $("#loopbox").setAttribute("aria-labelledby", `lt-${L.defs[L.i].id}`);
  }
  function renderLoop() {
    const d = L.defs[L.i], svg = $("#lmap");
    svg.innerHTML = "";
    const W = 124, H = 92, bw = 106, bh = 50, ox = 14, oy = 18;
    const pos = Object.fromEntries(d.nodes.map(([id, c, r]) => [id, [ox + c * W, oy + r * H]]));
    const rows = Math.max(...d.nodes.map((n) => n[2])) + 1;
    svg.setAttribute("viewBox", `0 0 760 ${oy * 2 + rows * H - (H - bh)}`);
    // coordinate ticks along the top
    for (let c = 0; c < 6; c++) el("text", { x: ox + c * W, y: 10, class: "coord" }, svg).textContent = String.fromCharCode(65 + c);
    const lit = new Set(d.steps[L.step][2]);
    const done = new Set(d.steps.slice(0, L.step).flatMap((s) => s[2]));
    d.edges.forEach(([a, b]) => {
      const [x1, y1] = pos[a], [x2, y2] = pos[b];
      const ax = x1 + bw, ay = y1 + bh / 2, bx = x2, by = y2 + bh / 2;
      let dpath;
      if (y1 === y2) dpath = x2 > x1 ? `M${ax},${ay}H${bx}` : `M${x1},${ay}H${x2 + bw}`;
      else if (x1 === x2) dpath = y2 > y1 ? `M${x1 + bw / 2},${y1 + bh}V${y2}` : `M${x1 + bw / 2},${y1}V${y2 + bh}`;
      else { const mx = (x1 + bw / 2 + x2 + bw / 2) / 2; dpath = `M${x1 + bw / 2},${y2 > y1 ? y1 + bh : y1}V${(y1 + y2 + bh) / 2}H${x2 + bw / 2}V${y2 > y1 ? y2 : y2 + bh}`; void mx; }
      const on = (lit.has(a) || done.has(a)) && (lit.has(b) || done.has(b));
      el("path", { d: dpath, fill: "none", stroke: tok(on ? "mint" : "rim"), "stroke-width": on ? 2 : 1, "stroke-dasharray": on ? "" : "4 3" }, svg);
    });
    d.nodes.forEach(([id, , , label, sub]) => {
      const [x, y] = pos[id], isLit = lit.has(id), isDone = done.has(id);
      const g = el("g", {}, svg);
      el("rect", { x, y, width: bw, height: bh, fill: tok(isLit ? "mint" : isDone ? "panel-2" : "deep"), stroke: tok(isLit ? "mint" : isDone ? "text-3" : "rim"), "stroke-width": isLit ? 2 : 1 }, g);
      el("rect", { x: x - 3, y: y - 3, width: 6, height: 6, fill: tok(isLit ? "gold" : "rim") }, g);
      const t = el("text", { x: x + 9, y: y + 21, class: "nl", fill: tok(isLit ? "on-accent" : "text") }, g); t.textContent = label;
      const s2 = el("text", { x: x + 9, y: y + 38, class: "ns", fill: tok(isLit ? "on-accent" : "text-3") }, g); s2.textContent = sub;
    });
    $("#lsteps").innerHTML = d.steps.map(([b, t], k) => `<li class="${k === L.step ? "cur" : k < L.step ? "done" : ""}" data-k="${k}"><span class="sn mono">${String(k + 1).padStart(2, "0")}</span><p>${b ? `<b>${esc(b)}</b> ` : ""}${esc(t)}</p></li>`).join("");
    const a = d.steps[L.step][3];
    $("#artifact").innerHTML = `<p class="art-k mono">Produces: ${esc(a.k)}</p><pre class="art-v">${esc(a.v)}</pre>`;
    $("#l-prev").disabled = L.step === 0;
    $("#l-next").textContent = L.step === d.steps.length - 1 ? "Start over" : "Next step";
  }
  function bindLoops() {
    $("#loop-tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; L.i = [...$("#loop-tabs").children].indexOf(b); L.step = 0; renderLoopTabs(); renderLoop(); });
    $("#loop-tabs").addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      L.i = (L.i + (e.key === "ArrowRight" ? 1 : -1) + L.defs.length) % L.defs.length; L.step = 0; renderLoopTabs(); renderLoop(); $("#loop-tabs").children[L.i].focus();
    });
    $("#l-next").addEventListener("click", () => { const n = L.defs[L.i].steps.length; L.step = (L.step + 1) % n; renderLoop(); });
    $("#l-prev").addEventListener("click", () => { L.step = Math.max(0, L.step - 1); renderLoop(); });
    $("#lsteps").addEventListener("click", (e) => { const li = e.target.closest("li[data-k]"); if (li) { L.step = +li.dataset.k; renderLoop(); } });
  }

  // ---------- 6. handlers + system map ----------
  const H = [
    [1, "Case runner", "agent/run_case.py", "Runs one client case through Pi in a sandbox; enforces turn and time limits; records every step", "Pi (Node 22.19+), a model key, Linux user agent", ["spark"], ["runs"]],
    [2, "Portfolio calculator", "agent/tools/portfolio.py", "The agent's tool: current weights, cash in months, what trades would do. The checker uses the same math", "Python only", [], []],
    [3, "Checker", "checker/check.py, rules.py", "Grades a recommendation: 10 rules, score, pass, violations", "Python only", [], ["runs"]],
    [4, "Drift indicator", "checker/drift.py", "Green / yellow / red from a window of graded runs", "Python only", [], ["drift_events"]],
    [5, "Backtest", "scenarios/backtest.py", "Replays the 12 held-out months: return, drawdown, cash coverage, forced sales", "Held-out market files", [], ["runs"]],
    [6, "Mentor", "runtime/mentor.py (mentor_propose, validate_playbook)", "Diagnoses failures and writes the next playbook with lessons; validates it", "Muse (or SubQ) key", ["wonder"], ["playbooks", "journey_playbooks"]],
    [7, "Compliance reviewer", "runtime/mentor.py (compliance_review)", "Blocks changes that weaken client protection", "Gemini key", ["gemini"], ["generations"]],
    [8, "Drift analyst", "runtime/mentor.py (analyze_drift)", "Reads all runs at once and names patterns", "SubQ Preview (or Muse) key", ["preview"], ["drift_analysis"]],
    [9, "Snap gates", "runtime/snap.py", "Per-event rule-risk check; second opinion on rollback", "SubQ key", ["snap"], ["drift_events"]],
    [10, "Training and drift loop", "runtime/loop.py (train, drift, bench)", "Orchestrates generations, gates, rollback, model comparisons", "All of the above, MongoDB", [], ["playbooks", "generations", "runs", "drift_events", "benchmarks", "loop_log", "clients"]],
    [11, "Journey loop", "runtime/journey.py", "Per-client learning over quarterly checkpoints, proven on the client's future", "All of the above", [], ["journeys", "journey_playbooks", "journey_steps", "journey_summaries", "runs"]],
    [12, "Live watcher", "runtime/watch.py (+ inject_event.py)", "Listens to MongoDB for new life events; runs the Snap gate, re-runs, triggers drift mode", "MongoDB change streams", ["snap"], ["life_events", "drift_events"]],
    ["—", "Store", "runtime/store.py", "Writes and reads everything; falls back to local files if the database is down", "MongoDB URI", [], ["*"]],
    ["—", "Model client", "runtime/llm.py", "One way to call Muse, Gemini or SubQ", "Keys", ["spark", "wonder", "gemini", "snap", "preview"], []],
    ["—", "Web app", "web/main.py", "The website and live view; read-only over the database", "MongoDB URI", [], ["*"]],
  ];
  const COLLS = ["playbooks", "generations", "runs", "drift_events", "drift_analysis", "clients", "life_events", "benchmarks", "loop_log", "journeys", "journey_playbooks", "journey_steps", "journey_summaries"];
  const MODELS = [["spark", "Muse Spark 1.3", "agent", "muse"], ["wonder", "Muse Wonder 1.0", "mentor", "muse"], ["gemini", "Gemini", "compliance", "gold"], ["snap", "SubQ Snap", "decision gates", "subq"], ["preview", "SubQ Preview", "analyst", "subq"]];
  let sel = null;
  function renderHandlers() {
    $("#hgrid").innerHTML = H.map((h, k) => `<li><button class="hcard" data-k="${k}" aria-pressed="${sel === k}">
      <span class="h-n mono">${typeof h[0] === "number" ? String(h[0]).padStart(2, "0") : "—"}</span><span class="h-name">${esc(h[1])}</span>
      <span class="h-file mono">${esc(h[2])}</span><span class="h-job">${esc(h[3])}</span><span class="h-needs"><b class="mono">needs</b> ${esc(h[4])}</span></button></li>`).join("");
    $("#colls").innerHTML = COLLS.map((c) => `<li class="mono">${esc(c)}</li>`).join("");
  }
  function renderMap() {
    const svg = $("#smap");
    svg.innerHTML = "";
    const mx = 16, mw = 176, hx = 300, hw = 250, cx = 676, cw = 176, top = 46;
    const hRow = 36, cRow = 40, mRow = 98;
    const hy = (k) => top + k * hRow + (k >= 14 ? 26 : 0), cy = (k) => top + 6 + k * cRow, my = (k) => top + 30 + k * mRow;
    // frames: machines and database
    const frame = (x, y, w, h, label, color) => { el("rect", { x, y, width: w, height: h, fill: "none", stroke: tok(color), "stroke-dasharray": "6 4" }, svg); el("text", { x: x + 6, y: y - 6, class: "fl", fill: tok(color) }, svg).textContent = label; };
    frame(hx - 12, top - 14, hw + 24, hRow * 14 + 6, "Fly machine ballast-runner (iad, Virginia)", "text-3");
    frame(hx - 12, hy(14) - 8, hw + 24, hRow + 2, "Fly machine ballast-web", "text-3");
    frame(cx - 12, top - 8, cw + 24, cRow * COLLS.length + 8, "MongoDB Atlas", "jade");
    frame(mx - 8, top + 16, mw + 16, mRow * MODELS.length - 30, "Model APIs", "muse");
    const S = sel == null ? null : H[sel];
    const litColl = new Set(S ? (S[6].includes("*") ? COLLS : S[6]) : []);
    const litModel = new Set(S ? S[5] : []);
    // edges
    H.forEach((h, k) => {
      const y = hy(k) + hRow / 2 - 4, on = sel === k;
      h[5].forEach((m) => { const i = MODELS.findIndex((x) => x[0] === m); const y2 = my(i) + 22; const xm = (mx + mw + hx) / 2;
        el("path", { d: `M${mx + mw},${y2}H${xm}V${y}H${hx}`, fill: "none", stroke: tok(on ? MODELS[i][3] : "rim"), "stroke-width": on ? 2 : 0.75, "stroke-opacity": sel == null || on ? 1 : 0.35 }, svg); });
      (h[6].includes("*") ? [] : h[6]).forEach((c) => { const i = COLLS.indexOf(c); const y2 = cy(i) + 13; const xm = hx + hw + 30 + (k % 6) * 12;
        el("path", { d: `M${hx + hw},${y}H${xm}V${y2}H${cx}`, fill: "none", stroke: tok(on ? "mint" : "rim"), "stroke-width": on ? 2 : 0.75, "stroke-opacity": sel == null || on ? 1 : 0.35 }, svg); });
      if (h[6].includes("*") && on) el("path", { d: `M${hx + hw},${y}H${cx - 12}`, fill: "none", stroke: tok("mint"), "stroke-width": 2 }, svg);
    });
    // nodes
    MODELS.forEach(([id, name, role, col], i) => {
      const y = my(i), on = litModel.has(id);
      el("rect", { x: mx, y, width: mw, height: 44, fill: tok(on ? col : "deep"), stroke: tok(col), "stroke-width": on ? 2 : 1 }, svg);
      el("text", { x: mx + 10, y: y + 19, class: "nl", fill: tok(on ? "on-accent" : "text") }, svg).textContent = name;
      el("text", { x: mx + 10, y: y + 35, class: "ns", fill: tok(on ? "on-accent" : "text-3") }, svg).textContent = role;
    });
    H.forEach((h, k) => {
      const y = hy(k), on = sel === k;
      const g = el("g", { class: "hnode", "data-k": k, tabindex: -1 }, svg);
      el("rect", { x: hx, y, width: hw, height: hRow - 8, fill: tok(on ? "mint" : "deep"), stroke: tok(on ? "mint" : "rim") }, g);
      el("text", { x: hx + 8, y: y + 18, class: "nl", fill: tok(on ? "on-accent" : "text") }, g).textContent = `${typeof h[0] === "number" ? String(h[0]).padStart(2, "0") : "--"}  ${h[1]}`;
      g.addEventListener("click", () => select(k));
    });
    COLLS.forEach((c, i) => {
      const y = cy(i), on = litColl.has(c);
      el("rect", { x: cx, y, width: cw, height: cRow - 12, fill: tok(on ? "jade" : "deep"), stroke: tok(on ? "jade" : "rim") }, svg);
      el("text", { x: cx + 8, y: y + 18, class: "ns", fill: tok(on ? "on-accent" : "text-2") }, svg).textContent = c;
    });
    el("text", { x: hx, y: 632, class: "ns", fill: tok("text-3") }, svg).textContent = sel == null ? "Pick a handler card or a box to light its connections." : `${H[sel][1]}: ${H[sel][5].length} model ${H[sel][5].length === 1 ? "API" : "APIs"}, ${H[sel][6].includes("*") ? "all 13" : H[sel][6].length} ${H[sel][6].length === 1 ? "collection" : "collections"}`;
  }
  function select(k) {
    sel = sel === k ? null : k;
    document.querySelectorAll("#hgrid .hcard").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.k === sel)));
    renderMap();
  }

  async function init() {
    renderGloss();
    $("#gloss-q").addEventListener("input", renderGloss);
    renderHandlers();
    renderMap();
    $("#hgrid").addEventListener("click", (e) => { const b = e.target.closest(".hcard"); if (b) select(+b.dataset.k); });
    bindLoops();
    L.defs = loops(); renderLoopTabs(); renderLoop();
    try {
      const [b, j] = await Promise.all([fetch("/api/scoreboard").then((r) => r.json()).catch(() => null), fetch("/api/journeys").then((r) => r.json()).catch(() => [])]);
      R.board = b; R.journeys = (j || []).filter((x) => x.source === "live").length ? j.filter((x) => x.source === "live") : j || [];
    } catch (_) { /* numbers stay as the doc's */ }
    renderNums();
    L.defs = loops(); renderLoop();
    try { const r = await fetch("/api/live/status"); const s = await r.json(); document.querySelector(".live-link").classList.toggle("on", !!s.active); } catch (_) { /* optional */ }
  }
  init();
})();
