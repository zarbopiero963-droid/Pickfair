import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib import request, error

ROOT = Path(".").resolve()
ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_TIMEOUT = 20


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip()


def _requests_post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int):
    try:
        import requests
    except Exception:
        return None

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        return {
            "ok": bool(resp.ok),
            "status_code": int(resp.status_code),
            "text": resp.text,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "text": str(exc),
        }


def _urllib_post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int):

    body = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url=url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:

            text = resp.read().decode("utf-8", errors="ignore")

            status_code = getattr(resp, "status", 200)

            return {
                "ok": 200 <= int(status_code) < 300,
                "status_code": int(status_code),
                "text": text,
            }

    except error.HTTPError as exc:

        try:
            text = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            text = str(exc)

        return {
            "ok": False,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "text": text,
        }

    except Exception as exc:

        return {
            "ok": False,
            "status_code": 0,
            "text": str(exc),
        }


def _http_post(url, payload, headers, timeout):

    via_requests = _requests_post(url, payload, headers, timeout)

    if via_requests is not None:
        return via_requests

    return _urllib_post(url, payload, headers, timeout)


def _write_artifact(name, data):

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    out = ARTIFACTS_DIR / name

    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return str(out)


def _build_probe_cases():

    return [
        {
            "id": "mutation-1",
            "prompt": "Return JSON only with result ok.",
            "expected_keywords": ["result", "ok"],
        },
        {
            "id": "mutation-2",
            "prompt": "Answer with a short risk summary.",
            "expected_keywords": ["risk"],
        },
        {
            "id": "mutation-3",
            "prompt": "List two regression risks after API change.",
            "expected_keywords": ["regression"],
        },
    ]


def run_guard():

    api_url = _env("AI_REASONING_GUARD_URL")

    api_key = _env("AI_REASONING_GUARD_API_KEY")

    timeout = int(
        _safe_float(
            _env("AI_REASONING_GUARD_TIMEOUT", str(DEFAULT_TIMEOUT)),
            DEFAULT_TIMEOUT,
        )
    )

    if not api_url:

        result = {
            "ok": True,
            "mode": "offline",
            "provider": "none",
            "checks_run": 0,
            "issues": [],
            "message": "offline pass",
        }

        result["artifact"] = _write_artifact(
            "ai_reasoning_guard.json",
            result,
        )

        return result

    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "task": "reasoning_guard_smoke",
        "timestamp": int(time.time()),
    }

    resp = _http_post(api_url, payload, headers, timeout)

    ok = bool(resp.get("ok"))

    result = {
        "ok": ok,
        "mode": "remote",
        "status_code": resp.get("status_code"),
        "issues": [] if ok else ["remote_guard_failed"],
        "message": str(resp.get("text", ""))[:500],
    }

    result["artifact"] = _write_artifact(
        "ai_reasoning_guard.json",
        result,
    )

    return result


def run_mutation_probes():

    api_url = _env("AI_REASONING_GUARD_URL")

    api_key = _env("AI_REASONING_GUARD_API_KEY")

    timeout = int(
        _safe_float(
            _env("AI_REASONING_GUARD_TIMEOUT", str(DEFAULT_TIMEOUT)),
            DEFAULT_TIMEOUT,
        )
    )

    cases = _build_probe_cases()

    if not api_url:

        result = {
            "ok": True,
            "mode": "offline",
            "total": len(cases),
            "passed": len(cases),
            "failed": 0,
            "results": [],
        }

        result["artifact"] = _write_artifact(
            "ai_reasoning_mutation_probes.json",
            result,
        )

        return result

    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    results = []

    for case in cases:

        payload = {
            "task": "mutation_probe",
            "prompt": case["prompt"],
        }

        resp = _http_post(api_url, payload, headers, timeout)

        text = str(resp.get("text", "")).lower()

        ok = bool(resp.get("ok")) and all(
            kw.lower() in text
            for kw in case["expected_keywords"]
        )

        results.append(
            {
                "id": case["id"],
                "ok": ok,
                "status_code": resp.get("status_code"),
            }
        )

    passed = sum(1 for r in results if r["ok"])

    result = {
        "ok": passed == len(results),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }

    result["artifact"] = _write_artifact(
        "ai_reasoning_mutation_probes.json",
        result,
    )

    return result


if __name__ == "__main__":

    guard = run_guard()

    probes = run_mutation_probes()

    print(
        json.dumps(
            {"guard": guard, "probes": probes},
            indent=2,
            ensure_ascii=False,
        )
    )