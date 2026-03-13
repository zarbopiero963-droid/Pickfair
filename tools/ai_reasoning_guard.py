import ast
import copy
import hashlib
import json
import os
import re
import sys
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
GUARDRAILS_DIR = ROOT / "guardrails"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}

DEFAULT_CONFIG = {
    "fail_on_deterministic_high": True,
    "fail_on_deterministic_critical": True,
    "fail_on_ai_high": False,
    "fail_on_ai_critical": True,
    "max_file_chars": 12000,
    "max_files_for_ai": 8,
    "hard_block_on_scope_violation": True,
    "hard_block_on_runtime_smoke_failure": True,
    "hard_block_on_semantic_failure": True,
    "trace_max_events_per_call": 500,
}

DEFAULT_PROMPT = """You are a repository safety reviewer.
Your role is NOT to rewrite code.
Your role is to assess whether a patch is risky.

You will receive:
- changed files
- deterministic guardrail findings
- semantic smoke results
- runtime smoke results
- mutation probe results
- runtime trace summaries
- source snippets

Return strict JSON only.

Rules:
- Be skeptical.
- Prefer false positives over false negatives when silent behavior changes are plausible.
- Focus on:
  - semantic drift
  - hidden new rules
  - fallback logic
  - silent exception swallowing
  - retry inflation
  - threshold changes
  - None-return shortcuts
  - event bus / callback hidden coupling
  - dynamic Python patterns
- If deterministic guardrails are already HIGH/CRITICAL, do not downgrade them.
- Suggest concrete extra tests when useful.
"""

AI_JSON_SCHEMA = {
    "name": "repo_patch_risk_review",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            },
            "summary": {"type": "string"},
            "semantic_drift_suspected": {"type": "boolean"},
            "silent_behavior_change_suspected": {"type": "boolean"},
            "new_rules_suspected": {"type": "boolean"},
            "requires_human_review": {"type": "boolean"},
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
            },
            "suggested_extra_tests": {
                "type": "array",
                "items": {"type": "string"},
            },
            "suspicious_files": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "risk_level",
            "summary",
            "semantic_drift_suspected",
            "silent_behavior_change_suspected",
            "new_rules_suspected",
            "requires_human_review",
            "reasons",
            "suggested_extra_tests",
            "suspicious_files",
        ],
        "additionalProperties": False,
    },
}


@dataclass
class Finding:
    severity: str
    category: str
    file: str
    symbol: str
    message: str


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_file(path: Path) -> Optional[ast.AST]:
    try:
        return ast.parse(read_text(path), filename=str(path))
    except Exception:
        return None


