#!/usr/bin/env python3

import os
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_MAP = {
    "audit": "openai/gpt-5.4",
    "reasoning": "openai/gpt-5.4",
    "patch": "openai/gpt-5.3-codex",
    "coding": "qwen/qwen3-coder-next",
    "batch": "qwen/qwen3-coder-next",
    "huge_context": "google/gemini-3.1-pro-preview",
}

def get_model(task_type: str) -> str:
    return MODEL_MAP.get(task_type, "openai/gpt-5.4")


def call_openrouter(task_type: str, messages: list):

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY mancante")

    model = get_model(task_type)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "provider": {
            "allow_fallbacks": False
        }
    }

    # reasoning mode per modelli che lo supportano
    if model in [
        "openai/gpt-5.4",
        "google/gemini-3.1-pro-preview"
    ]:
        payload["reasoning"] = {
            "enabled": True
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/zarbopiero963-droid/Pickfair",
        "X-Title": "Pickfair AI Router"
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    content = data["choices"][0]["message"]["content"]

    return {
        "model_used": model,
        "content": content,
        "raw": data
    }