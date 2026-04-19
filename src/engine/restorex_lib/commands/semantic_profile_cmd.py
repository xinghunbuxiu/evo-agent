from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import collect_files, read_text, rel, write_json, write_text, find_matching_brace
from restorex_lib.run_context import ensure_baseline_exists, run_paths
from restorex_lib.config_rules import load_json_if_exists

DEFAULT_SEMANTIC_RULES: dict[str, Any] = {
    "class_rules": [
        {
            "tag": "logger_like",
            "required_methods": ["debug", "info", "warn", "error"],
            "candidate_name": "AppLogger",
        },
        {
            "tag": "lifecycle_like",
            "required_methods": ["constructor"],
            "any_methods": ["start", "stop", "init"],
            "candidate_name": "",
        },
    ],
    "object_rules": [
        {
            "tag": "registry_like",
            "required_key_patterns": ["api|service|client|store|manager|config|state"],
            "min_pattern_hits": 1,
            "min_keys": 3,
            "candidate_name": "ServiceRegistry",
        }
    ],
    "function_rules": [
        {
            "tag": "state_transition_flow",
            "required_calls_prefix": ["set", "update", "toggle", "enable", "disable", "start", "stop"],
            "candidate_name": "",
        },
        {
            "tag": "bridge_command_flow",
            "required_calls_prefix": ["invoke", "emit", "listen", "request", "send"],
            "candidate_name": "",
        },
        {
            "tag": "ui_action_flow",
            "literal_contains": ["open", "close", "click", "submit", "confirm", "cancel"],
            "candidate_name": "",
        },
        {
            "tag": "log_invocation",
            "required_calls_prefix": ["log"],
            "candidate_name": "",
        },
    ],
    "scan_limits": {
        "class_body_chars": 6000,
        "function_body_chars": 1800,
        "max_class_items": 40,
        "max_object_items": 60,
        "max_function_items": 120,
    },
}


def _load_semantic_rules(workspace: Path) -> dict[str, Any]:
    obj = load_json_if_exists(workspace / "cache" / "project" / "semantic_rules.json")
    if not obj:
        return dict(DEFAULT_SEMANTIC_RULES)
    out = dict(DEFAULT_SEMANTIC_RULES)
    out.update({k: v for k, v in obj.items() if k in {"class_rules", "object_rules", "function_rules", "scan_limits"}})
    return out