def iter_python_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def module_name_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def get_changed_files_from_env() -> List[str]:
    raw = os.environ.get("AI_CHANGED_FILES", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_changed_files_from_args(args: List[str]) -> List[str]:
    return [x.strip() for x in args if x.strip()]


def collect_imports(tree: ast.AST) -> List[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return sorted(set(imports))


def build_dependency_graph(root: Path) -> Dict[str, Any]:
    modules = {}
    for pyfile in iter_python_files(root):
        mod = module_name_from_path(pyfile, root)
        tree = parse_file(pyfile)
        imports = collect_imports(tree) if tree else []
        modules[mod] = {
            "path": str(pyfile.relative_to(root)),
            "imports": imports,
        }

    reverse = {m: [] for m in modules}
    for src, data in modules.items():
        for imported in data["imports"]:
            for target in modules:
                if imported == target or imported.startswith(target + "."):
                    reverse[target].append(src)

    reverse = {k: sorted(set(v)) for k, v in reverse.items()}
    return {"modules": modules, "reverse_dependencies": reverse}


def impact_analysis(root: Path, changed_files: List[str]) -> Dict[str, Any]:
    graph = build_dependency_graph(root)
    modules = graph["modules"]
    reverse = graph["reverse_dependencies"]

    changed_modules = []
    for rel in changed_files:
        path = root / rel
        if path.exists() and path.suffix == ".py":
            try:
                changed_modules.append(module_name_from_path(path, root))
            except Exception:
                pass

    impacted = set(changed_modules)
    queue = list(changed_modules)

    while queue:
        current = queue.pop(0)
        for dep in reverse.get(current, []):
            if dep not in impacted:
                impacted.add(dep)
                queue.append(dep)

    impacted_paths = []
    for mod in sorted(impacted):
        if mod in modules:
            impacted_paths.append(modules[mod]["path"])

    return {
        "changed_modules": sorted(changed_modules),
        "impacted_modules": sorted(impacted),
        "impacted_paths": impacted_paths,
    }


def analyze_dynamic_risks(path: Path, root: Path) -> List[Finding]:
    findings: List[Finding] = []
    tree = parse_file(path)
    if tree is None:
        findings.append(
            Finding(
                severity="HIGH",
                category="parse_failure",
                file=str(path.relative_to(root)),
                symbol="module",
                message="AST parse failed; static analysis incomplete.",
            )
        )
        return findings

    dynamic_names = {"getattr", "setattr", "hasattr", "__import__", "eval", "exec"}
    event_hints = {
        "emit",
        "publish",
        "post",
        "dispatch",
        "subscribe",
        "handler",
        "listener",
        "callback",
    }
    suspicious_tokens = {
        "fallback": "Possible fallback path added.",
        "retry": "Possible retry inflation.",
        "threshold": "Possible new threshold rule.",
        "timeout": "Possible runtime behavior change.",
        "except Exception": "Broad exception swallowing can hide regressions.",
        "pass": "Silent branch may hide failure.",
        "return None": "Potential silent short-circuit.",
    }

    src = read_text(path)

    for token, msg in suspicious_tokens.items():
        count = src.count(token)
        if count:
            findings.append(
                Finding(
                    severity="MEDIUM",
                    category="suspicious_token",
                    file=str(path.relative_to(root)),
                    symbol=token,
                    message=f"{msg} Token '{token}' found {count} time(s).",
                )
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in dynamic_names:
                findings.append(
                    Finding(
                        severity="HIGH",
                        category="dynamic_runtime",
                        file=str(path.relative_to(root)),
                        symbol=func_name,
                        message=f"Dynamic builtin '{func_name}' used; hidden runtime coupling possible.",
                    )
                )
            if func_name in event_hints:
                findings.append(
                    Finding(
                        severity="MEDIUM",
                        category="event_coupling",
                        file=str(path.relative_to(root)),
                        symbol=func_name,
                        message=f"Event-style call '{func_name}' suggests hidden runtime dependency.",
                    )
                )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "importlib":
                    findings.append(
                        Finding(
                            severity="HIGH",
                            category="dynamic_import",
                            file=str(path.relative_to(root)),
                            symbol=alias.name,
                            message="importlib imported; static dependency graph may be incomplete.",
                        )
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "importlib":
                findings.append(
                    Finding(
                        severity="HIGH",
                        category="dynamic_import",
                        file=str(path.relative_to(root)),
                        symbol=node.module,
                        message="Dynamic import support detected.",
                    )
                )

    dedup = {}
    for finding in findings:
        key = (
            finding.severity,
            finding.category,
            finding.file,
            finding.symbol,
            finding.message,
        )
        dedup[key] = finding
    return list(dedup.values())


def extract_public_api(tree: ast.AST) -> Dict[str, Any]:
    result: Dict[str, Any] = {"functions": {}, "classes": {}}

    def fn_sig(node: ast.FunctionDef) -> Dict[str, Any]:
        args = node.args

        def names(arg_list):
            return [a.arg for a in arg_list]

        positional = names(args.args)
        defaults_count = len(args.defaults)
        positional_defaults = positional[-defaults_count:] if defaults_count else []

        kwonly = []
        for idx, arg in enumerate(args.kwonlyargs):
            kwonly.append(
                {
                    "name": arg.arg,
                    "has_default": args.kw_defaults[idx] is not None,
                }
            )

        return {
            "positional": positional,
            "positional_with_defaults": positional_defaults,
            "vararg": args.vararg.arg if args.vararg else None,
            "kwonly": kwonly,
            "kwarg": args.kwarg.arg if args.kwarg else None,
        }

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            result["functions"][node.name] = fn_sig(node)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    methods[item.name] = fn_sig(item)
            result["classes"][node.name] = {"methods": methods}
    return result


def build_public_api_snapshot(root: Path) -> Dict[str, Any]:
    out = {}
    for pyfile in iter_python_files(root):
        mod = module_name_from_path(pyfile, root)
        tree = parse_file(pyfile)
        if tree is None:
            out[mod] = {"parse_error": True}
            continue
        out[mod] = extract_public_api(tree)
    return out


def compare_api_snapshot(current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    current_keys = set(current)
    baseline_keys = set(baseline)

    added_modules = sorted(current_keys - baseline_keys)
    removed_modules = sorted(baseline_keys - current_keys)
    changed_modules = []

    for mod in sorted(current_keys & baseline_keys):
        if current[mod] != baseline[mod]:
            changed_modules.append(mod)

    return {
        "added_modules": added_modules,
        "removed_modules": removed_modules,
        "changed_modules": changed_modules,
    }


def load_callable(dotted_path: str):
    module_name, attr = dotted_path.rsplit(".", 1)
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)


def resolve_path(obj: Any, path: Optional[str]) -> Any:
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, part)
    return current


def set_path_value(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    current = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, part)

    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    else:
        setattr(current, last, value)


def compare_expectation(actual: Any, spec: Dict[str, Any]) -> Tuple[bool, str]:
    mode = spec.get("mode", "equals")

    if mode == "equals":
        expected = spec.get("expected")
        return actual == expected, f"expected={expected!r}, actual={actual!r}"

    if mode == "contains_keys":
        expected = spec.get("expected", [])
        if not isinstance(actual, dict):
            return False, f"actual is not dict: {type(actual).__name__}"
        missing = [k for k in expected if k not in actual]
        return len(missing) == 0, f"missing_keys={missing}"

    if mode == "greater_than":
        expected = spec.get("expected")
        try:
            return actual > expected, f"actual={actual!r}, expected>{expected!r}"
        except Exception as exc:
            return False, f"comparison_error={exc}"

    if mode == "less_than":
        expected = spec.get("expected")
        try:
            return actual < expected, f"actual={actual!r}, expected<{expected!r}"
        except Exception as exc:
            return False, f"comparison_error={exc}"

    if mode == "between":
        low = spec.get("min")
        high = spec.get("max")
        try:
            return low <= actual <= high, f"actual={actual!r}, range=[{low!r}, {high!r}]"
        except Exception as exc:
            return False, f"comparison_error={exc}"

    if mode == "hash_equals":
        expected = spec.get("expected")
        actual_hash = stable_hash(actual)
        return actual_hash == expected, f"actual_hash={actual_hash}, expected_hash={expected}"

    return False, f"unknown mode: {mode}"


def _trace_call(fn, args, kwargs, max_events: int) -> Tuple[Any, Dict[str, Any]]:
    events: List[Dict[str, str]] = []

    def tracer(frame, event, arg):
        if event != "call":
            return tracer

        filename = frame.f_code.co_filename
        try:
            path = Path(filename).resolve()
        except Exception:
            return tracer

        if ROOT not in path.parents and path != ROOT:
            return tracer

        if len(events) >= max_events:
            return tracer

        try:
            rel = str(path.relative_to(ROOT))
        except Exception:
            rel = str(path)

        events.append(
            {
                "file": rel,
                "function": frame.f_code.co_name,
            }
        )
        return tracer

    old_profile = sys.getprofile()
    sys.setprofile(tracer)
    try:
        result = fn(*args, **kwargs)
    finally:
        sys.setprofile(old_profile)

    unique_pairs = []
    seen = set()
    for item in events:
        key = (item["file"], item["function"])
        if key not in seen:
            seen.add(key)
            unique_pairs.append(item)

    return result, {
        "event_count": len(events),
        "unique_calls": unique_pairs,
        "unique_files": sorted({x["file"] for x in unique_pairs}),
    }


def run_semantic_checks(specs_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    specs = read_json(specs_path, default={"checks": []})
    checks = specs.get("checks", [])
    results = []
    overall_ok = True

    for item in checks:
        record = {
            "callable": item.get("callable"),
            "ok": True,
            "assertions": [],
            "trace": {},
        }
        try:
            fn = load_callable(item["callable"])
            args = item.get("args", [])
            kwargs = item.get("kwargs", {})

            result, trace = _trace_call(
                fn,
                args,
                kwargs,
                max_events=config["trace_max_events_per_call"],
            )
            record["trace"] = trace

            for assertion in item.get("assertions", []):
                actual = resolve_path(result, assertion.get("path"))
                ok, msg = compare_expectation(actual, assertion)
                entry = {
                    "path": assertion.get("path"),
                    "mode": assertion.get("mode"),
                    "ok": ok,
                    "details": msg,
                }
                record["assertions"].append(entry)
                if not ok:
                    overall_ok = False
                    record["ok"] = False

        except Exception as exc:
            overall_ok = False
            record["ok"] = False
            record["error"] = f"{exc.__class__.__name__}: {exc}"
            record["traceback"] = traceback.format_exc()

        results.append(record)

    return {"ok": overall_ok, "checks": results}


def run_runtime_smokes(specs_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    specs = read_json(specs_path, default={"smokes": []})
    smokes = specs.get("smokes", [])
    results = []
    overall_ok = True

    for item in smokes:
        record = {
            "callable": item.get("callable"),
            "ok": True,
            "trace": {},
        }
        try:
            fn = load_callable(item["callable"])
            args = item.get("args", [])
            kwargs = item.get("kwargs", {})
            value, trace = _trace_call(
                fn,
                args,
                kwargs,
                max_events=config["trace_max_events_per_call"],
            )
            record["trace"] = trace
            record["result_preview"] = repr(value)[:300]
        except Exception as exc:
            overall_ok = False
            record["ok"] = False
            record["error"] = f"{exc.__class__.__name__}: {exc}"
            record["traceback"] = traceback.format_exc()

        results.append(record)

    return {"ok": overall_ok, "smokes": results}


def _mutated_value_for_assertion(assertion: Dict[str, Any], current: Any) -> Tuple[bool, Any]:
    mode = assertion.get("mode", "equals")

    if mode == "equals":
        expected = assertion.get("expected")
        if isinstance(expected, str):
            return True, expected + "_MUTATED"
        if isinstance(expected, bool):
            return True, not expected
        if isinstance(expected, (int, float)):
            return True, expected + 999
        return True, "__MUTATED__"

    if mode == "greater_than":
        expected = assertion.get("expected", 0)
        return True, expected - 1

    if mode == "less_than":
        expected = assertion.get("expected", 0)
        return True, expected + 1

    if mode == "between":
        high = assertion.get("max", 0)
        return True, high + 1

    if mode == "contains_keys":
        if isinstance(current, dict):
            bad = dict(current)
            expected = assertion.get("expected", [])
            if expected:
                bad.pop(expected[0], None)
            return True, bad
        return False, current

    if mode == "hash_equals":
        return True, {"__mutated__": True}

    return False, current


def run_mutation_probes(specs_path: Path) -> Dict[str, Any]:
    specs = read_json(specs_path, default={"checks": []})
    checks = specs.get("checks", [])
    results = []
    overall_ok = True

    for item in checks:
        entry = {
            "callable": item.get("callable"),
            "ok": True,
            "mutations": [],
        }

        try:
            fn = load_callable(item["callable"])
            args = item.get("args", [])
            kwargs = item.get("kwargs", {})
            baseline = fn(*args, **kwargs)

            for assertion in item.get("assertions", []):
                path = assertion.get("path")
                if not path:
                    continue

                mutated = copy.deepcopy(baseline)
                current_value = resolve_path(mutated, path)
                can_mutate, new_value = _mutated_value_for_assertion(assertion, current_value)

                if not can_mutate:
                    entry["mutations"].append(
                        {
                            "path": path,
                            "mode": assertion.get("mode"),
                            "mutation_caught": False,
                            "details": "Mutation generation skipped",
                        }
                    )
                    entry["ok"] = False
                    overall_ok = False
                    continue

                set_path_value(mutated, path, new_value)
                actual = resolve_path(mutated, path)
                ok_after_mutation, msg = compare_expectation(actual, assertion)

                mutation_caught = not ok_after_mutation
                entry["mutations"].append(
                    {
                        "path": path,
                        "mode": assertion.get("mode"),
                        "mutation_caught": mutation_caught,
                        "details": msg,
                    }
                )

                if not mutation_caught:
                    entry["ok"] = False
                    overall_ok = False

        except Exception as exc:
            entry["ok"] = False
            entry["error"] = f"{exc.__class__.__name__}: {exc}"
            entry["traceback"] = traceback.format_exc()
            overall_ok = False

        results.append(entry)

    return {"ok": overall_ok, "probes": results}


def inspect_guard_weaknesses(semantic_specs: Dict[str, Any]) -> List[Finding]:
    findings = []
    checks = semantic_specs.get("checks", [])

    if not checks:
        findings.append(
            Finding(
                severity="HIGH",
                category="weak_guardrails",
                file="guardrails/semantic_specs.json",
                symbol="checks",
                message="No semantic checks defined; semantic regressions may pass.",
            )
        )
        return findings

    for item in checks:
        assertions = item.get("assertions", [])
        callable_name = item.get("callable", "unknown")
        if not assertions:
            findings.append(
                Finding(
                    severity="HIGH",
                    category="weak_guardrails",
                    file="guardrails/semantic_specs.json",
                    symbol=callable_name,
                    message="Semantic check without assertions; only crash/no-crash is being tested.",
                )
            )
            continue

        shallow_only = all(a.get("mode") == "contains_keys" for a in assertions)
        if shallow_only:
            findings.append(
                Finding(
                    severity="MEDIUM",
                    category="shallow_semantics",
                    file="guardrails/semantic_specs.json",
                    symbol=callable_name,
                    message="Only key presence is checked; wrong calculations may still pass.",
                )
            )
    return findings


def inspect_mutation_weaknesses(mutation_result: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    for probe in mutation_result.get("probes", []):
        callable_name = probe.get("callable", "unknown")
        for mutation in probe.get("mutations", []):
            if not mutation.get("mutation_caught", False):
                findings.append(
                    Finding(
                        severity="HIGH",
                        category="mutation_escape",
                        file="guardrails/semantic_specs.json",
                        symbol=callable_name,
                        message=f"Mutation escaped detection for path '{mutation.get('path')}'.",
                    )
                )

    return findings


def inspect_trace_weaknesses(semantic_result: Dict[str, Any], runtime_result: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    def process_trace_block(items: List[Dict[str, Any]], category: str):
        for item in items:
            trace = item.get("trace", {})
            unique_files = trace.get("unique_files", [])
            if not unique_files:
                findings.append(
                    Finding(
                        severity="MEDIUM",
                        category=category,
                        file=item.get("callable", "unknown"),
                        symbol="trace",
                        message="Trace captured no repository files; probe may be too shallow.",
                    )
                )
            elif len(unique_files) == 1:
                findings.append(
                    Finding(
                        severity="LOW",
                        category=category,
                        file=item.get("callable", "unknown"),
                        symbol="trace",
                        message="Trace touched only one repository file; coupling coverage may be shallow.",
                    )
                )

    process_trace_block(semantic_result.get("checks", []), "semantic_trace_shallow")
    process_trace_block(runtime_result.get("smokes", []), "runtime_trace_shallow")
    return findings


def check_scope(allowed_files_path: Path, changed_files: List[str]) -> Dict[str, Any]:
    data = read_json(allowed_files_path, default={"allowed_files": []})
    allowed = set(data.get("allowed_files", []))
    violations = [f for f in changed_files if f not in allowed]
    return {
        "ok": len(violations) == 0,
        "allowed_files": sorted(allowed),
        "violations": violations,
    }


def collect_source_snippets(
    changed_files: List[str],
    max_file_chars: int,
    max_files: int,
) -> List[Dict[str, Any]]:
    snippets = []
    for rel in changed_files[:max_files]:
        path = ROOT / rel
        if not path.exists() or not path.is_file():
            continue
        try:
            text = read_text(path)
            snippets.append(
                {
                    "file": rel,
                    "content": text[:max_file_chars],
                    "truncated": len(text) > max_file_chars,
                }
            )
        except Exception as exc:
            snippets.append(
                {
                    "file": rel,
                    "content": f"<<read error: {exc}>>",
                    "truncated": False,
                }
            )
    return snippets


def severity_score(level: str) -> int:
    return {
        "LOW": 1,
        "MEDIUM": 3,
        "HIGH": 6,
        "CRITICAL": 10,
    }.get(level, 1)


def aggregate_deterministic_risk(
    scope_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    runtime_result: Dict[str, Any],
    mutation_result: Dict[str, Any],
    api_diff: Dict[str, Any],
    findings: List[Finding],
) -> str:
    score = 0

    if not scope_result["ok"]:
        score += 10
    if not semantic_result["ok"]:
        score += 10
    if not runtime_result["ok"]:
        score += 8
    if not mutation_result["ok"]:
        score += 9

    if api_diff["added_modules"] or api_diff["removed_modules"]:
        score += 6
    if api_diff["changed_modules"]:
        score += min(8, 2 + len(api_diff["changed_modules"]))

    for finding in findings:
        score += severity_score(finding.severity)

    if score >= 28:
        return "CRITICAL"
    if score >= 16:
        return "HIGH"
    if score >= 8:
        return "MEDIUM"
    return "LOW"


def build_ai_payload(
    changed_files: List[str],
    impact: Dict[str, Any],
    deterministic_risk: str,
    scope_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    runtime_result: Dict[str, Any],
    mutation_result: Dict[str, Any],
    api_diff: Dict[str, Any],
    findings: List[Finding],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    snippets = collect_source_snippets(
        changed_files,
        max_file_chars=config["max_file_chars"],
        max_files=config["max_files_for_ai"],
    )

    return {
        "changed_files": changed_files,
        "impact_analysis": impact,
        "deterministic_risk": deterministic_risk,
        "scope_check": scope_result,
        "semantic_check_summary": {
            "ok": semantic_result["ok"],
            "failed_checks": [
                c["callable"] for c in semantic_result["checks"] if not c["ok"]
            ],
            "trace_summary": [
                {
                    "callable": c["callable"],
                    "unique_files": c.get("trace", {}).get("unique_files", []),
                }
                for c in semantic_result["checks"]
            ],
        },
        "runtime_smoke_summary": {
            "ok": runtime_result["ok"],
            "failed_smokes": [
                s["callable"] for s in runtime_result["smokes"] if not s["ok"]
            ],
            "trace_summary": [
                {
                    "callable": s["callable"],
                    "unique_files": s.get("trace", {}).get("unique_files", []),
                }
                for s in runtime_result["smokes"]
            ],
        },
        "mutation_probe_summary": mutation_result,
        "api_snapshot_diff": api_diff,
        "findings": [asdict(finding) for finding in findings],
        "source_snippets": snippets,
        "instructions": {
            "never_downgrade_deterministic_risk": True,
            "focus": [
                "semantic drift",
                "hidden new rules",
                "silent fallback logic",
                "broad exception swallowing",
                "retry inflation",
                "threshold changes",
                "return None shortcuts",
                "event bus hidden coupling",
                "dynamic Python patterns",
                "trace coverage gaps",
                "mutation escapes",
            ],
        },
    }


def parse_json_maybe(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()
    return json.loads(text)


def call_reasoning_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.environ.get("LLM_GUARD_API_KEY", "").strip()
    model = os.environ.get("LLM_GUARD_MODEL", "").strip()
    endpoint = os.environ.get(
        "LLM_GUARD_BASE_URL",
        "https://openrouter.ai/api/v1/chat/completions",
    ).strip()

    if not api_key or not model:
        return {
            "enabled": False,
            "ok": False,
            "error": "Missing LLM_GUARD_API_KEY or LLM_GUARD_MODEL",
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if "openrouter.ai" in endpoint:
        headers["HTTP-Referer"] = os.environ.get(
            "LLM_GUARD_SITE_URL",
            "https://local.guard",
        )
        headers["X-Title"] = os.environ.get(
            "LLM_GUARD_APP_NAME",
            "AI Reasoning Guard",
        )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": DEFAULT_PROMPT},
            {"role": "user", "content": stable_json(payload)},
        ],
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": AI_JSON_SCHEMA,
        },
    }

    response = requests.post(endpoint, headers=headers, json=body, timeout=120)
    response.raise_for_status()
    data = response.json()

    content = None
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        pass

    if content is None:
        return {
            "enabled": True,
            "ok": False,
            "raw_response": data,
            "error": "Unable to parse AI response content",
        }

    if isinstance(content, list):
        text_chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                text_chunks.append(item.get("text", ""))
        content = "\n".join(text_chunks).strip()

    parsed = parse_json_maybe(content)
    return {
        "enabled": True,
        "ok": True,
        "review": parsed,
        "raw_response_preview": str(data)[:1500],
    }


def final_decision(
    deterministic_risk: str,
    ai_result: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    ai_risk = None
    if ai_result.get("ok") and ai_result.get("review"):
        ai_risk = ai_result["review"].get("risk_level")

    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

    merged_risk = deterministic_risk
    if ai_risk and order.get(ai_risk, 0) > order.get(deterministic_risk, 0):
        merged_risk = ai_risk

    block = False
    reasons = []

    if deterministic_risk == "CRITICAL" and config["fail_on_deterministic_critical"]:
        block = True
        reasons.append("Deterministic risk is CRITICAL.")
    elif deterministic_risk == "HIGH" and config["fail_on_deterministic_high"]:
        block = True
        reasons.append("Deterministic risk is HIGH.")

    if ai_risk == "CRITICAL" and config["fail_on_ai_critical"]:
        block = True
        reasons.append("AI review marked patch as CRITICAL.")
    elif ai_risk == "HIGH" and config["fail_on_ai_high"]:
        block = True
        reasons.append("AI review marked patch as HIGH.")

    return {
        "deterministic_risk": deterministic_risk,
        "ai_risk": ai_risk,
        "final_risk": merged_risk,
        "block_merge": block,
        "block_reasons": reasons,
    }


def run_guard(changed_files: List[str]) -> Dict[str, Any]:
    config = {
        **DEFAULT_CONFIG,
        **read_json(GUARDRAILS_DIR / "guard_config.json", default={}),
    }

    scope_result = check_scope(GUARDRAILS_DIR / "allowed_files.json", changed_files)
    impact = impact_analysis(ROOT, changed_files)

    current_api = build_public_api_snapshot(ROOT)
    baseline_api = read_json(GUARDRAILS_DIR / "public_api_snapshot.json", default={})
    api_diff = (
        compare_api_snapshot(current_api, baseline_api)
        if baseline_api
        else {"added_modules": [], "removed_modules": [], "changed_modules": []}
    )

    semantic_result = run_semantic_checks(GUARDRAILS_DIR / "semantic_specs.json", config)
    runtime_result = run_runtime_smokes(GUARDRAILS_DIR / "runtime_smoke_specs.json", config)
    mutation_result = run_mutation_probes(GUARDRAILS_DIR / "semantic_specs.json")

    findings: List[Finding] = []
    semantic_specs = read_json(
        GUARDRAILS_DIR / "semantic_specs.json",
        default={"checks": []},
    )
    findings.extend(inspect_guard_weaknesses(semantic_specs))
    findings.extend(inspect_mutation_weaknesses(mutation_result))
    findings.extend(inspect_trace_weaknesses(semantic_result, runtime_result))

    for rel in changed_files:
        path = ROOT / rel
        if path.exists() and path.suffix == ".py":
            findings.extend(analyze_dynamic_risks(path, ROOT))

    if not scope_result["ok"]:
        for item in scope_result["violations"]:
            findings.append(
                Finding(
                    severity="CRITICAL",
                    category="scope_violation",
                    file=item,
                    symbol="file",
                    message="Changed file is outside allowed scope.",
                )
            )

    deterministic_risk = aggregate_deterministic_risk(
        scope_result=scope_result,
        semantic_result=semantic_result,
        runtime_result=runtime_result,
        mutation_result=mutation_result,
        api_diff=api_diff,
        findings=findings,
    )

    ai_payload = build_ai_payload(
        changed_files=changed_files,
        impact=impact,
        deterministic_risk=deterministic_risk,
        scope_result=scope_result,
        semantic_result=semantic_result,
        runtime_result=runtime_result,
        mutation_result=mutation_result,
        api_diff=api_diff,
        findings=findings,
        config=config,
    )

    ai_result = call_reasoning_api(ai_payload)
    decision = final_decision(deterministic_risk, ai_result, config)

    report = {
        "changed_files": changed_files,
        "scope_check": scope_result,
        "impact_analysis": impact,
        "api_snapshot_diff": api_diff,
        "semantic_checks": semantic_result,
        "runtime_smokes": runtime_result,
        "mutation_probes": mutation_result,
        "findings": [asdict(finding) for finding in findings],
        "ai_review": ai_result,
        "decision": decision,
    }

    return report


def cmd_snapshot_api() -> int:
    snapshot = build_public_api_snapshot(ROOT)
    write_json(GUARDRAILS_DIR / "public_api_snapshot.json", snapshot)
    print("Saved guardrails/public_api_snapshot.json")
    return 0


def cmd_run(changed_files: List[str]) -> int:
    report = run_guard(changed_files)
    out = GUARDRAILS_DIR / "ai_reasoning_guard_report.json"
    write_json(out, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["decision"]["block_merge"] else 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tools/ai_reasoning_guard.py snapshot-api")
        print("  python tools/ai_reasoning_guard.py run [file1.py file2.py ...]")
        return 1

    cmd = sys.argv[1]

    if cmd == "snapshot-api":
        return cmd_snapshot_api()

    if cmd == "run":
        changed_files = get_changed_files_from_args(sys.argv[2:])
        if not changed_files:
            changed_files = get_changed_files_from_env()
        return cmd_run(changed_files)

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())