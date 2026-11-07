"""One OpenAI-compatible client for every model ballast. talks to outside Pi.

Providers (all OpenAI chat-completions compatible):
  muse    Meta Model API      MUSE_BASE_URL, MUSE_API_KEY, MUSE_MODEL
  gemini  Google Gemini       GEMINI_API_KEY, GEMINI_MODEL (OpenAI-compat endpoint)
  subq    Subquadratic SubQ   SUBQ_BASE_URL, SUBQ_API_KEY, SUBQ_MODEL

Role -> provider is configurable so benchmarks can swap models:
  MENTOR_PROVIDER (default muse), REVIEWER_PROVIDER (default gemini),
  ANALYST_PROVIDER (default subq, falls back to gemini if SubQ fails).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PROVIDERS = {
    "muse": ("MUSE_BASE_URL", "MUSE_API_KEY", "MUSE_MODEL", None, None),
    "gemini": (None, "GEMINI_API_KEY", "GEMINI_MODEL",
               "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.8-flash"),
    "subq": ("SUBQ_BASE_URL", "SUBQ_API_KEY", "SUBQ_MODEL", "https://api.subq.ai/v1", "subq-preview"),
}


@dataclass
class Reply:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    seconds: float


def config(provider: str) -> tuple[str, str, str]:
    url_env, key_env, model_env, url_default, model_default = PROVIDERS[provider]
    base = (os.environ.get(url_env) if url_env else None) or url_default
    key = os.environ.get(key_env, "")
    model = os.environ.get(model_env) or model_default
    if not (base and key and model):
        raise RuntimeError(f"{provider}: missing base URL, key or model in env")
    return base, key, model


def chat(provider: str, system: str, user: str, max_tokens: int = 8000,
         temperature: float = 0.2, model: str | None = None, response_format: dict | None = None) -> Reply:
    base, key, default_model = config(provider)
    model = model or default_model
    client = OpenAI(base_url=base, api_key=key, timeout=300)
    t0 = time.time()
    extra = {"response_format": response_format} if response_format else {}
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
    u = r.usage
    return Reply(text=r.choices[0].message.content or "", provider=provider, model=model,
                 tokens_in=getattr(u, "prompt_tokens", 0) or 0,
                 tokens_out=getattr(u, "completion_tokens", 0) or 0,
                 seconds=round(time.time() - t0, 1))


def role(name: str, default: str) -> str:
    return os.environ.get(f"{name.upper()}_PROVIDER", default)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "gemini"
    r = chat(p, "You are terse.", "Reply with OK", max_tokens=20)
    print(r)