def _extract_class_profiles(text: str, rules: dict[str, Any], class_body_chars: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for m in re.finditer(r"\bclass\s+([A-Za-z_$][\w$]*)\s*\{", text):
        class_name = m.group(1)
        body_start = m.end()
        body = text[body_start : body_start + class_body_chars]
        methods = re.findall(r"\n\s*([A-Za-z_$][\w$]*)\s*\(", body)
        method_set = sorted({x for x in methods if x not in {"if", "for", "while", "switch", "catch"}})
        tags: list[str] = []
        candidates: list[str] = []
        method_key = set(method_set)
        for rule in rules.get("class_rules", []):
            if not isinstance(rule, dict):
                continue
            required = set(str(x) for x in rule.get("required_methods", []))
            optional_any = set(str(x) for x in rule.get("any_methods", []))
            if required and not required.issubset(method_key):
                continue
            if optional_any and method_key.isdisjoint(optional_any):
                continue
            tag = str(rule.get("tag", "")).strip()
            cand = str(rule.get("candidate_name", "")).strip()
            if tag:
                tags.append(tag)
            if cand:
                candidates.append(cand)
        items.append({"class_name": class_name, "methods": method_set, "tags": tags, "candidate_names": candidates})
    return items


def _extract_object_profiles(text: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # 只处理中小对象，避免把大型常量/字典误识别为“服务注册表”。
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*\{([^{}]{10,500})\}", text, re.S):
        obj_name = m.group(1)
        body = m.group(2)
        pairs = re.findall(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)", body)
        if not pairs:
            continue
        keys = [k for k, _ in pairs]
        tags: list[str] = []
        candidates: list[str] = []
        key_set = set(keys)
        for rule in rules.get("object_rules", []):
            if not isinstance(rule, dict):
                continue
            min_keys = int(rule.get("min_keys", 0) or 0)
            required = set(str(x) for x in rule.get("required_keys", []))
            required_key_patterns = [str(x) for x in rule.get("required_key_patterns", []) if str(x).strip()]
            min_pattern_hits = int(rule.get("min_pattern_hits", 0) or 0)
            if min_keys and len(keys) < min_keys:
                continue
            if required and not required.issubset(key_set):
                continue
            if required_key_patterns:
                pattern_hits = 0
                for pat in required_key_patterns:
                    if any(re.search(pat, k, flags=re.I) for k in keys):
                        pattern_hits += 1
                if pattern_hits < max(1, min_pattern_hits):
                    continue
            tag = str(rule.get("tag", "")).strip()
            cand = str(rule.get("candidate_name", "")).strip()
            if tag:
                tags.append(tag)
            if cand:
                candidates.append(cand)
        items.append({"object_name": obj_name, "keys": keys, "tags": tags, "candidate_names": candidates})
    return items


def _infer_function_semantics(text: str, rules: dict[str, Any], function_body_chars: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # 同时覆盖三类常见编译产物函数形态：
    # 1) function 声明
    # 2) const fn = (...) => {}
    # 3) const fn = function(...) {}
    header_matches: list[tuple[str, str, int, str]] = []
    patterns = [
        r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>\s*\{",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function(?:\s+[A-Za-z_$][\w$]*)?\s*\(([^)]*)\)\s*\{",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*([^;\n]{1,240});",
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?([A-Za-z_$][\w$]*)\s*=>\s*([^;\n]{1,240});",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            fn_name = m.group(1)
            raw_params = m.group(2)
            expr_body = m.group(3) if m.lastindex and m.lastindex >= 3 else ""
            if re.match(r"^[A-Za-z_$][\w$]*$", raw_params or ""):
                params = raw_params
            else:
                params = raw_params or ""
            header_matches.append((fn_name, params, m.end(), expr_body))

    seen: set[tuple[str, int]] = set()
    for fn_name, raw_params, body_start, expr_body in sorted(header_matches, key=lambda x: x[2]):
        if (fn_name, body_start) in seen:
            continue
        seen.add((fn_name, body_start))
        params = [p.strip() for p in str(raw_params).split(",") if p.strip()]
        # 优先用真实花括号边界截取函数体；否则回退到表达式体/固定窗口。
        brace_open = text.rfind("{", 0, body_start + 1)
        if brace_open >= 0:
            brace_end = find_matching_brace(text, brace_open)
        else:
            brace_end = -1
        if brace_open >= 0 and brace_end > brace_open:
            body = text[brace_open + 1 : min(brace_end, brace_open + 1 + function_body_chars)]
        elif expr_body:
            body = str(expr_body)[:function_body_chars]
        else:
            body = text[body_start : body_start + function_body_chars]
        literals = re.findall(r'"([^"]{2,40})"|\'([^\']{2,40})\'', body)
        text_literals = [a or b for a, b in literals]
        calls = re.findall(r"([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\(", body)
        tags: list[str] = []
        candidate_names: list[str] = []
        call_methods = [b for _, b in calls]
        call_methods_lower = [x.lower() for x in call_methods]
        for rule in rules.get("function_rules", []):
            if not isinstance(rule, dict):
                continue
            literals_required = [str(x) for x in rule.get("literal_contains", [])]
            required_calls = [str(x) for x in rule.get("required_calls", [])]
            required_prefix = [str(x).lower() for x in rule.get("required_calls_prefix", [])]
            min_literal_hits = int(rule.get("min_literal_hits", 1) or 1)
            min_prefix_hits = int(rule.get("min_prefix_hits", 1) or 1)
            deny_prefix = [str(x).lower() for x in rule.get("deny_calls_prefix", [])]
            if literals_required and not any(any(tok in s for tok in literals_required) for s in text_literals):
                continue
            if literals_required:
                literal_hits = sum(1 for tok in literals_required if any(tok in s for s in text_literals))
                if literal_hits < min_literal_hits:
                    continue
            if required_calls and not all(rc in call_methods for rc in required_calls):
                continue
            if required_prefix:
                prefix_hits = sum(1 for cm in call_methods_lower if any(cm.startswith(p) for p in required_prefix))
                if prefix_hits < min_prefix_hits:
                    continue
            if deny_prefix and any(any(cm.startswith(p) for p in deny_prefix) for cm in call_methods_lower):
                continue
            tag = str(rule.get("tag", "")).strip()
            cand = str(rule.get("candidate_name", "")).strip()
            if tag:
                tags.append(tag)
            if cand:
                candidate_names.append(cand)
        items.append(
            {
                "function_name": fn_name,
                "params": params,
                "calls": [{"receiver": a, "method": b} for a, b in calls[:30]],
                "text_literals": text_literals[:20],
                "tags": sorted(set(tags)),
                "candidate_names": candidate_names,
            }
        )
    return items


def cmd_build_js_semantic_profile(workspace: Path, run_id: str) -> None:
    """构建 JS 语义画像。

    输出目标：
    - 以文件为单位给出 class/object/function 语义标签。
    - 汇总成稳定指标，供 verify、script-plan、diagnose 使用。
    """
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    origin_path = paths.analysis / "build_origin_report.json"
    origin_obj = json.loads(read_text(origin_path)) if origin_path.is_file() else {"items": []}
    origin_by_file = {str(i.get("file", "")): str(i.get("origin_label", "unknown")) for i in origin_obj.get("items", [])}
    semantic_rules = _load_semantic_rules(workspace)
    limits = semantic_rules.get("scan_limits", {}) if isinstance(semantic_rules.get("scan_limits", {}), dict) else {}
    class_body_chars = int(limits.get("class_body_chars", 6000))
    function_body_chars = int(limits.get("function_body_chars", 1800))
    max_class_items = int(limits.get("max_class_items", 40))
    max_object_items = int(limits.get("max_object_items", 60))
    max_function_items = int(limits.get("max_function_items", 120))

    items: list[dict[str, Any]] = []
    for f in collect_files(source_root, {".js"}):
        rel_path = rel(f, source_root)
        origin = origin_by_file.get(rel_path, "unknown")
        text = read_text(f)
        class_profiles = _extract_class_profiles(text, semantic_rules, class_body_chars)
        object_profiles = _extract_object_profiles(text, semantic_rules)
        function_profiles = _infer_function_semantics(text, semantic_rules, function_body_chars)
        # 精度优先：仅业务层参与标签统计，显式隔离三方/框架噪声。
        if origin != "app_business":
            for c in class_profiles:
                c["tags"] = []
                c["candidate_names"] = []
            for o in object_profiles:
                o["tags"] = []
                o["candidate_names"] = []
            for fn in function_profiles:
                fn["tags"] = []
                fn["candidate_names"] = []
        items.append(
            {
                "file": rel_path,
                "origin_label": origin,
                "class_profiles": class_profiles[:max_class_items],
                "object_profiles": object_profiles[:max_object_items],
                "function_profiles": function_profiles[:max_function_items],
            }
        )

    # 汇总命中
    summary = {
        "files": len(items),
        "logger_like_classes": 0,
        "registry_like_objects": 0,
        "tagged_functions_total": 0,
        "bridge_command_flows": 0,
        "state_transition_flows": 0,
        "ui_action_flows": 0,
    }
    for it in items:
        for c in it.get("class_profiles", []):
            if "logger_like" in c.get("tags", []):
                summary["logger_like_classes"] += 1
        for o in it.get("object_profiles", []):
            if "registry_like" in o.get("tags", []):
                summary["registry_like_objects"] += 1
        for fn in it.get("function_profiles", []):
            tags = set(fn.get("tags", []))
            if tags:
                summary["tagged_functions_total"] += 1
            if "bridge_command_flow" in tags:
                summary["bridge_command_flows"] += 1
            if "state_transition_flow" in tags:
                summary["state_transition_flows"] += 1
            if "ui_action_flow" in tags:
                summary["ui_action_flows"] += 1

    write_json(
        paths.analysis / "js_semantic_profile.json",
        {
            "run_id": run_id,
            "rules_source": "spec/semantic_rules.json",
            "summary": summary,
            "count": len(items),
            "items": items,
        },
    )
    md = [
        "# JS Semantic Profile",
        "",
        f"- run_id: `{run_id}`",
        f"- files: `{summary['files']}`",
        f"- logger_like_classes: `{summary['logger_like_classes']}`",
        f"- registry_like_objects: `{summary['registry_like_objects']}`",
        f"- tagged_functions_total: `{summary['tagged_functions_total']}`",
        f"- bridge_command_flows: `{summary['bridge_command_flows']}`",
        f"- state_transition_flows: `{summary['state_transition_flows']}`",
        f"- ui_action_flows: `{summary['ui_action_flows']}`",
        "",
        "## Highlights",
    ]
    shown = 0
    for it in items:
        file_path = it["file"]
        for c in it.get("class_profiles", []):
            if "logger_like" in c.get("tags", []):
                md.append(f"- {file_path} class `{c['class_name']}` -> logger_like, methods={','.join(c.get('methods', []))}")
                shown += 1
        for o in it.get("object_profiles", []):
            if "registry_like" in o.get("tags", []):
                md.append(f"- {file_path} object `{o['object_name']}` -> registry_like, keys={','.join(o.get('keys', []))}")
                shown += 1
        for fn in it.get("function_profiles", []):
            tags = fn.get("tags", [])
            if tags:
                md.append(
                    f"- {file_path} function `{fn['function_name']}` -> tags={','.join(tags)} candidate={','.join(fn.get('candidate_names', [])) or 'none'}"
                )
                shown += 1
        if shown >= 40:
            break
    if shown == 0:
        md.append("- none")
    write_text(paths.analysis / "js_semantic_profile.md", "\n".join(md))
