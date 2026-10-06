"""Tiny LLM client. Default is a local Ollama model; no API keys, nothing leaves the machine.

QA_LLM=ollama (default)  real model via http://localhost:11434
QA_LLM=stub              canned answers for offline pipeline tests only; NEVER use for demo results
Environment: QA_MODEL (default llama3.1:8b), OLLAMA_URL (default http://localhost:11434)
"""
import json
import os

import requests

PROVIDER = os.environ.get("QA_LLM", "ollama").lower()
MODEL = os.environ.get("QA_MODEL", "llama3.1:8b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class LLMError(RuntimeError):
    pass


def describe() -> dict:
    return {"provider": PROVIDER, "model": "stub" if PROVIDER == "stub" else MODEL}


def chat_json(task: str, system: str, user: str, timeout: int = 300) -> dict:
    """Ask for a JSON object. `task` is "generate" or "triage" (only the stub uses it)."""
    if PROVIDER == "stub":
        from qa import stubs
        return stubs.respond(task, user)
    if PROVIDER != "ollama":
        raise LLMError(f"unknown QA_LLM provider {PROVIDER!r}")
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
    except requests.ConnectionError as e:
        raise LLMError(
            f"Cannot reach Ollama at {OLLAMA_URL}. Start it with `ollama serve` "
            f"and make sure `ollama pull {MODEL}` has been run."
        ) from e
    except requests.RequestException as e:
        raise LLMError(f"Ollama request failed: {e}") from e
    content = r.json().get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(f"model returned invalid JSON: {content[:200]!r}") from e
    if not isinstance(parsed, dict):
        raise LLMError("model returned JSON that is not an object")
    return parsed
