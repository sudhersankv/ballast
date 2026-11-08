/* ballast. chat: the Fetch.ai agent's address + the latest real client conversations, as a phone. Renders into every [data-fetch-chat]. */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const short = (a) => (a && a.length > 20 ? `${a.slice(0, 12)}…${a.slice(-6)}` : a || "");
  const usd = (v) => `$${Math.round(Math.abs(Number(v) || 0)).toLocaleString("en-US")}`;
  const hhmm = (t) => { const d = new Date(t); return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
  const onLive = location.pathname.startsWith("/live");

  function jobChip(j) {
    if (!j) return "";
    const buys = j.trades.filter((t) => /buy/i.test(t.action || t.side || "")), sells = j.trades.filter((t) => /sell/i.test(t.action || t.side || ""));
    const tr = [...sells.map((t) => `<span class="neg">sell ${usd(t.amount_usd ?? t.usd ?? t.amount)} ${esc(t.symbol)}</span>`), ...buys.map((t) => `<span class="pos">buy ${usd(t.amount_usd ?? t.usd ?? t.amount)} ${esc(t.symbol)}</span>`)].join(" · ");
    const href = `/live#replay-job-${encodeURIComponent(j.job_id)}`;
    return `<div class="fc-job mono">
      ${tr ? `<p>${tr}</p>` : ""}
      <p><span class="${j.passed ? "pos" : "neg"}">policy ${j.score != null ? Number(j.score).toFixed(2) : "—"} ${j.passed ? "✓ passed" : "✕ failed"}</span>${j.seconds ? ` · ${Number(j.seconds).toFixed(1)} s` : ""}${j.event?.type ? ` · event ${esc(j.event.type)}` : ""}${j.playbook_version != null ? ` · ${esc(j.case)} v${esc(j.playbook_version)}` : ""}</p>
      <p><a class="fc-replay" href="${href}" data-job="${esc(j.job_id)}">Replay run ${esc(j.job_id)} →</a></p></div>`;
  }

  function phone(conv) {
    return `<div class="fc-phone" role="log" aria-label="Chat with the ballast. agent">
      <div class="fc-bar"><b>ballast.</b><span class="mono">Agent Chat Protocol 0.3.0</span></div>
      <div class="fc-msgs">${conv.messages.map((m) => `<div class="fc-m ${m.role === "agent" ? "agent" : "client"}">
        <div class="fc-b">${esc(m.text)}</div>${m.role === "agent" ? jobChip(m.job) : ""}
        <span class="fc-t mono">${m.role === "agent" ? "agent" : `client ${esc(short(conv.sender))}`} · ${hhmm(m.created_at)}</span></div>`).join("")}</div>
    </div>`;
  }

  function render(root, data) {
    const a = data.agent || {}, convs = data.conversations || [];
    root.innerHTML = `<div class="fc-grid">
      <div class="fc-side">
        <p class="fc-status mono"><span class="pos">● live</span> on Fly app ballast-fetch · registered on the Almanac · Agentverse listing pending</p>
        <p class="fc-k mono">Agent address</p>
        <div class="fc-addr"><code class="mono">${esc(a.address || "not registered")}</code>${a.address ? `<button class="btn small" type="button" data-copy="${esc(a.address)}">Copy</button>` : ""}</div>
        <ol class="fc-how">
          <li>Open <a href="https://asi1.ai" target="_blank" rel="noopener">ASI:One</a> or <a href="https://agentverse.ai" target="_blank" rel="noopener">Agentverse</a> chat.</li>
          <li>Start a chat with the address above.</li>
          <li>Say what changed, in plain words: "I got laid off", "we're expecting twins".</li>
        </ol>
        <p class="muted csm">Muse classifies the life event, a real job runs on the worker with the connected client's v1 playbook, and the agent replies with trades, reasons, advisor flags and its policy score. An advisor approves before anything trades.</p>
      </div>
      <div class="fc-convs">${convs.length ? convs.slice(0, 2).map(phone).join("") : `<p class="muted">No chats yet.</p>`}</div>
    </div>`;
    root.querySelector("[data-copy]")?.addEventListener("click", async (e) => {
      const b = e.currentTarget;
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; } catch { b.textContent = "Select and copy"; }
      setTimeout(() => { b.textContent = "Copy"; }, 1600);
    });
    if (onLive) root.querySelectorAll(".fc-replay").forEach((l) => l.addEventListener("click", (e) => {
      if (!window.ballastReplay) return; e.preventDefault(); window.ballastReplay("job", l.dataset.job);
    }));
  }

  async function init() {
    const roots = document.querySelectorAll("[data-fetch-chat]");
    if (!roots.length) return;
    let data;
    try { const r = await fetch("/api/fetch"); if (!r.ok) throw new Error(r.status); data = await r.json(); }
    catch (e) { roots.forEach((r) => { r.innerHTML = `<p class="muted">Chat data unavailable.</p>`; }); return; }
    roots.forEach((r) => render(r, data));
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
