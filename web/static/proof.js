/* ballast. hero proof: the latest shipped playbook vs its parent on unseen clients, the paired gain with its CI, and the control arm. Real data from /api/proof. */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const f3 = (v) => (v == null ? "—" : Number(v).toFixed(3));
  const sg = (v) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`);
  const CHECK = { "gain>=0.02": "Paired gain ≥ +0.02", "ci_low>0": "90% CI above zero", no_lost_test_cases: "No unseen client got worse", no_confirmed_regressions: "No confirmed regression", backtest_not_worse: "Backtest not worse", gemini_approves: "Gemini compliance approves" };

  // forest plot: each arm's paired gain with its 90% CI against zero
  function forest(rows) {
    const W = 560, L = 150, R = 20, rowH = 40, H = rows.length * rowH + 34;
    const lo = Math.min(-0.05, ...rows.flatMap((r) => r.ci || [r.gain])), hi = Math.max(0.2, ...rows.flatMap((r) => r.ci || [r.gain]));
    const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
    const ticks = [-0.05, 0, 0.05, 0.1, 0.15, 0.2].filter((t) => t >= lo - 1e-9 && t <= hi + 1e-9);
    return `<svg class="pf-forest" viewBox="0 0 ${W} ${H}" role="img" aria-label="Paired gain with 90% confidence interval, candidate vs control">
      ${ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="6" y2="${H - 22}" class="${t === 0 ? "pf-zero" : "pf-grid"}"/><text x="${x(t)}" y="${H - 6}" class="pf-tick" text-anchor="middle">${t === 0 ? "0" : sg(t).replace(/0+$/, "").replace(/\.$/, "")}</text>`).join("")}
      ${rows.map((r, i) => { const y = 24 + i * rowH, c = r.ci || [r.gain, r.gain];
        return `<text x="0" y="${y + 4}" class="pf-lab ${r.cls}">${esc(r.label)}</text>
          <line x1="${x(c[0])}" x2="${x(c[1])}" y1="${y}" y2="${y}" class="pf-ci ${r.cls}"/><line x1="${x(c[0])}" x2="${x(c[0])}" y1="${y - 6}" y2="${y + 6}" class="pf-ci ${r.cls}"/><line x1="${x(c[1])}" x2="${x(c[1])}" y1="${y - 6}" y2="${y + 6}" class="pf-ci ${r.cls}"/>
          <rect x="${x(r.gain) - 5}" y="${y - 5}" width="10" height="10" class="pf-pt ${r.cls}"/>
          <text x="${x(c[1]) + 8}" y="${y + 4}" class="pf-v ${r.cls}">${sg(r.gain)}</text>`; }).join("")}
    </svg>`;
  }

  function render(p) {
    const el = document.getElementById("proof");
    if (!el) return;
    if (!p || !p.base || !p.cand) { el.hidden = true; return; }
    const b = p.base, c = p.cand, ctl = p.control;
    const tile = (k, v0, v1, fmt, better) => { const good = better(v0, v1);
      return `<div class="pf-tile"><p class="pf-k">${k}</p><p class="pf-n"><span class="pf-old">${fmt(v0)}</span><span class="pf-arr" aria-hidden="true">→</span><span class="${good ? "pos" : "neg"}">${fmt(v1)}</span></p></div>`; };
    const checks = Object.entries(p.checks || {});
    const rules = Object.keys({ ...b.rule_fail_rate, ...c.rule_fail_rate }).map((r) => [r, b.rule_fail_rate[r] || 0, c.rule_fail_rate[r] || 0]).filter(([, x, y]) => Math.abs(x - y) >= 0.05).sort((a, z) => (a[2] - a[1]) - (z[2] - z[1]));
    const runs = c.n_cases && c.n_runs ? Math.round(c.n_runs / c.n_cases) : null;
    el.hidden = false;
    el.innerHTML = `
      <div class="pf-head">
        <p class="pf-tag mono"><span class="pos">■ v${esc(p.version)} ${esc(p.decision)}</span> · ${checks.filter(([, v]) => v).length}/${checks.length} gate checks · ${esc(p.db)}</p>
        <h2 class="pf-h">Muse rewrote its own playbook. On ${esc(c.n_cases)} clients it had never seen${runs ? `, ${runs} runs each` : ""}, it got better.</h2>
      </div>
      <div class="pf-tiles">
        ${tile("Pass rate, unseen test", b.pass_rate, c.pass_rate, pct, (x, y) => y >= x)}
        ${tile("Mean policy score", b.mean_score, c.mean_score, f3, (x, y) => y >= x)}
        ${tile("Clients breaching cash in backtest", b.case_breaches, c.case_breaches, (v) => (v == null ? "—" : String(v)), (x, y) => y <= x)}
        ${tile("Clients forced to sell", b.case_forced_sales, c.case_forced_sales, (v) => (v == null ? "—" : String(v)), (x, y) => y <= x)}
      </div>
      <div class="pf-body">
        <div class="pf-eff">
          <p class="pf-k">Paired gain per client, 90% CI <span class="muted">(same clients, v${esc(p.parent)} vs new)</span></p>
          ${forest([{ label: `v${p.version}, trained on failures`, gain: p.gain, ci: p.ci, cls: "cand" }, ...(ctl ? [{ label: `v${ctl.version}, control arm`, gain: ctl.gain, ci: ctl.ci, cls: "ctl" }] : [])])}
          <p class="muted csm">${ctl ? `The control arm gets the same mentor with shuffled failures. It moved ${sg(ctl.gain)} and was not shipped: the gain comes from learning from the real failures, not from rerolling the prompt.` : ""}</p>
        </div>
        <div class="pf-side">
          <ul class="pf-checks">${checks.map(([k, v]) => `<li class="${v ? "pos" : "neg"}"><span class="mono">${v ? "✓" : "✕"}</span>${esc(CHECK[k] || k)}</li>`).join("")}</ul>
          ${p.reg_flips.length ? `<p class="csm pf-note"><b class="mono">${p.reg_flips.map(esc).join(", ")}</b> flipped on the regression set; re-run twice, ${p.reg_confirmed.length ? `confirmed: ${p.reg_confirmed.map(esc).join(", ")}` : "did not reproduce"}.</p>` : ""}
          ${p.compliance ? `<p class="csm pf-note"><b class="gold">Gemini: ${esc(p.compliance.verdict === "approve" ? "approved" : p.compliance.verdict)}</b>: ${esc(p.compliance.note || "")}</p>` : ""}
        </div>
      </div>
      ${rules.length ? `<div class="pf-rules"><p class="pf-k">Rule failure rate, unseen test, v${esc(p.parent)} → v${esc(p.version)}</p>
        <ul>${rules.map(([r, x, y]) => `<li><span class="mono">${esc(r)}</span><span class="pf-bar"><i class="old" style="width:${x * 100}%"></i><i class="${y <= x ? "pos" : "neg"}" style="width:${y * 100}%"></i></span><span class="mono ${y <= x ? "pos" : "neg"}">${pct(x)} → ${pct(y)}</span></li>`).join("")}</ul>
        <p class="muted csm">Not everything improved: rules where v${esc(p.version)} fails more often are shown in red. The gate still shipped it because the paired gain is positive with its whole CI above zero and no unseen client got worse.</p></div>` : ""}
      ${p.changelog ? `<p class="csm pf-chg"><span class="mono muted">What changed</span> ${esc(p.changelog)}</p>` : ""}`;
  }

  async function init() {
    try { const r = await fetch("/api/proof"); render(r.ok ? await r.json() : null); } catch { render(null); }
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
