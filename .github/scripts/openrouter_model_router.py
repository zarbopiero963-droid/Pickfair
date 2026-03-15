#!/usr/bin/env python3

import json
import os
from typing import Any

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variabile ambiente mancante: {name}")
    return value


def _read_optional_env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _model_for_task(task_type: str) -> str:
    task_type = (task_type or "").strip().lower()

    if task_type == "audit":
        return _read_optional_env("OPENROUTER_MODEL_TRIAGE", "openai/gpt-5.4")

    if task_type == "review":
        return _read_optional_env("OPENROUTER_MODEL_REVIEW", "openai/gpt-5.4")

    if task_type == "patch":
        return _read_optional_env("OPENROUTER_MODEL_PATCH", "openai/gpt-5.3-codex")

    if task_type == "cheap":
        return _read_optional_env("OPENROUTER_MODEL_CHEAP", "qwen/qwen3-coder-next")

    if task_type == "huge_context":
        return _read_optional_env(
            "OPENROUTER_MODEL_HUGE_CONTEXT",
            "google/gemini-3.1-pro-preview",
        )

    return _read_optional_env("OPENROUTER_MODEL_TRIAGE", "openai/gpt-5.4")


def _reasoning_enabled_for_model(model: str) -> bool:
    model = (model or "").lower()
    return model.startswith("openai/gpt-5.4") or model.startswith(
        "google/gemini-3.1-pro-preview"
    )


def _extract_content_from_message(message: Any) -> str:

    if isinstance(message, str):
        return message

    if isinstance(message, dict):

        content = message.get("content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):

            chunks = []

            for item in content:

                if isinstance(item, str):
                    chunks.append(item)
                    continue

                if not isinstance(item, dict):
                    continue

                item_type = str(item.get("type", "")).strip().lower()

                if item_type in {"text", "output_text"}:
                    text_value = item.get("text", "")
                    if isinstance(text_value, str):
                        chunks.append(text_value)

            return "\n".join(chunks)

    return ""


def _extract_content(resp_json: dict) -> str:

    choices = resp_json.get("choices")

    if not isinstance(choices, list) or not choices:

        if isinstance(resp_json.get("error"), dict):
            error_obj = resp_json["error"]
            message = error_obj.get("message") or error_obj.get("code") or str(error_obj)
            raise RuntimeError(f"OpenRouter error payload: {message}")

        raise RuntimeError("Risposta OpenRouter non valida: 'choices'")

    first_choice = choices[0]

    if not isinstance(first_choice, dict):
        raise RuntimeError("Risposta OpenRouter non valida: first choice non è un dict")

    message = first_choice.get("message")

    if message is None:
        text = first_choice.get("text")
        if isinstance(text, str) and text.strip():
            return text
        raise RuntimeError("Risposta OpenRouter non valida: manca 'message'")

    content = _extract_content_from_message(message)

    if content.strip():
        return content

    raise RuntimeError("Risposta OpenRouter non valida: contenuto vuoto")


def call_openrouter(task_type: str, messages: list[dict]) -> dict:

    api_key = _read_required_env("OPENROUTER_API_KEY")
    model = _model_for_task(task_type)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/zarbopiero963-droid/Pickfair",
        "X-Title": "Pickfair Repo Ultra Audit",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "provider": {
            "allow_fallbacks": False,
        },
    }

    if _reasoning_enabled_for_model(model):
        payload["reasoning"] = {"enabled": True}

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=180,
    )

    raw_text = response.text or ""

    try:
        resp_json = response.json()
    except Exception as exc:

        snippet = raw_text[:1000]

        raise RuntimeError(
            f"OpenRouter non ha restituito JSON valido ({type(exc).__name__}): {snippet}"
        ) from exc

    if response.status_code >= 400:

        if isinstance(resp_json.get("error"), dict):

            error_obj = resp_json["error"]
            message = error_obj.get("message") or error_obj.get("code") or str(error_obj)

            raise RuntimeError(
                f"OpenRouter HTTP {response.status_code}: {message}"
            )

        raise RuntimeError(
            f"OpenRouter HTTP {response.status_code}: {raw_text[:1000]}"
        )

    content = _extract_content(resp_json)

    model_used = str(resp_json.get("model") or model).strip() or model

    return {
        "content": content,
        "model_used": model_used,
        "raw": resp_json,
    }


if __name__ == "__main__":

    demo = {
        "status": "ok",
        "available_task_types": [
            "audit",
            "review",
            "patch",
            "cheap",
            "huge_context",
        ],
    }

    print(json.dumps(demo, indent=2, ensure_ascii=False))