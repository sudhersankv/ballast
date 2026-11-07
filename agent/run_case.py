"""Run one client case through the Pi harness with a given playbook.

run_case(playbook_path, case_dir) -> {"case_id", "recommendation", "turns", "tokens_in",
    "tokens_out", "seconds", "trace_path", "error"}

The playbook YAML is materialized into prompt.md + skills/<name>/SKILL.md, the case is
copied into a fresh working dir with tools/portfolio.py, and Pi runs once in JSON mode.
Max turns is enforced by counting `turn_end` events (Pi has no flag for it).

Model selection (env):
  BALLAST_MODEL     pi model id, e.g. "meta/<muse-id>" or "google/gemini-3.8-flash".
                    Defaults to the playbook's `model`, mapped through models.json.
  MUSE_API_KEY, MUSE_BASE_URL, MUSE_MODEL   used to register the `meta` provider.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "agent" / "tools" / "portfolio.py"
TRACES = ROOT / "runs" / "traces"
TIMEOUT_S = int(os.environ.get("BALLAST_CASE_TIMEOUT", "180"))
TASK = ("Review this client case and write recommendation.json. "
        "There are no hidden rules, tests or other files to find: decide using your own judgment "
        "and the case files in this directory. Read several files at once when you can, "
        "and write the file within a few steps.")


def materialize(playbook: dict, out_dir: Path) -> tuple[Path, list[Path]]:
    """Write prompt.md and one SKILL.md per skill; return (prompt_path, skill_dirs)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = out_dir / "prompt.md"
    prompt.write_text(playbook.get("prompt", "").strip() + "\n", encoding="utf-8")
    skill_dirs = []
    for s in playbook.get("skills", []) or []:
        d = out_dir / "skills" / s["name"]
        d.mkdir(parents=True, exist_ok=True)
        desc = str(s["description"]).replace("\n", " ").strip()
        (d / "SKILL.md").write_text(
            f"---\nname: {s['name']}\ndescription: {desc}\n---\n\n{s['body'].strip()}\n", encoding="utf-8")
        skill_dirs.append(d)
    return prompt, skill_dirs


