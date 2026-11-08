"""ballast. on Fetch.ai: each client chats with their own portfolio agent from Agentverse / ASI:One.

Flow for each chat message:
  1. Ack. Work out who the client is (they say their name once; remembered per sender in MongoDB).
  2. Muse reads the message and classifies any life event (type + details) - or answers a question.
  3. A real job goes to the ballast. worker on Fly (MongoDB `jobs`): the client's own agent runs on
     Muse Spark in the Pi harness with their connected data, the message added to their feed.
  4. Reply with what the agent found, the trades and the reason for each, the flags for a human,
     and the policy score. The agent recommends only; an advisor approves.

Env: MONGODB_URI, MONGODB_DB (default ballast_muse), MUSE_API_KEY, MUSE_BASE_URL, AGENT_SEED_PHRASE,
     AGENTVERSE_API_KEY, PUBLIC_ENDPOINT (e.g. https://ballast-fetch.fly.dev/submit), PORT (8000).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone

from openai import OpenAI
from pymongo import MongoClient
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, EndSessionContent, TextContent, chat_protocol_spec,
)

DB = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "ballast_muse")]
MUSE = OpenAI(base_url=os.environ.get("MUSE_BASE_URL", "https://api.meta.ai/v1"), api_key=os.environ["MUSE_API_KEY"])
MODEL = "meta/muse-spark-1.3"
PORT = int(os.environ.get("PORT", "8000"))
ENDPOINT = os.environ.get("PUBLIC_ENDPOINT", "https://ballast-fetch.fly.dev/submit")

CLIENTS = {  # demo clients with connected data (scenarios/cases/connected)
    "cx-001": "Dana Reyes, 41, rates trader at Halvard Capital",
    "cx-002": "Miguel Santos, 36, ICU nurse",
    "cx-003": "Aisha Karim, 47, product manager",
    "cx-004": "Tom Becker, 58, engineer",
    "cx-005": "Priya Shah, 33, UX designer",
}
EVENT_TYPES = ["layoff", "job_change", "marriage", "child", "divorce", "inheritance", "market_drop",
               "parent_long_term_care", "tuition_due", "home_purchase", "medical_bill", "disability",
               "furlough", "desk_shutdown", "trading_blackout", "death_of_spouse", "tax_bill", "none"]

agent = Agent(name="ballast", seed=os.environ["AGENT_SEED_PHRASE"], port=PORT, endpoint=[ENDPOINT],
              publish_agent_details=True, readme_path=os.path.join(os.path.dirname(__file__), "README.md"))
chat = Protocol(spec=chat_protocol_spec)


def now():
    return datetime.now(timezone.utc)


def text_of(msg: ChatMessage) -> str:
    return " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()


def reply(text: str, end: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=now(), msg_id=uuid.uuid4(), content=content)


def who(sender: str, text: str) -> str | None:
    s = DB.fetch_sessions.find_one({"sender": sender})
    low = text.lower()
    for cid, desc in CLIENTS.items():
        first = desc.split(" ")[0].lower()
        if first in low or cid in low:
            DB.fetch_sessions.update_one({"sender": sender}, {"$set": {"client": cid, "updated_at": now().isoformat()}}, upsert=True)
            return cid
    return s["client"] if s else None


def classify(text: str) -> dict:
    prompt = (
        "A wealth-management client sent their advisor this message. Classify any life event that could "
        f"affect their portfolio. Types: {', '.join(EVENT_TYPES)}. Extract numbers when present "
        "(e.g. new_income, amount_due, due_date YYYY-MM-DD, monthly_cost_increase, severance, symbol). "
        'Answer JSON only: {"type": "...", "details": {...}, "summary": "<one sentence>"}\n\nMESSAGE: ' + text)
    try:
        r = MUSE.chat.completions.create(model="muse-spark-1.3", max_tokens=3000, temperature=0,
                                         messages=[{"role": "user", "content": prompt}])
        m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.S)
        return json.loads(m.group(0)) if m else {"type": "none", "details": {}, "summary": text}
    except Exception as e:
        return {"type": "none", "details": {}, "summary": f"(classifier unavailable: {e.__class__.__name__})"}


async def wait_job(job_id: str, timeout: int = 240) -> dict | None:
    for _ in range(timeout // 3):
        j = DB.jobs.find_one({"job_id": job_id}, {"_id": 0})
        if j and j.get("status") in ("done", "error"):
            return j
        await asyncio.sleep(3)
    return None


def summarize(cid: str, ev: dict, job: dict) -> str:
    if job.get("status") == "error":
        return f"Your agent hit an error and a human will follow up: {job.get('error', '')[:200]}"
    r = job.get("result") or {}
    rec, chk = r.get("recommendation") or {}, r.get("check") or {}
    lines = [f"Here's what your ballast. agent recommends ({CLIENTS[cid].split(',')[0]}):"]
    if ev.get("type") not in (None, "none"):
        lines.append(f"• I understood: {ev.get('summary') or ev['type']}")
    trades = rec.get("trades") or []
    if trades:
        lines.append("• Recommended trades (an advisor approves before anything happens):")
        for t in trades[:6]:
            lines.append(f"   - {t.get('action')} ${t.get('amount_usd', 0):,.0f} {t.get('symbol')}  (reason: {t.get('reason_ref')})")
    else:
        lines.append(f"• No trades: {rec.get('no_action_reason') or 'your portfolio already fits your plan'}")
    for x in (rec.get("rationale") or [])[:2]:
        lines.append(f"• Why: {x.get('text', '')[:220]}")
    pu = rec.get("profile_updates") or {}
    if pu.get("monthly_contribution") is not None:
        lines.append(f"• Suggested monthly contribution: ${pu['monthly_contribution']:,.0f}")
    for g in pu.get("goals_add") or []:
        lines.append(f"• New goal: {g.get('type')} by {g.get('target_year')}")
    for f in (rec.get("flags") or [])[:3]:
        lines.append(f"• For your advisor: {f[:200]}")
    score = chk.get("score")
    if score is not None:
        lines.append(f"• Policy check: {score:.2f} {'passed' if chk.get('passed') else 'needs review'}"
                     + ("" if chk.get("passed") else " — " + "; ".join(v["detail"] for v in chk.get("violations", [])[:2])))
    lines.append(f"(run {job['job_id']}, {r.get('turns')} steps, {r.get('seconds')} s on Muse · replay at ballast-web.fly.dev/live)")
    return "\n".join(lines)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=now(), acknowledged_msg_id=msg.msg_id))
    text = text_of(msg)
    DB.fetch_chats.insert_one({"sender": sender, "role": "client", "text": text, "created_at": now().isoformat()})
    cid = who(sender, text)
    if cid is None:
        menu = "\n".join(f"• {d}" for d in CLIENTS.values())
        out = ("Hi, I'm ballast., your personal portfolio agent. Which client are you? (demo profiles)\n" + menu +
               "\nJust tell me your first name, then what's changed in your life.")
        DB.fetch_chats.insert_one({"sender": sender, "role": "agent", "text": out, "created_at": now().isoformat()})
        await ctx.send(sender, reply(out))
        return
    ev = await asyncio.to_thread(classify, text)
    if ev.get("type") in (None, "none") and len(text.split()) <= 4:
        out = f"Hi {CLIENTS[cid].split(' ')[0]}! Tell me what's going on — a new job, a layoff, a baby, a bill coming up — and I'll review your portfolio."
        await ctx.send(sender, reply(out))
        return
    job_id = "job-fetch-" + uuid.uuid4().hex[:8]
    DB.jobs.insert_one({"job_id": job_id, "status": "queued", "case": f"connected/{cid}", "model": MODEL,
                        "playbook_version": 1, "journey": "connected", "created_at": now().isoformat(),
                        "tag": "fetch-chat", "sender": sender,
                        "chat": {"message": text, "event": None if ev.get("type") in (None, "none")
                                 else {"type": ev["type"], "details": ev.get("details") or {}}}})
    await ctx.send(sender, reply(f"Got it — {ev.get('summary') or 'thanks for the update'}. Your agent is reviewing your accounts now (about a minute)…"))
    job = await wait_job(job_id)
    out = summarize(cid, ev, job) if job else "Your agent is still working; check ballast-web.fly.dev/live for the result."
    DB.fetch_chats.insert_one({"sender": sender, "role": "agent", "text": out, "job_id": job_id, "created_at": now().isoformat()})
    await ctx.send(sender, reply(out, end=True))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"ack from {sender}")


agent.include(chat, publish_manifest=True)


@agent.on_event("startup")
async def register(ctx: Context):
    ctx.logger.info(f"ballast. agent address: {agent.address}  endpoint: {ENDPOINT}")
    try:
        from uagents_core.utils.registration import RegistrationRequestCredentials, register_chat_agent
        register_chat_agent("ballast.", ENDPOINT, active=True,
                            credentials=RegistrationRequestCredentials(
                                agentverse_api_key=os.environ["AGENTVERSE_API_KEY"],
                                agent_seed_phrase=os.environ["AGENT_SEED_PHRASE"]))
        ctx.logger.info("registered on Agentverse")
    except Exception as e:
        ctx.logger.error(f"Agentverse registration failed: {e}")
    DB.fetch_agent.update_one({"name": "ballast"}, {"$set": {"address": agent.address, "endpoint": ENDPOINT,
                                                             "started_at": now().isoformat()}}, upsert=True)


if __name__ == "__main__":
    agent.run()
