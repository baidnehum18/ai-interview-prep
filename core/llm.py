"""Optional LLM through any OpenAI-compatible API (OpenAI, Claude, Groq, local Ollama).

Every call returns None when the LLM is off or fails, so the app falls back to NLP scoring.
"""
import json
import re
from functools import lru_cache

from core import config


def enabled() -> bool:
    return bool(config.LLM_MODEL and (config.LLM_API_KEY or config.LLM_BASE_URL))


@lru_cache
def _client():
    from openai import OpenAI
    return OpenAI(api_key=config.LLM_API_KEY or "not-needed", base_url=config.LLM_BASE_URL, timeout=120)


def ask(system: str, prompt: str, max_tokens: int = 800) -> str | None:
    if not enabled():
        return None
    try:
        reply = _client().chat.completions.create(
            model=config.LLM_MODEL, max_tokens=max_tokens, temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return reply.choices[0].message.content
    except Exception as error:
        print("LLM call failed:", error)
        return None


def ask_json(system: str, prompt: str) -> dict | None:
    """Ask for a JSON object and parse it out of the reply."""
    match = re.search(r"\{.*\}", ask(system, prompt) or "", re.S)
    try:
        return json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None
