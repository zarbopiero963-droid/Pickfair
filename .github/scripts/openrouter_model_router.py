#!/usr/bin/env python3

import os
from typing import Any

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_MAP = {
    "audit": "openai/gpt-5.4",
    "reasoning": "openai/gpt-5.4",
    "review": "openai/gpt-5.4",
    "patch": "openai/gpt-5.3-codex",
    "coding": "qwen/qwen3-coder-next",
    "batch": "qwen/qwen3-coder-next",
    "cheap": "qwen/qwen3-coder-next",
    "huge_context": "google/gemini-3.1-pro-preview",
    "tools": "google/gemini-3.1-pro-preview",
}

REASONING_MODELS = {
    "openai/gpt-5.4",
    "google/gemini-3.1-pro-preview",
}


def _env_model(task_type: str) -> str | None:
    task_to_env = {
        "audit": "OPENROUTER_MODEL_TRIAGE",
        "reasoning": "OPENROUTER_MODEL_REVIEW",
        "review": "OPENROUTER_MODEL_REVIEW",
        "patch": "OPENROUTER_MODEL_PATCH",
        "coding": "OPENROUTER_MODEL_CHEAP",
        "batch": "OPENROUTER_MODEL_CHEAP",
        "cheap": "OPENROUTER_MODEL_CHEAP",
        "huge_context": "OPENROUTER_MODEL_HUGE_CONTEXT",
        "tools": "OPENROUTER_MODEL_HUGE_CONTEXT",
    }

    env_name = task_to_env.get(task_type)
    if not env_name:
        return None

    value = os.getenv(env_name, "").strip()
    return value or None


def get_model(task_type: str) -> str:
    task_type = (task_type or "audit").strip()
    env_override = _env_model(task_type)
    if env_override:
        return env_override
    return MODEL_MAP.get(task_type, "openai/gpt-5.4")


def _build_payload(task_type: str, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "provider": {
            "allow_fallbacks": False,
        },
    }

    if model in REASONING_MODELS and task_type in {"audit", "reasoning", "review", "huge_context"}:
        payload["reasoning"] = {
            "enabled": True
        }

    return payload


def call_openrouter(task_type: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY mancante")

    model = get_model(task_type)
    payload = _build_payload(task_type, model, messages)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/zarbopiero963-droid/Pickfair",
        "X-Title": "Pickfair AI Router",
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Risposta OpenRouter non valida: {exc}") from exc

    model_used = data.get("model", model)

    return {
        "model_used": model_used,
        "content": content,
        "raw": data,
    }


if __name__ == "__main__":
    demo_messages = [
        {"role": "user", "content": "Test router OpenRouter."}
    ]
    try:
        resp = call_openrouter("audit", demo_messages)
        print(f"Model used: {resp['model_used']}")
        print(resp["content"])
    except Exception as exc:
        print(f"Errore: {exc}")
        raise