def write_models_json(agent_dir: Path) -> None:
    """Register Muse (Meta Model API, OpenAI-compatible) as provider `meta`."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    providers = {}
    if os.environ.get("MUSE_BASE_URL"):
        providers["meta"] = {
            "baseUrl": os.environ["MUSE_BASE_URL"],
            "api": "openai-completions",
            "apiKey": "$MUSE_API_KEY",
            "models": [{"id": os.environ.get("MUSE_MODEL") or "muse"}],
        }
    if os.environ.get("SUBQ_API_KEY"):
        providers["subq"] = {
            "baseUrl": os.environ.get("SUBQ_BASE_URL") or "https://api.subq.ai/v1",
            "api": "openai-completions",
            "apiKey": "$SUBQ_API_KEY",
            "models": [{"id": os.environ.get("SUBQ_MODEL") or "subq-preview"}],
        }
    (agent_dir / "models.json").write_text(json.dumps({"providers": providers}, indent=2), encoding="utf-8")


def resolve_model(playbook: dict) -> str:
    if os.environ.get("BALLAST_MODEL"):
        return os.environ["BALLAST_MODEL"]
    m = playbook.get("model", "meta/muse")
    if m.startswith("meta/") and os.environ.get("MUSE_MODEL"):
        return f"meta/{os.environ['MUSE_MODEL']}"
    return m


def _usage(ev: dict) -> tuple[int, int]:
    """Pull token usage from a message_end event, tolerant of field naming."""
    msg = ev.get("message") or {}
    u = msg.get("usage") or ev.get("usage") or {}
    tin = u.get("input") or u.get("inputTokens") or u.get("prompt_tokens") or 0
    tout = u.get("output") or u.get("outputTokens") or u.get("completion_tokens") or 0
    return int(tin or 0), int(tout or 0)


def _sandbox_user() -> bool:
    if os.name != "posix" or os.geteuid() != 0 or os.environ.get("BALLAST_NO_SANDBOX"):
        return False
    return subprocess.run(["id", "agent"], capture_output=True).returncode == 0


def run_case(playbook_path: str, case_dir: str, keep_workdir: bool = False, on_step=None,
             model: str | None = None) -> dict:
    """on_step(step_dict) is called as each tool call / message lands (for live streaming).
    model overrides BALLAST_MODEL / the playbook's model for this run only (thread-safe)."""
    playbook = yaml.safe_load(Path(playbook_path).read_text(encoding="utf-8"))
    case_dir_p = Path(case_dir)
    case_id = case_dir_p.name
    max_turns = int(playbook.get("max_turns", 12))
    tools = ",".join(playbook.get("tools", ["read", "bash", "write"]))

    # Case workdir and harness/config live in separate temp roots so `ls ..` from the
    # case dir reveals nothing about the harness or credentials.
    tmp = Path(tempfile.mkdtemp(prefix="bh-"))
    harness, agent_dir = tmp / "harness", tmp / "agent"
    work = Path(tempfile.mkdtemp(prefix="case-")) / case_id
    shutil.copytree(case_dir_p, work)
    (work / "tools").mkdir(exist_ok=True)
    shutil.copy(TOOLS, work / "tools" / "portfolio.py")
    prompt_path, skill_dirs = materialize(playbook, harness)
    write_models_json(agent_dir)

    cmd = ["pi", "--mode", "json", "--no-session", "--no-extensions", "--no-context-files",
           "--no-mcp", "--no-approve", "--no-skills"]
    for d in skill_dirs:
        cmd += ["--skill", str(d)]
    # Replace Pi's default coding-assistant prompt: it pushes the model to explore the
    # filesystem instead of deciding. The playbook prompt is the whole system prompt.
    # --system-prompt takes literal text (only --append-system-prompt reads files).
    cmd += ["--system-prompt", prompt_path.read_text(encoding="utf-8"), "--tools", tools,
            "--model", (model or resolve_model(playbook)), TASK]

    TRACES.mkdir(parents=True, exist_ok=True)
    trace_path = TRACES / f"{case_id}-v{playbook.get('version', 'x')}-{int(time.time())}.jsonl"
    # Minimal env: the agent never sees Mongo/Fly/other secrets.
    keep = ("PATH", "LANG", "MUSE_API_KEY", "GEMINI_API_KEY", "SUBQ_API_KEY")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    if _sandbox_user():
        # Linux runner: drop to the unprivileged `agent` user, which cannot read /app.
        for p in (tmp, work.parent):
            subprocess.run(["chown", "-R", "agent:agent", str(p)], check=True)
        env["HOME"] = "/home/agent"
        cmd = ["runuser", "-u", "agent", "--"] + cmd
    else:
        env["HOME"] = os.environ.get("HOME", os.environ.get("USERPROFILE", ""))

    turns = tin = tout = 0
    error = None
    steps: list[dict] = []  # compact per-step trace for the live UI

    def clip(x, n=400):
        s = x if isinstance(x, str) else json.dumps(x, default=str)
        return s if len(s) <= n else s[:n] + "…"
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    timer = threading.Timer(TIMEOUT_S, proc.kill)
    timer.start()
    try:
        with open(trace_path, "w", encoding="utf-8") as trace:
            for line in proc.stdout:
                trace.write(line)
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "tool_execution_start":
                    steps.append({"turn": turns, "kind": "tool", "tool": ev.get("toolName"),
                                  "args": clip(ev.get("args"), 300)})
                elif kind == "tool_execution_end" and steps:
                    content = (ev.get("result") or {}).get("content") or []
                    text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    steps[-1]["result"] = clip(text)
                    steps[-1]["error"] = bool(ev.get("isError"))
                    if on_step:
                        on_step(steps[-1])
                if kind == "message_end" and (ev.get("message") or {}).get("role") == "assistant":
                    a, b = _usage(ev)
                    tin, tout = tin + a, tout + b
                    said = " ".join(c.get("text", "") for c in ev["message"].get("content", [])
                                    if isinstance(c, dict) and c.get("type") == "text").strip()
                    if said:
                        steps.append({"turn": turns, "kind": "say", "text": clip(said, 600)})
                        if on_step:
                            on_step(steps[-1])
                elif kind == "turn_end":
                    turns += 1
                    if turns >= max_turns:
                        error = f"max_turns ({max_turns}) reached"
                        proc.kill()
                        break
        proc.wait(timeout=10)
    finally:
        timer.cancel()
    seconds = round(time.time() - t0, 1)
    if error is None and seconds >= TIMEOUT_S:
        error = f"timeout after {TIMEOUT_S}s"
    if error is None and proc.returncode not in (0, None):
        err = (proc.stderr.read() if proc.stderr else "")[-500:]
        error = f"pi exited {proc.returncode}: {err.strip()}"

    rec_path = work / "recommendation.json"
    recommendation = None
    if rec_path.exists():
        try:
            recommendation = json.loads(rec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            error = error or f"recommendation.json is not valid JSON: {e}"
    elif error is None:
        error = "agent did not write recommendation.json"

    shutil.rmtree(tmp, ignore_errors=True)
    if not keep_workdir:
        shutil.rmtree(work.parent, ignore_errors=True)
    return {"case_id": case_id, "model": (model or resolve_model(playbook)),
            "recommendation": recommendation, "turns": turns,
            "tokens_in": tin, "tokens_out": tout, "seconds": seconds,
            "trace_path": str(trace_path), "error": error, "steps": steps[:60]}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python agent/run_case.py <playbook.yaml> <case_dir>")
        sys.exit(2)
    print(json.dumps(run_case(sys.argv[1], sys.argv[2]), indent=2))
