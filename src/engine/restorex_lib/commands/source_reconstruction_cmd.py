from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from restorex_lib.config_rules import load_json_if_exists
from restorex_lib.fs_utils import find_matching_brace, line_of_offset, read_text, write_json, write_text
from restorex_lib.run_context import run_paths
from restorex_lib.source_reconstruction import (
    analyze_component_structure,
    build_component_model_from_rules,
    render_component_from_rules,
    render_store_from_rules,
    render_composable_from_rules,
)


def _source_root(workspace: Path, run_id: str) -> tuple[Any, Path]:
    paths = run_paths(workspace, run_id)
    root = paths.analysis / "source_reconstruction"
    root.mkdir(parents=True, exist_ok=True)
    return paths, root


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(read_text(path))
    except Exception:
        return default


def _generated_source_rules_path(workspace: Path, run_id: str) -> Path:
    _, root = _source_root(workspace, run_id)
    return root / "source_reconstruction_rules.generated.json"


def _load_source_reconstruction_rules(workspace: Path, run_id: str = "") -> dict[str, Any]:
    manual = load_json_if_exists(workspace / "cache" / "project" / "source_reconstruction_rules.json")
    if manual:
        return manual
    if run_id:
        generated = load_json_if_exists(_generated_source_rules_path(workspace, run_id))
        if generated:
            return generated
    return {}


def _analysis_rules(rules: dict[str, Any]) -> dict[str, Any]:
    return dict(rules.get("analysis_rules", {}))


def _read_project_template(workspace: Path, rel_path: str) -> str:
    path = workspace / rel_path
    if not path.is_file():
        return ""
    try:
        return read_text(path)
    except Exception:
        return ""


def _fill_template(template: str, replacements: dict[str, str]) -> str:
    text = template
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def _safe_lower_file_stem(name: str, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", str(name or "").strip())
    if not token:
        token = fallback
    return token[:1].lower() + token[1:]


def _safe_name(name: str, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "", str(name or "").strip())
    if not s:
        s = fallback
    if not re.match(r"[A-Za-z_]", s):
        s = f"{fallback}{s}"
    return s


def _normalize_param_name(raw: str, idx: int) -> str:
    token = str(raw or "").strip()
    token = token.split("=", 1)[0].strip()
    token = token.strip("{}[]")
    token = re.sub(r"[^A-Za-z0-9_]", "", token)
    return token or f"arg{idx}"


def _component_display_title(name: str, rules: dict[str, Any] | None = None) -> str:
    mapping = dict((rules or {}).get("component_titles", {}))
    return mapping.get(name, _to_title(name))


def _first_meaningful_literal(text: str) -> str:
    for literal in re.findall(r'"([^"\n]{2,48})"', text):
        candidate = literal.strip()
        if not candidate:
            continue
        if candidate.startswith("./") or candidate.startswith("../"):
            continue
        if candidate.endswith((".js", ".css")):
            continue
        if "assets/" in candidate or "__name" in candidate or "data-v-" in candidate:
            continue
        if candidate in {"visible", "close", "default", "update:visible"}:
            continue
        if candidate in {"modulepreload", "anonymous", "function", "button"}:
            continue
        if re.fullmatch(r"[a-z0-9-]{6,}", candidate):
            continue
        if re.search(r"[\u4e00-\u9fffA-Za-z]", candidate):
            return candidate
    return ""


def _meaningful_literals(text: str, limit: int = 24) -> list[str]:
    items: list[str] = []
    for literal in re.findall(r'"([^"\n]{2,64})"', text):
        candidate = literal.strip()
        if not candidate:
            continue
        if candidate.startswith("./") or candidate.startswith("../"):
            continue
        if candidate.endswith((".js", ".css")):
            continue
        if "assets/" in candidate or "__name" in candidate or "data-v-" in candidate:
            continue
        if candidate in {"visible", "close", "default", "update:visible", "value", "onClick", "onUpdate", "link"}:
            continue
        if re.fullmatch(r"\$+\d+", candidate):
            continue
        if re.fullmatch(r"[a-z0-9-]{6,}", candidate):
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z]", candidate):
            continue
        if candidate not in items:
            items.append(candidate)
        if len(items) >= limit:
            break
    return items


def _is_noisy_ui_label(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return True
    lowered = token.lower()
    if token in {"value", "error", "mode", "renew", "cardKey", "TutorialDialog", "PurchaseWindow", "CodexProxyDialog", "CodexAuthDialog", "KiroAuthDialog", "AppContent"}:
        return True
    if lowered in {
        "value",
        "error",
        "mode",
        "renew",
        "cardkey",
        "nonce",
        "load",
        "nsis",
        "msi",
        "http://",
        "https://",
        "div",
        "span",
        "done",
        "side",
        "right",
        "quota_limit",
        "toggle_proxy",
    }:
        return True
    if "replace(" in token or "http://" in lowered or "https://" in lowered:
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) and not re.search(r"[A-Z].*[a-z]|[a-z].*[A-Z]", token):
        return True
    if re.fullmatch(r"[0-9]+(?:px|rem|em|%)", lowered):
        return True
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", lowered):
        return True
    return False


def _clean_ui_labels(values: list[str], *, max_items: int, min_len: int = 2, max_len: int = 20) -> list[str]:
    items: list[str] = []
    for raw in values:
        token = str(raw or "").strip()
        if len(token) < min_len or len(token) > max_len:
            continue
        if _is_noisy_ui_label(token):
            continue
        if token not in items:
            items.append(token)
        if len(items) >= max_items:
            break
    return items


def _labels_by_keywords(values: list[str], keywords: list[str], *, max_items: int, min_len: int = 2, max_len: int = 28) -> list[str]:
    out: list[str] = []
    for raw in values:
        token = str(raw or "").strip()
        if len(token) < min_len or len(token) > max_len:
            continue
        if _is_noisy_ui_label(token):
            continue
        if keywords and not any(keyword in token for keyword in keywords):
            continue
        if token not in out:
            out.append(token)
        if len(out) >= max_items:
            break
    return out


def _remove_label_overlaps(primary: list[str], secondary: list[str]) -> list[str]:
    blocked = {str(x).strip() for x in secondary if str(x).strip()}
    return [item for item in primary if str(item).strip() not in blocked]


def _remove_class_like_labels(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in values:
        token = str(item).strip()
        lowered = token.lower()
        if not token:
            continue
        if "-" in token and not re.search(r"[\u4e00-\u9fff]", token):
            continue
        if lowered.startswith("proxy-btn") or lowered.startswith("form-") or lowered.startswith("tag-") or lowered.startswith("codex-"):
            continue
        if token not in cleaned:
            cleaned.append(token)
    return cleaned


def _unique_preserve(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if token and token not in items:
            items.append(token)
    return items


def _extract_status_messages_generic(text: str) -> list[str]:
    literals = _meaningful_literals(text, limit=80)
    return _labels_by_keywords(
        literals,
        ["成功", "失败", "错误", "保存", "在线", "检测", "登录", "注册", "取消", "完成", "上限"],
        max_items=8,
        min_len=2,
        max_len=32,
    )


def _extract_form_fields_generic(text: str) -> list[str]:
    literals = _meaningful_literals(text, limit=80)
    return _labels_by_keywords(
        literals,
        ["代理", "端口", "账号", "卡密", "密码", "地址", "链接", "proxy"],
        max_items=8,
        min_len=2,
        max_len=24,
    )


def _extract_input_placeholders_generic(text: str) -> list[str]:
    items: list[str] = []
    for value in re.findall(r'placeholder:\s*"([^"]+)"', text):
        token = str(value).strip()
        if token and token not in items:
            items.append(token)
    return items[:6]


def _extract_form_hints_generic(text: str) -> list[str]:
    items: list[str] = []
    for value in re.findall(r'\{\s*class:\s*"form-hint"\s*\}\s*,\s*"([^"]+)"', text):
        token = str(value).strip()
        if token and token not in items:
            items.append(token)
    return items[:6]


def _extract_message_literals_generic(text: str) -> list[str]:
    items: list[str] = []
    for value in re.findall(r"\.\s*(?:warning|error|success|info)\(\s*\"([^\"]+)\"", text):
        token = str(value).strip()
        if token and token not in items:
            items.append(token)
    return items[:10]


def _extract_button_texts_generic(text: str) -> list[str]:
    items: list[str] = []
    for a, b in re.findall(r'B\([^?]+\?\s*"([^"]+)"\s*:\s*"([^"]+)"\)', text):
        for value in (a, b):
            token = str(value).strip()
            if token and token not in items:
                items.append(token)
    for value in re.findall(r'o\(\s*"button"[\s\S]*?,\s*"([^"]+)"\s*,\s*\d+', text):
        token = str(value).strip()
        if token and token not in items:
            items.append(token)
    return items[:8]


def _extract_static_title_generic(text: str, class_name: str) -> str:
    match = re.search(rf'\{{\s*class:\s*"{re.escape(class_name)}"\s*\}}\s*,\s*"([^"]+)"', text)
    return match.group(1).strip() if match else ""


def _parse_js_literal(raw: str) -> Any:
    token = str(raw or "").strip().rstrip(",")
    if token in {"!0", "true"}:
        return True
    if token in {"!1", "false"}:
        return False
    if token == "null":
        return None
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return {"raw": token}


def _ts_literal(value: Any) -> str:
    if isinstance(value, dict) and "raw" in value:
        raw = str(value.get("raw", "")).strip()
        if raw == "Mt()":
            return "readPersistedProxyState()"
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _collect_app_js_files(paths: Any) -> list[tuple[str, str]]:
    readable = paths.restore_v1 / "readable"
    origin = _load_json(paths.analysis / "build_origin_report.json", {"items": []})
    files: list[tuple[str, str]] = []
    for item in origin.get("items", []):
        rel_file = str(item.get("file", "")).strip()
        if (
            rel_file.endswith(".js")
            and str(item.get("origin_label", "")) == "app_business"
            and (readable / rel_file).is_file()
        ):
            files.append((rel_file, read_text(readable / rel_file)))
    if files:
        return sorted(files)
    for p in sorted((readable / "assets").glob("*.js")):
        files.append((str(p.relative_to(readable)).replace("\\", "/"), read_text(p)))
    return files


def _match_analysis_component_hint(file_path: str, rules: dict[str, Any]) -> dict[str, Any]:
    for item in _analysis_rules(rules).get("component_file_name_hints", []) or []:
        if str(item.get("file_contains", "")).strip() and str(item.get("file_contains", "")) in file_path:
            return dict(item)
    return {}


def _extract_object_block(text: str, object_name: str) -> str:
    match = re.search(rf"\b{re.escape(object_name)}\s*=\s*\{{", text)
    if not match:
        return ""
    open_idx = text.find("{", match.start())
    if open_idx < 0:
        return ""
    close_idx = find_matching_brace(text, open_idx)
    if close_idx < 0:
        return ""
    return text[open_idx : close_idx + 1]


def _extract_class_block(text: str, class_name: str) -> str:
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\b", text)
    if not match:
        return ""
    open_idx = text.find("{", match.end())
    if open_idx < 0:
        return ""
    close_idx = find_matching_brace(text, open_idx)
    if close_idx < 0:
        return ""
    return text[match.start() : close_idx + 1]


def _extract_component_info(file_path: str, text: str, rules: dict[str, Any]) -> dict[str, Any] | None:
    name_match = re.search(r'__name:\s*"([^"]+)"', text)
    hint = _match_analysis_component_hint(file_path, rules)
    component_name = ""
    if name_match:
        component_name = _safe_name(name_match.group(1), "RecoveredComponent")
    elif str(hint.get("component_name", "")).strip():
        component_name = _safe_name(str(hint.get("component_name", "")), "RecoveredComponent")
    if not component_name:
        return None
    props = sorted(set(re.findall(r"props:\s*\{([\s\S]*?)\}\s*,\s*emits:", text)))
    prop_keys: list[str] = []
    if props:
        prop_keys = sorted(set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", props[0])))
    emits_match = re.search(r"emits:\s*\[([^\]]*)\]", text)
    emit_keys = sorted(set(re.findall(r'"([^"]+)"', emits_match.group(1) if emits_match else "")))
    handler_names = sorted(set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)))
    if not handler_names:
        handler_names = sorted(set(re.findall(r"on[A-Z][A-Za-z0-9_]+", text)))
    class_refs = sorted(set(re.findall(r'class:\s*"([^"]+)"', text)))
    title = _first_meaningful_literal(text)
    if not title or title in {"value", "link", "onClick", "onUpdate"} or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", title):
        title = _component_display_title(component_name)
    dynamic_imports = sorted(set(re.findall(r'import\("([^"]+)"\)', text)))
    return {
        "name": component_name,
        "source_file": file_path,
        "props": prop_keys,
        "emits": emit_keys,
        "handlers": handler_names[:12],
        "class_refs": class_refs[:24],
        "dynamic_imports": dynamic_imports[:12],
        "title": title,
        "render_mode": "render_component",
        "module_type_hint": str(hint.get("module_type", "")).strip(),
    }


def _extract_handler_blocks(file_path: str, text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in re.finditer(r"((?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\()", text):
        fn_name = match.group(2)
        line = line_of_offset(text, match.start())
        bridge_calls = sorted(set(re.findall(r'h\("([^"]+)"', text[match.start() : match.start() + 800])))
        items.append(
            {
                "file": file_path,
                "name": fn_name,
                "line": line,
                "bridge_calls": bridge_calls[:8],
            }
        )
    return items


def _extract_render_block(file_path: str, text: str) -> dict[str, Any] | None:
    if "setup(" not in text or "return (" not in text:
        return None
    return {
        "file": file_path,
        "has_setup": "setup(" in text,
        "has_render_return": "return (" in text,
        "class_ref_count": len(re.findall(r'class:\s*"([^"]+)"', text)),
        "dynamic_import_count": text.count('import("'),
    }


def _extract_service_methods(text: str, object_name: str) -> list[dict[str, Any]]:
    block = _extract_object_block(text, object_name)
    if not block:
        return []
    methods: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    skip_names = {"catch", "debug", "error", "warn", "info", "return", "String", "Date", "toISOString"}
    method_matches = list(re.finditer(r"(async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{", block))
    for idx, match in enumerate(method_matches):
        method_name = match.group(2)
        if method_name in skip_names or method_name in seen_names:
            continue
        seen_names.add(method_name)
        params = [x.strip() for x in match.group(3).split(",") if x.strip()]
        open_idx = block.find("{", match.end() - 1)
        close_idx = find_matching_brace(block, open_idx) if open_idx >= 0 else -1
        body = block[open_idx : close_idx + 1] if close_idx > open_idx else ""
        commands = sorted(set(re.findall(r'h\("([^"]+)"', body)))
        shell_calls = sorted(set(re.findall(r"K\.shell\.([A-Za-z_][A-Za-z0-9_]*)", body)))
        methods.append(
            {
                "name": method_name,
                "params": params,
                "bridge_commands": commands[:8],
                "shell_calls": shell_calls[:8],
            }
        )
    return methods


def _extract_store_methods(text: str, store_name: str) -> list[dict[str, Any]]:
    match = re.search(rf"\b{re.escape(store_name)}\s*=\s*[A-Za-z_][A-Za-z0-9_]*\([^,]+,\s*\{{", text)
    if not match:
        return []
    open_idx = text.find("{", match.end() - 1)
    if open_idx < 0:
        return []
    close_idx = find_matching_brace(text, open_idx)
    if close_idx < 0:
        return []
    block = text[open_idx : close_idx + 1]
    actions_match = re.search(r"actions:\s*\{", block)
    if not actions_match:
        return []
    actions_open = block.find("{", actions_match.end() - 1)
    actions_close = find_matching_brace(block, actions_open)
    if actions_open < 0 or actions_close < 0:
        return []
    actions_block = block[actions_open : actions_close + 1]
    methods: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    skip_names = {"catch", "return"}
    for method_match in re.finditer(r"(async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{", actions_block):
        method_name = method_match.group(2)
        if method_name in skip_names or method_name in seen_names:
            continue
        seen_names.add(method_name)
        params = [x.strip() for x in method_match.group(3).split(",") if x.strip()]
        body_open = actions_block.find("{", method_match.end() - 1)
        body_close = find_matching_brace(actions_block, body_open) if body_open >= 0 else -1
        body = actions_block[body_open : body_close + 1] if body_close > body_open else ""
        commands = sorted(set(re.findall(r'h\("([^"]+)"', body)))
        methods.append({"name": method_name, "params": params, "bridge_commands": commands[:8]})
    return methods


def _extract_editor_options(text: str) -> list[str]:
    match = re.search(r'E\(\[([^\]]+)\]\)', text)
    if not match:
        return []
    return [x for x in re.findall(r'"([^"]+)"', match.group(1)) if x]


def _extract_button_labels(text: str) -> list[str]:
    labels = [x.strip() for x in re.findall(r'>\s*([^<>\n]{2,24})\s*<', text) if x.strip()]
    out: list[str] = []
    for label in labels:
        if label.startswith("http"):
            continue
        if re.fullmatch(r"\$+\d+", label):
            continue
        if label in {"value", "onClick", "onUpdate", "default", "link"}:
            continue
        if label not in out:
            out.append(label)
    return out[:16]


def _extract_main_view_model(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    main_rule = dict(rules.get("main_view_rule", {}))
    title_literal = str(main_rule.get("title_literal", "")).strip()
    default_title = str(main_rule.get("default_title", "App Content"))
    title = title_literal if title_literal and title_literal in text else default_title
    configured_editors = [str(x).strip() for x in main_rule.get("editor_names", []) if str(x).strip()]
    editor_pattern = "|".join(re.escape(name) for name in configured_editors)
    editor_colors = (
        {key: value for key, value in re.findall(rf'({editor_pattern}):\s*"([^"]+)"', text)}
        if editor_pattern
        else {}
    )
    tutorial_strings = []
    hint_keywords = [str(x) for x in main_rule.get("tutorial_hint_keywords", []) if str(x).strip()]
    for literal in re.findall(r'"([^"\n]{6,64})"', text):
        candidate = literal.strip()
        if candidate.startswith("assets/") or candidate.endswith((".js", ".css")):
            continue
        if any(keyword in candidate for keyword in hint_keywords):
            if candidate not in tutorial_strings:
                tutorial_strings.append(candidate)
    return {
        "editor_options": _extract_editor_options(text) or configured_editors or ["Primary"],
        "action_labels": [x for x in _extract_button_labels(text) if x in set(main_rule.get("action_labels", []))]
        or list(main_rule.get("action_labels", [])),
        "has_announcement": str(main_rule.get("announcement_marker", "announcement")) in text,
        "has_proxy_toggle": str(main_rule.get("proxy_toggle_marker", "toggle_proxy")) in text,
        "has_purchase_flow": str(main_rule.get("purchase_flow_marker", "create_payment_order")) in text,
        "title": title,
        "title_suffix": title_literal if title_literal and title_literal in text else title,
        "proxy_toggle_label": str(main_rule.get("proxy_toggle_label", "Runtime Toggle")),
        "codex_service_label": str(main_rule.get("codex_service_label", "Runtime Service")),
        "announcement_title": str(main_rule.get("announcement_title", "Announcement")),
        "purchase_entry_label": str(main_rule.get("purchase_entry_label", "Open Flow")),
        "purchase_url": str(main_rule.get("purchase_url", "")),
        "install_target_dialog": str(main_rule.get("dialog_open_on_install", "")),
        "tutorial_hints": tutorial_strings[:6],
        "editor_colors": editor_colors or dict(main_rule.get("editor_color_defaults", {})),
        "template_kind": str(main_rule.get("template_kind", "")),
        "template_path": str(main_rule.get("template_path", "")),
    }


def _extract_dialog_state_model(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    trigger_map = dict(rules.get("dialog_trigger_labels", {}))
    for name in list(rules.get("dialog_components", [])):
        if name not in text:
            continue
        items.append(
            {
                "name": name,
                "title": _component_display_title(name, rules),
                "trigger_label": trigger_map.get(name, _component_display_title(name, rules)),
                "default_visible": False,
            }
        )
    return {"items": items}


def _extract_announcement_model(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    main_rule = dict(rules.get("main_view_rule", {}))
    announcement_title = str(main_rule.get("announcement_title", "Announcement"))
    return {
        "enabled": str(main_rule.get("announcement_marker", "announcement")) in text,
        "title": announcement_title if announcement_title and f'"{announcement_title}"' in text else announcement_title,
        "has_link_transform": "announcement-link" in text,
        "has_purchase_deeplink": "app://purchase" in text,
        "emoji": "📣" if "announcement-emoji" in text else "",
    }


def _extract_store_state(text: str, store_name: str) -> dict[str, Any]:
    match = re.search(rf"\b{re.escape(store_name)}\s*=\s*[A-Za-z_][A-Za-z0-9_]*\([^,]+,\s*\{{", text)
    if not match:
        return {"state_fields": [], "getters": []}
    open_idx = text.find("{", match.end() - 1)
    close_idx = find_matching_brace(text, open_idx) if open_idx >= 0 else -1
    if open_idx < 0 or close_idx < 0:
        return {"state_fields": [], "getters": []}
    block = text[open_idx : close_idx + 1]
    state_match = re.search(r"state:\s*\(\)\s*=>\s*\(\{", block)
    state_fields: list[dict[str, Any]] = []
    if state_match:
        state_open = block.find("{", state_match.end() - 1)
        state_close = find_matching_brace(block, state_open)
        if state_open >= 0 and state_close >= 0:
            state_block = block[state_open + 1 : state_close]
            for line in state_block.splitlines():
                entry = line.strip().rstrip(",")
                if not entry or ":" not in entry:
                    continue
                key, value = entry.split(":", 1)
                field_name = key.strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name):
                    continue
                state_fields.append({"name": field_name, "default": _parse_js_literal(value.strip())})
    getters = sorted(set(re.findall(r"getters:\s*\{\s*([A-Za-z_][A-Za-z0-9_]*)", block)))
    return {"state_fields": state_fields, "getters": getters}


def _extract_store_candidates(text: str) -> list[str]:
    items: list[str] = []
    for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[A-Za-z_][A-Za-z0-9_]*\([^,]+,\s*\{", text):
        if name not in items:
            items.append(name)
    return items


def _extract_service_candidates_from_rules(app_files: dict[str, str], rules: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in _analysis_rules(rules).get("service_object_candidates", []) or []:
        spec = dict(raw)
        object_name = str(spec.get("object_name", "")).strip()
        service_key = str(spec.get("service_key", "")).strip()
        file_contains = str(spec.get("source_file_contains", "")).strip()
        if not object_name or not service_key:
            continue
        for file_path, text in app_files.items():
            if file_contains and file_contains not in file_path:
                continue
            methods = _extract_service_methods(text, object_name)
            if not methods and not _extract_object_block(text, object_name):
                continue
            items.append(
                {
                    "file": file_path,
                    "service_key": service_key,
                    "candidate": _safe_name(object_name, "Service"),
                    "role": str(spec.get("role", "service")),
                    "methods": len(methods),
                }
            )
            break
    return items


def _module_type_for_component(name: str, item: dict[str, Any], rules: dict[str, Any]) -> str:
    analysis_rules = dict(rules.get("analysis_rules", {}))
    component_module_types = dict(analysis_rules.get("component_module_types", {}))
    explicit = str(component_module_types.get(name, "")).strip()
    if explicit:
        return explicit
    if str(item.get("module_type_hint", "")).strip():
        return str(item.get("module_type_hint", "")).strip()
    if name in set(rules.get("view_components", [])):
        return "view"
    return "component"


def _service_role_priority(item: dict[str, Any], rules: dict[str, Any]) -> int:
    priorities = dict(_analysis_rules(rules).get("service_role_priorities", {}))
    role = str(item.get("role", "service")).strip()
    try:
        return int(priorities.get(role, 0))
    except Exception:
        return 0


def _filter_store_ids(store_ids: list[str], rules: dict[str, Any]) -> list[str]:
    analysis_rules = _analysis_rules(rules)
    store_candidate_rules = dict(analysis_rules.get("store_candidate_rules", {}))
    hinted = {str(x).strip() for x in analysis_rules.get("store_candidate_hints", []) or [] if str(x).strip()}
    primary_store_id = str(rules.get("primary_store_id", "")).strip()
    if primary_store_id:
        hinted.add(primary_store_id)
    try:
        min_name_length = int(store_candidate_rules.get("min_name_length", 1))
    except Exception:
        min_name_length = 1
    allow_short_hinted_names = bool(store_candidate_rules.get("allow_short_hinted_names", True))
    filtered: list[str] = []
    for store_id in store_ids:
        name = str(store_id).strip()
        if not name:
            continue
        if len(name) < min_name_length and not (allow_short_hinted_names and name in hinted):
            continue
        if name not in filtered:
            filtered.append(name)
    return filtered


def _module_ownership_precedence(rules: dict[str, Any]) -> dict[str, int]:
    priority_rules = dict(_analysis_rules(rules).get("module_priority_rules", {}))
    order = [str(x).strip() for x in priority_rules.get("ownership_precedence", []) if str(x).strip()]
    return {name: idx for idx, name in enumerate(order)}


def _module_conflict_rules(rules: dict[str, Any]) -> dict[str, Any]:
    return dict(_analysis_rules(rules).get("module_conflict_rules", {}))


def _configured_specs(rules: dict[str, Any], key: str, fallback_ids: list[str], default_kind: str) -> list[dict[str, Any]]:
    specs = []
    for raw in _analysis_rules(rules).get(key, []) or []:
        if isinstance(raw, dict):
            specs.append(dict(raw))
    if specs:
        return specs
    return [{"id": item_id, "kind": default_kind} for item_id in fallback_ids if str(item_id).strip()]


def _composable_specs(rules: dict[str, Any]) -> list[dict[str, Any]]:
    priority_rules = dict(_analysis_rules(rules).get("module_priority_rules", {}))
    fallback_ids = [str(x).strip() for x in priority_rules.get("composable_ids", []) if str(x).strip()]
    return _configured_specs(rules, "composable_candidates", fallback_ids, "generic_composable")


def _bootstrap_specs(rules: dict[str, Any]) -> list[dict[str, Any]]:
    priority_rules = dict(_analysis_rules(rules).get("module_priority_rules", {}))
    fallback_ids = [str(x).strip() for x in priority_rules.get("bootstrap_ids", []) if str(x).strip()]
    return _configured_specs(rules, "bootstrap_candidates", fallback_ids, "generic_bootstrap")


def _candidate_conflict_tokens(item: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    conflict_rules = _module_conflict_rules(rules)
    fields = [str(x).strip() for x in conflict_rules.get("dedupe_fields", []) if str(x).strip()]
    if not fields:
        fields = ["id", "output_path"]
    tokens: list[str] = []
    for field in fields:
        value = str(item.get(field, "")).strip()
        if value:
            tokens.append(f"{field}:{value}")
    return tokens


def _source_file_conflict_tokens(item: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    conflict_rules = _module_conflict_rules(rules)
    source_file = str(item.get("source_file", "")).strip()
    module_type = str(item.get("module_type", "")).strip()
    if not source_file or not module_type:
        return []
    fields = [str(x).strip() for x in conflict_rules.get("source_file_conflict_fields", []) if str(x).strip()]
    if not fields:
        return []
    tokens: list[str] = []
    for raw_rule in conflict_rules.get("source_file_conflict_rules", []) or []:
        spec = dict(raw_rule)
        source_contains = str(spec.get("source_file_contains", "")).strip()
        module_types = {str(x).strip() for x in spec.get("module_types", []) if str(x).strip()}
        if source_contains and source_contains not in source_file:
            continue
        if module_types and module_type not in module_types:
            continue
        for field in fields:
            value = str(item.get(field, "")).strip()
            if value:
                tokens.append(f"source_file:{source_contains or '*'}:{field}:{value}")
    return tokens


def _candidate_is_excluded(item: dict[str, Any], rules: dict[str, Any]) -> bool:
    conflict_rules = _module_conflict_rules(rules)
    exclude_ids = {str(x).strip() for x in conflict_rules.get("exclude_ids", []) if str(x).strip()}
    exclude_output_paths = {str(x).strip() for x in conflict_rules.get("exclude_output_paths", []) if str(x).strip()}
    return str(item.get("id", "")).strip() in exclude_ids or str(item.get("output_path", "")).strip() in exclude_output_paths


def _candidate_rank(item: dict[str, Any], rules: dict[str, Any]) -> tuple[int, int, str]:
    precedence = _module_ownership_precedence(rules)
    fidelity = str(item.get("fidelity", "")).strip()
    fidelity_score = {
        "direct_transpile": 0,
        "structured_extract": 1,
        "reconstructed_template": 2,
    }.get(fidelity, 9)
    module_type = str(item.get("module_type", "")).strip()
    return (
        precedence.get(module_type, 99),
        fidelity_score,
        str(item.get("source_file", "")),
    )


def _dedupe_candidates_by_ownership(groups: list[list[dict[str, Any]]], rules: dict[str, Any]) -> list[list[dict[str, Any]]]:
    chosen_by_token: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            if _candidate_is_excluded(item, rules):
                continue
            for token in _candidate_conflict_tokens(item, rules) + _source_file_conflict_tokens(item, rules):
                current = chosen_by_token.get(token)
                if current is None or _candidate_rank(item, rules) < _candidate_rank(current, rules):
                    chosen_by_token[token] = item
    resolved_groups: list[list[dict[str, Any]]] = []
    for group in groups:
        resolved: list[dict[str, Any]] = []
        for item in group:
            if _candidate_is_excluded(item, rules):
                continue
            rejected = False
            for token in _candidate_conflict_tokens(item, rules) + _source_file_conflict_tokens(item, rules):
                if chosen_by_token.get(token) is not item:
                    rejected = True
                    break
            if rejected:
                continue
            resolved.append(item)
        resolved_groups.append(resolved)
    return resolved_groups


def _guess_component_name_from_file(file_path: str) -> str:
    stem = Path(file_path).stem.split("-", 1)[0].strip()
    token = _safe_name(stem, "RecoveredComponent")
    if token.lower() == "main":
        return "RecoveredMainView"
    return token


def _select_component_by_keywords(names: list[str], *keywords: str) -> str:
    lowered = [(name, name.lower()) for name in names]
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for name, lowered_name in lowered:
            if keyword_lower in lowered_name:
                return name
    return names[0] if names else ""


def _guess_runtime_service_bindings(service_keys: list[str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    available = {key: key for key in service_keys}
    for preferred in ("auth", "shell", "config", "clipboard", "errorLog"):
        if preferred in available:
            bindings[preferred] = available[preferred]
    return bindings


def _extract_editor_descriptions_generic(text: str) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for editor, desc in re.findall(r"(Windsurf|Cursor|Kiro|Codex):\s*`([\s\S]*?)`", text):
        normalized = " ".join(line.strip() for line in desc.splitlines() if line.strip())
        if normalized:
            descriptions[editor] = normalized
    return descriptions


def _extract_plan_labels_generic(text: str) -> list[str]:
    labels = [candidate.strip() for candidate in re.findall(r'label:\s*"([^"]+)"', text)]
    return _clean_ui_labels(labels, max_items=8, min_len=2, max_len=24)


def _extract_price_points_generic(text: str) -> list[str]:
    items: list[str] = []
    for candidate in re.findall(r"price:\s*([0-9]+(?:\.[0-9]+)?)", text):
        value = f"¥{candidate}"
        if value not in items:
            items.append(value)
    for candidate in re.findall(r"magicPrice:\s*([0-9]+(?:\.[0-9]+)?)", text):
        value = f"magic ¥{candidate}"
        if value not in items:
            items.append(value)
    return items[:8]


def _build_generated_special_component_rule(name: str, source_file: str, text: str, title: str, class_refs: list[str]) -> dict[str, Any] | None:
    return analyze_component_structure(
        name=name,
        source_file=source_file,
        text=text,
        fallback_title=title,
        class_refs=class_refs,
    )


def _guess_source_rules_from_readable(workspace: Path, run_id: str) -> dict[str, Any]:
    paths, _ = _source_root(workspace, run_id)
    app_files = _collect_app_js_files(paths)
    main_source_file = next((file_path for file_path, _ in app_files if "main-" in file_path), "")
    component_titles: dict[str, str] = {}
    dialog_components: list[str] = []
    view_components: list[str] = []
    component_file_name_hints: list[dict[str, Any]] = []
    special_component_rules: dict[str, Any] = {}

    for file_path, text in app_files:
        guessed_name = ""
        name_match = re.search(r'__name:\s*"([^"]+)"', text)
        if name_match:
            guessed_name = _safe_name(name_match.group(1), "RecoveredComponent")
        elif "main-" in file_path:
            guessed_name = "RecoveredMainView"
        elif "export" in text or "defineComponent" in text or "setup(" in text:
            guessed_name = _guess_component_name_from_file(file_path)
        if not guessed_name:
            continue
        title = _first_meaningful_literal(text) or _to_title(guessed_name)
        if title in {"value", "onClick", "link", "default", "close"} or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", title):
            title = _to_title(guessed_name)
        component_titles[guessed_name] = title
        hint: dict[str, Any] = {"file_contains": Path(file_path).name, "component_name": guessed_name}
        if "main-" in file_path:
            hint["module_type"] = "view"
            if guessed_name not in view_components:
                view_components.append(guessed_name)
        else:
            if guessed_name not in dialog_components:
                dialog_components.append(guessed_name)
        component_file_name_hints.append(hint)
        class_refs = sorted(set(re.findall(r'class:\s*"([^"]+)"', text)))[:16]
        generated_special = _build_generated_special_component_rule(guessed_name, file_path, text, title, class_refs)
        if generated_special and guessed_name not in special_component_rules:
            special_component_rules[guessed_name] = generated_special

    if not view_components:
        view_components = ["RecoveredMainView"]
        component_titles.setdefault("RecoveredMainView", "Recovered Main View")
        if main_source_file:
            component_file_name_hints.append(
                {"file_contains": Path(main_source_file).name, "component_name": "RecoveredMainView", "module_type": "view"}
            )

    main_text = next((text for file_path, text in app_files if file_path == main_source_file), "")
    editor_names = _extract_editor_options(main_text)
    action_labels = _extract_button_labels(main_text)
    store_hints = _filter_store_ids(_extract_store_candidates(main_text), {"analysis_rules": {"store_candidate_rules": {"min_name_length": 3}}})
    primary_store_id = store_hints[0] if store_hints else "appStore"
    dialog_trigger_labels = {name: component_titles.get(name, _to_title(name)) for name in dialog_components}
    required_service_keys = sorted({
        str(item.get("service_key", "")).strip()
        for item in _load_json(paths.analysis / "service_facade_profile.json", {"items": []}).get("items", [])
        if str(item.get("service_key", "")).strip()
    })
    if not required_service_keys:
        required_service_keys = sorted({
            str(item.get("service_key", "")).strip()
            for item in _extract_service_candidates_from_rules({file_path: text for file_path, text in app_files}, {"analysis_rules": {"service_object_candidates": []}})
            if str(item.get("service_key", "")).strip()
        })
    tutorial_dialog_id = _select_component_by_keywords(dialog_components, "tutorial", "guide", "help")
    purchase_dialog_id = _select_component_by_keywords(dialog_components, "purchase", "pay", "shop", "renew")
    proxy_dialog_id = _select_component_by_keywords(dialog_components, "proxy")
    auth_dialog_id = _select_component_by_keywords(
        [name for name in dialog_components if name not in {tutorial_dialog_id, purchase_dialog_id, proxy_dialog_id}],
        "auth",
        "login",
        "account",
    )
    runtime_service_bindings = _guess_runtime_service_bindings(required_service_keys)
    filtered_action_labels = []
    for label in action_labels:
        if label not in filtered_action_labels and len(label) >= 2:
            filtered_action_labels.append(label)
    generated_title = component_titles.get(view_components[0], "Recovered Main View")
    return {
        "_comment": "Auto-generated source reconstruction rules for this run. Manual project rules override this file.",
        "component_titles": component_titles,
        "dialog_components": dialog_components,
        "view_components": view_components,
        "bootstrap_view_id": view_components[0],
        "primary_store_id": primary_store_id,
        "dialog_trigger_labels": dialog_trigger_labels,
        "analysis_rules": {
            "module_priority_rules": {
                "component_module_types": {name: "view" for name in view_components}
                | {name: "component" for name in dialog_components},
                "service_role_priorities": {"logger": 100, "service": 90, "registry": 70},
                "ownership_precedence": ["bootstrap", "view", "component", "service", "store", "composable", "util"],
                "composable_ids": ["useRuntimeServices", "useDialogState"],
                "bootstrap_ids": ["AppRoot", "MainEntry"],
            },
            "component_file_name_hints": component_file_name_hints,
            "service_object_candidates": [],
            "store_candidate_rules": {"min_name_length": 3, "allow_short_hinted_names": False},
            "store_candidate_hints": store_hints[:4],
            "composable_candidates": [
                {
                    "id": "useRuntimeServices",
                    "kind": "runtime_services",
                    "output_path": "src/composables/useRuntimeServices.ts",
                    "source_file": "analysis/source_reconstruction/service_facades.json",
                },
                {
                    "id": "useDialogState",
                    "kind": "dialog_state",
                    "output_path": "src/composables/useDialogState.ts",
                    "source_file": "analysis/source_reconstruction/component_exports.json",
                },
            ],
            "bootstrap_candidates": [
                {
                    "id": "AppRoot",
                    "kind": "app_root",
                    "output_path": "src/App.vue",
                    "source_file": main_source_file or "assets/main.js",
                    "depends_on_rule": "bootstrap_view_id",
                },
                {
                    "id": "MainEntry",
                    "kind": "main_entry",
                    "output_path": "src/main.ts",
                    "source_file": main_source_file or "assets/main.js",
                    "depends_on": ["AppRoot"],
                },
            ],
            "module_conflict_rules": {
                "exclude_ids": [],
                "exclude_output_paths": [],
                "dedupe_fields": ["id", "output_path", "service_key", "name"],
                "source_file_conflict_fields": ["service_key", "name"],
                "source_file_conflict_rules": [
                    {
                        "source_file_contains": "main-",
                        "module_types": ["view", "service", "store", "composable", "bootstrap", "util"],
                    }
                ],
            },
        },
        "special_component_rules": special_component_rules,
        "main_view_rule": {
            "default_title": generated_title,
            "title_literal": generated_title,
            "editor_names": editor_names,
            "action_labels": filtered_action_labels[:4] or ["Open Tutorial", "Open Dialog"],
            "proxy_toggle_label": "Runtime Toggle",
            "codex_service_label": "Runtime Service",
            "announcement_title": "Announcement",
            "purchase_entry_label": "Open Flow",
            "purchase_url": "",
            "editor_color_defaults": {},
            "tutorial_hint_keywords": editor_names[:2],
            "proxy_toggle_marker": "toggle_proxy",
            "purchase_flow_marker": "create_payment_order",
            "announcement_marker": "announcement",
            "dialog_open_on_install": purchase_dialog_id or tutorial_dialog_id or auth_dialog_id,
            "tutorial_dialog_id": tutorial_dialog_id or auth_dialog_id or (dialog_components[0] if dialog_components else ""),
            "purchase_dialog_id": purchase_dialog_id or (dialog_components[0] if dialog_components else ""),
            "proxy_dialog_id": proxy_dialog_id,
            "tutorial_open_label": "Open Tutorial",
            "purchase_open_label": "Open Related Flow",
            "proxy_settings_label": "Open Settings",
            "runtime_service_bindings": runtime_service_bindings,
            "primary_store_contract": {
                "initialize_method": "initialize",
                "refresh_method": "refresh",
                "quota_method": "getQuota",
                "disable_proxy_method": "disableProxy",
                "announcement_field": "announcement",
                "announcement_date_field": "announcementDate",
                "proxy_enabled_field": "accelerateEnabled",
            },
        },
        "special_store_rules": {},
        "special_composable_rules": {},
        "source_project_contracts": {
            "required_service_keys": required_service_keys[:5],
            "required_component_ids": dialog_components[:4],
            "min_partition_count": max(4, len(dialog_components) + len(required_service_keys)),
        },
    }


def cmd_bootstrap_source_rules(workspace: Path, run_id: str) -> None:
    generated_path = _generated_source_rules_path(workspace, run_id)
    manual_path = workspace / "cache" / "project" / "source_reconstruction_rules.json"
    payload = {
        "run_id": run_id,
        "rule_mode": "manual_override" if manual_path.is_file() else "generated_seed",
        "manual_rule_path": str(manual_path),
        "generated_rule_path": str(generated_path),
        "rules": _guess_source_rules_from_readable(workspace, run_id),
    }
    write_json(generated_path, payload["rules"])
    write_json(generated_path.with_name("source_reconstruction_rule_bootstrap_report.json"), payload)


def cmd_decompile_bundle_structure(workspace: Path, run_id: str) -> None:
    paths, root = _source_root(workspace, run_id)
    rules = _load_source_reconstruction_rules(workspace, run_id)
    app_files = _collect_app_js_files(paths)
    js_semantic = _load_json(paths.analysis / "js_semantic_profile.json", {"items": [], "summary": {}})
    service_facade = _load_json(paths.analysis / "service_facade_profile.json", {"items": []})

    runtime_shells: list[dict[str, Any]] = []
    dynamic_import_groups: list[dict[str, Any]] = []
    component_exports: list[dict[str, Any]] = []
    render_blocks: list[dict[str, Any]] = []
    handler_blocks: list[dict[str, Any]] = []
    service_facades: list[dict[str, Any]] = []

    for file_path, text in app_files:
        runtime_shells.append(
            {
                "file": file_path,
                "vite_mapdeps_count": text.count("__vite__mapDeps"),
                "dynamic_import_count": text.count('import("'),
                "plugin_export_helper_count": text.count("_plugin-vue_export-helper"),
                "render_helper_import_count": len(re.findall(r'import\s*\{[^}]+\}\s*from\s*"./naive-ui', text)),
            }
        )
        imports = sorted(set(re.findall(r'import\("([^"]+)"\)', text)))
        if imports:
            dynamic_import_groups.append({"file": file_path, "imports": imports})
        component_info = _extract_component_info(file_path, text, rules)
        if component_info:
            component_exports.append(component_info)
        render_block = _extract_render_block(file_path, text)
        if render_block:
            render_blocks.append(render_block)
        handler_blocks.extend(_extract_handler_blocks(file_path, text))

    for item in service_facade.get("items", []):
        methods_raw = item.get("methods", 0)
        if isinstance(methods_raw, list):
            methods_count = len(methods_raw)
        else:
            methods_count = int(methods_raw or 0)
        service_facades.append(
            {
                "file": str(item.get("file", "")),
                "service_key": str(item.get("service_key", "")),
                "candidate": _safe_name(str(item.get("candidate", "")) or str(item.get("service_key", "")), "Service"),
                "role": str(item.get("role", "service")),
                "methods": methods_count,
            }
        )
    for item in js_semantic.get("items", []):
        if str(item.get("kind", "")) == "logger_like":
            service_facades.append(
                {
                    "file": str(item.get("file", "")),
                    "service_key": "logger",
                    "candidate": "AppLogger",
                    "role": "logger",
                    "methods": len(item.get("methods", []) if isinstance(item.get("methods", []), list) else []),
                }
            )
        if str(item.get("kind", "")) == "registry_like":
            service_facades.append(
                {
                    "file": str(item.get("file", "")),
                    "service_key": "registry",
                    "candidate": _safe_name(str(item.get("entity_name", "")), "ServiceRegistry"),
                    "role": "registry",
                    "methods": 0,
                }
            )
    for item in _extract_service_candidates_from_rules({file_path: text for file_path, text in app_files}, rules):
        service_facades.append(item)

    write_json(root / "runtime_shells.json", {"run_id": run_id, "items": runtime_shells})
    write_json(root / "dynamic_import_groups.json", {"run_id": run_id, "items": dynamic_import_groups})
    write_json(root / "component_exports.json", {"run_id": run_id, "items": component_exports})
    write_json(root / "service_facades.json", {"run_id": run_id, "items": service_facades})
    write_json(root / "render_blocks.json", {"run_id": run_id, "items": render_blocks})
    write_json(root / "handler_blocks.json", {"run_id": run_id, "items": handler_blocks})


def cmd_extract_source_modules(workspace: Path, run_id: str) -> None:
    paths, root = _source_root(workspace, run_id)
    rules = _load_source_reconstruction_rules(workspace, run_id)
    component_exports = _load_json(root / "component_exports.json", {"items": []}).get("items", [])
    service_facades = _load_json(root / "service_facades.json", {"items": []}).get("items", [])
    handler_blocks = _load_json(root / "handler_blocks.json", {"items": []}).get("items", [])
    app_files = {file_path: text for file_path, text in _collect_app_js_files(paths)}
    main_text = ""
    main_source_file = ""
    for file_path, text in app_files.items():
        if "main-" in file_path:
            main_source_file = file_path
            main_text = text
            break

    component_candidates: list[dict[str, Any]] = []
    for item in component_exports:
        name = _safe_name(str(item.get("name", "")), "RecoveredComponent")
        module_kind = _module_type_for_component(name, item, rules)
        output_path = f"src/views/{name}.vue" if module_kind == "view" else f"src/components/{name}.vue"
        source_file = str(item.get("source_file", ""))
        source_text = app_files.get(source_file, "")
        component_model: dict[str, Any] = {}
        if source_text:
            component_model = build_component_model_from_rules(
                name=name,
                source_text=source_text,
                main_text=main_text,
                rules=rules,
            )
        if not component_model and source_text:
            generated_special = _build_generated_special_component_rule(
                name,
                source_file,
                source_text,
                _component_display_title(name, rules),
                list(item.get("class_refs", [])),
            )
            if generated_special:
                component_model = dict(generated_special.get("model", {}))
                component_model["template_kind"] = str(generated_special.get("template_kind", "")).strip()
        component_candidates.append(
            {
                "id": name,
                "module_type": module_kind,
                "name": name,
                "source_file": source_file,
                "output_path": output_path,
                "props": list(item.get("props", [])),
                "emits": list(item.get("emits", [])),
                "handlers": list(item.get("handlers", [])),
                "class_refs": list(item.get("class_refs", [])),
                "title": _component_display_title(name, rules),
                "component_model": component_model,
                "fidelity": "structured_extract",
            }
        )

    service_candidates: list[dict[str, Any]] = []
    if main_text:
        logger_block = _extract_class_block(main_text, "AppLogger")
        if logger_block:
            service_candidates.append(
                {
                    "id": "AppLogger",
                    "module_type": "util",
                    "name": "AppLogger",
                    "service_key": "logger",
                    "output_path": "src/utils/logger.ts",
                    "source_file": "main",
                    "class_source": logger_block,
                    "fidelity": "direct_transpile",
                }
            )
    for item in service_facades:
        candidate = _safe_name(
            str(item.get("service_candidate", "")) or str(item.get("candidate", "")) or str(item.get("service_key", "")),
            "Service",
        )
        service_key = str(item.get("service_key", "")).strip() or candidate.lower()
        source_file = str(item.get("file", "")).strip()
        source_text = app_files.get(source_file, main_text)
        methods = _extract_service_methods(source_text, candidate) if source_text else []
        if not methods and source_text:
            methods = _extract_service_methods(source_text, candidate[:1].upper() + candidate[1:]) or _extract_service_methods(
                source_text, service_key[:1].upper() + service_key[1:]
            )
        output_path = f"src/services/{service_key}.ts"
        if str(item.get("role", "")) == "logger":
            continue
        service_candidates.append(
            {
                "id": candidate,
                "module_type": "service",
                "name": candidate,
                "service_key": service_key,
                "role": str(item.get("role", "service")),
                "source_file": source_file,
                "output_path": output_path,
                "methods": methods,
                "fidelity": "structured_extract",
            }
        )

    service_candidates = sorted(
        service_candidates,
        key=lambda item: (-_service_role_priority(item, rules), str(item.get("service_key", "")), str(item.get("source_file", ""))),
    )
    seen_service_keys: set[str] = set()
    deduped_services: list[dict[str, Any]] = []
    for item in service_candidates:
        key = str(item.get("service_key", "")).strip() or str(item.get("id", ""))
        if key in seen_service_keys:
            continue
        seen_service_keys.add(key)
        deduped_services.append(item)

    store_ids = _extract_store_candidates(main_text) if main_text else []
    for hinted_store in dict(rules.get("analysis_rules", {})).get("store_candidate_hints", []) or []:
        hinted_store_name = str(hinted_store).strip()
        if hinted_store_name and hinted_store_name not in store_ids:
            store_ids.append(hinted_store_name)
    store_ids = _filter_store_ids(store_ids, rules)
    primary_store_id = str(rules.get("primary_store_id", "")).strip()
    if not store_ids and primary_store_id:
        store_ids = [primary_store_id]
    main_view_model = _extract_main_view_model(main_text, rules) if main_text else {}
    dialog_state_model = _extract_dialog_state_model(main_text, rules) if main_text else {"items": []}
    announcement_model = _extract_announcement_model(main_text, rules) if main_text else {}

    store_candidates: list[dict[str, Any]] = []
    for store_id in store_ids:
        store_model = _extract_store_state(main_text, store_id) if main_text else {"state_fields": [], "getters": []}
        store_candidates.append(
            {
                "id": store_id,
                "module_type": "store",
                "name": store_id,
                "source_file": main_source_file or "assets/main.js",
                "output_path": f"src/stores/{_safe_lower_file_stem(store_id, 'store')}.ts",
                "methods": _extract_store_methods(main_text, store_id) if main_text else [],
                "state_fields": list(store_model.get("state_fields", [])),
                "getters": list(store_model.get("getters", [])),
                "fidelity": "structured_extract",
            }
        )
    composable_candidates: list[dict[str, Any]] = []
    for spec in _composable_specs(rules):
        composable_id = _safe_name(str(spec.get("id", "")), "RecoveredComposable")
        composable_kind = str(spec.get("kind", "generic_composable")).strip() or "generic_composable"
        item = {
            "id": composable_id,
            "module_type": "composable",
            "name": composable_id,
            "kind": composable_kind,
            "source_file": str(spec.get("source_file", "")).strip() or f"analysis/source_reconstruction/{composable_id}.json",
            "output_path": str(spec.get("output_path", "")).strip() or f"src/composables/{composable_id}.ts",
            "fidelity": "structured_extract",
        }
        if composable_kind == "dialog_state":
            item["dialog_model"] = dialog_state_model
        if composable_kind == "runtime_services":
            item["service_keys"] = [str(x.get("service_key", "")).strip() for x in deduped_services if str(x.get("service_key", "")).strip()]
        composable_candidates.append(item)

    bootstrap_candidates: list[dict[str, Any]] = []
    for spec in _bootstrap_specs(rules):
        bootstrap_id = _safe_name(str(spec.get("id", "")), "RecoveredBootstrap")
        bootstrap_kind = str(spec.get("kind", "generic_bootstrap")).strip() or "generic_bootstrap"
        depends_on = [str(x).strip() for x in spec.get("depends_on", []) if str(x).strip()]
        depends_on_rule = str(spec.get("depends_on_rule", "")).strip()
        if depends_on_rule:
            depends_on_value = str(rules.get(depends_on_rule, "")).strip()
            if depends_on_value:
                depends_on.append(depends_on_value)
        candidate = {
            "id": bootstrap_id,
            "module_type": "bootstrap",
            "name": bootstrap_id,
            "kind": bootstrap_kind,
            "source_file": str(spec.get("source_file", "")).strip() or main_source_file or "assets/main.js",
            "output_path": str(spec.get("output_path", "")).strip() or f"src/{bootstrap_id}.ts",
            "depends_on": depends_on,
            "fidelity": "structured_extract",
        }
        if bootstrap_kind == "app_root":
            candidate["view_model"] = main_view_model
            candidate["dialog_model"] = dialog_state_model
            candidate["announcement_model"] = announcement_model
        elif bootstrap_kind == "main_entry":
            candidate["view_model"] = main_view_model
        bootstrap_candidates.append(candidate)

    component_candidates, deduped_services, store_candidates, composable_candidates, bootstrap_candidates = _dedupe_candidates_by_ownership(
        [component_candidates, deduped_services, store_candidates, composable_candidates, bootstrap_candidates],
        rules,
    )

    plan = {
        "run_id": run_id,
        "component_count": len(component_candidates),
        "service_count": len(deduped_services),
        "store_count": len(store_candidates),
        "composable_count": len(composable_candidates),
        "bootstrap_count": len(bootstrap_candidates),
        "handler_count": len(handler_blocks),
    }
    write_json(root / "component_candidates.json", {"run_id": run_id, "items": component_candidates})
    write_json(root / "service_candidates.json", {"run_id": run_id, "items": deduped_services})
    write_json(root / "store_candidates.json", {"run_id": run_id, "items": store_candidates})
    write_json(root / "composable_candidates.json", {"run_id": run_id, "items": composable_candidates})
    write_json(root / "bootstrap_candidates.json", {"run_id": run_id, "items": bootstrap_candidates})
    write_json(root / "main_view_model.json", {"run_id": run_id, **main_view_model})
    write_json(root / "dialog_state_model.json", {"run_id": run_id, **dialog_state_model})
    write_json(root / "announcement_model.json", {"run_id": run_id, **announcement_model})
    write_json(root / "source_reconstruction_plan.json", plan)


def cmd_build_source_graph(workspace: Path, run_id: str) -> None:
    rules = _load_source_reconstruction_rules(workspace, run_id)
    _, root = _source_root(workspace, run_id)
    component_candidates = _load_json(root / "component_candidates.json", {"items": []}).get("items", [])
    service_candidates = _load_json(root / "service_candidates.json", {"items": []}).get("items", [])
    store_candidates = _load_json(root / "store_candidates.json", {"items": []}).get("items", [])
    composable_candidates = _load_json(root / "composable_candidates.json", {"items": []}).get("items", [])
    bootstrap_candidates = _load_json(root / "bootstrap_candidates.json", {"items": []}).get("items", [])

    bootstrap_view_ids = {
        str(dep)
        for item in bootstrap_candidates
        for dep in item.get("depends_on", [])
        if str(dep).strip()
    }
    nodes: list[dict[str, Any]] = []
    for item in component_candidates + service_candidates + store_candidates + composable_candidates + bootstrap_candidates:
        node_id = str(item.get("id", "")).strip()
        module_type = str(item.get("module_type", "module"))
        deps: list[str] = []
        if module_type == "view" and node_id in bootstrap_view_ids:
            deps.extend([str(x.get("id", "")) for x in component_candidates if str(x.get("id", "")) != node_id])
            deps.extend([str(x.get("id", "")) for x in service_candidates])
            deps.extend([str(x.get("id", "")) for x in store_candidates])
            deps.extend([str(x.get("id", "")) for x in composable_candidates])
        elif module_type == "bootstrap":
            deps.extend([str(x) for x in item.get("depends_on", [])])
        elif module_type == "composable" and str(item.get("kind", "")).strip() == "runtime_services":
            deps.extend([str(x.get("id", "")) for x in service_candidates])
        nodes.append(
            {
                "id": node_id,
                "module_type": module_type,
                "name": str(item.get("name", node_id)),
                "source_file": str(item.get("source_file", "")),
                "output_path": str(item.get("output_path", "")),
                "dependencies": sorted({x for x in deps if x and x != node_id}),
                "exports": [str(item.get("name", node_id))],
                "fidelity": str(item.get("fidelity", "structured_extract")),
                "allow_fallback": bool(module_type in {"component", "service", "store", "composable"} and node_id not in set(dict(rules.get("analysis_rules", {})).get("bootstrap_ids", []))),
            }
        )
    plan = _load_json(root / "source_reconstruction_plan.json", {})
    plan["module_graph_nodes"] = len(nodes)
    plan["source_module_adoption_rate"] = round(
        len(nodes) / max(1, len(component_candidates) + len(service_candidates) + len(store_candidates) + len(composable_candidates) + len(bootstrap_candidates)),
        4,
    )
    write_json(root / "module_graph.json", {"run_id": run_id, "nodes": nodes})
    write_json(root / "source_reconstruction_plan.json", plan)


def _to_title(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).strip() or name


def _render_component_props_interface(props: list[str]) -> str:
    entries = [f"  {_safe_name(prop, 'prop')}?: {_component_prop_ts_type(prop)};" for prop in props if prop]
    if "visible" not in props:
        entries.insert(0, "  visible?: boolean;")
    return "\n".join(entries) or "  visible?: boolean;"


def _render_component_props_object(props: list[str]) -> str:
    lines: list[str] = []
    for prop in props:
        key = _safe_name(prop, "prop")
        if key == "visible":
            lines.append("  visible: { type: Boolean, default: false },")
        else:
            lines.append(f'  {key}: {{ type: null, default: undefined }},')
    if "visible" not in props:
        lines.insert(0, "  visible: { type: Boolean, default: false },")
    return "\n".join(lines)


def _render_component_emits_array(emits: list[str]) -> str:
    items = sorted({x for x in emits if x})
    if "close" not in items:
        items.append("close")
    return ", ".join(f'"{x}"' for x in items)


def _component_prop_ts_type(prop: str) -> str:
    key = _safe_name(prop, "prop")
    if key in {"visible", "hasCard", "inProgress", "bgMode"}:
        return "boolean"
    if key == "availableEditors":
        return "string[]"
    if key in {"logs", "accountStatuses"}:
        return "unknown[]"
    if key in {"editorName", "currentCard", "type"}:
        return "string"
    if key in {"onInstall"}:
        return "() => void"
    return "unknown"


def _render_component_module(workspace: Path, item: dict[str, Any]) -> str:
    name = _safe_name(str(item.get("name", "")), "RecoveredComponent")
    title = str(item.get("title", name))
    props = list(item.get("props", []))
    emits = list(item.get("emits", []))
    handlers = list(item.get("handlers", []))
    class_refs = list(item.get("class_refs", []))
    source_file = str(item.get("source_file", ""))
    component_model = dict(item.get("component_model", {})) if isinstance(item.get("component_model", {}), dict) else {}
    specialized = render_component_from_rules(
        workspace=workspace,
            name=name,
            title=title,
            props=props,
            emits=emits,
            source_file=source_file,
            component_model=component_model,
        render_component_props_interface=_render_component_props_interface,
        render_component_emits_array=_render_component_emits_array,
    )
    if specialized:
        return specialized
    handler_buttons = "\n".join(
        f'      <button class="restorex-action" @click="emitClose()">{_to_title(hn)}</button>'
        for hn in handlers[:4]
    )
    if not handler_buttons:
        handler_buttons = '      <button class="restorex-action" @click="emitClose()">Close</button>'
    class_tags = "\n".join(f"      <code>{tag}</code>" for tag in class_refs[:8]) or "      <code>no-class-refs</code>"
    emit_array = _render_component_emits_array(emits)
    emit_visibility_sync = '  emit("update:visible", false);\n' if "update:visible" in emits else ""
    return f"""<script setup lang="ts">
interface {name}Props {{
{_render_component_props_interface(props)}
}}

const props = withDefaults(defineProps<{name}Props>(), {{
  visible: false,
}});

const emit = defineEmits([{emit_array}]);

function emitClose() {{
{emit_visibility_sync}  emit("close");
}}
</script>

<template>
  <section v-if="props.visible" class="restorex-dialog-shell">
    <header class="restorex-dialog-header">
      <h2>{title}</h2>
      <button class="restorex-close" @click="emitClose">x</button>
    </header>
    <p class="restorex-source">Source: {source_file}</p>
    <p class="restorex-note">This component is auto-generated from RestoreX analysis.</p>
    <div class="restorex-tags">
{class_tags}
    </div>
    <div class="restorex-actions">
{handler_buttons}
    </div>
  </section>
</template>
"""
def _render_logger_module(class_source: str) -> str:
    sanitized = class_source.replace("class AppLogger", "export class AppLogger", 1)
    return f"""{sanitized}

export const logger = new AppLogger();

export default logger;
"""


def _render_service_module(item: dict[str, Any]) -> str:
    name = _safe_name(str(item.get("name", "")), "Service")
    methods = list(item.get("methods", []))
    method_blocks: list[str] = []
    for method in methods:
        method_name = _safe_name(str(method.get("name", "")), "run")
        if method_name in {"initialize", "refresh", "logout", "getQuota"}:
            continue
        params = [_normalize_param_name(x, idx) for idx, x in enumerate(method.get("params", []), start=1)]
        param_sig = ", ".join(params)
        payload_expr = "{" + ", ".join(f"{p}: {p}" for p in params) + "}" if params else "undefined"
        commands = list(method.get("bridge_commands", []))
        command = commands[0] if commands else method_name
        method_blocks.append(
            f"""  async {method_name}({param_sig}) {{
    return invokeRuntime("{command}", {payload_expr});
  }},"""
        )
    if not method_blocks:
        method_blocks.append(
            """  async probe() {
    return invokeRuntime("service_probe", undefined);
  },"""
        )
    return f"""import {{ invokeRuntime }} from "../utils/runtime";

export const {name} = {{
{chr(10).join(method_blocks)}
}};

export default {name};
"""


def _render_store_module(workspace: Path, item: dict[str, Any], rules: dict[str, Any]) -> str:
    methods = list(item.get("methods", []))
    state_fields = list(item.get("state_fields", []))
    state_lines = []
    for field in state_fields:
        field_name = _safe_name(str(field.get("name", "")), "stateField")
        state_lines.append(f"  {field_name}: {_ts_literal(field.get('default'))},")
    if not state_lines:
        state_lines = ["  ready: false,"]
    store_export_name = f"use{_safe_name(str(item.get('name', 'store')), 'Store')[:1].upper()}{_safe_name(str(item.get('name', 'store')), 'Store')[1:]}"
    special = render_store_from_rules(
        workspace=workspace,
        store_id=str(item.get("id", "")),
        rules=rules,
        replacements={
            "{{STATE_LINES}}": chr(10).join(state_lines),
            "{{STORE_EXPORT_NAME}}": store_export_name,
        },
    )
    if special:
        return special
    method_blocks: list[str] = []
    method_names: list[str] = []
    seen_method_names: set[str] = set()
    for method in methods:
        method_name = _safe_name(str(method.get("name", "")), "run")
        if method_name in seen_method_names:
            continue
        seen_method_names.add(method_name)
        method_names.append(method_name)
        params = [_normalize_param_name(x, idx) for idx, x in enumerate(method.get("params", []), start=1)]
        param_sig = ", ".join(params)
        payload_expr = "{" + ", ".join(f"{p}: {p}" for p in params) + "}" if params else "undefined"
        commands = list(method.get("bridge_commands", []))
        command = commands[0] if commands else method_name
        method_blocks.append(
            f"""  async function {method_name}({param_sig}) {{
    const result = await invokeRuntime("{command}", {payload_expr});
    state.lastAction = "{method_name}";
    return result;
  }}"""
        )
    if not method_blocks:
        method_names.append("probe")
        method_blocks.append(
            """  async function probe() {
    state.lastAction = "probe";
    return invokeRuntime("store_probe", undefined);
  }"""
        )
    return_entries = "\n".join(f"    {name}," for name in method_names)
    return f"""import {{ reactive, readonly }} from "vue";
import {{ invokeRuntime }} from "../utils/runtime";

const state = reactive({{
{chr(10).join(state_lines)}
  lastAction: "",
}});

export function {store_export_name}() {{
{chr(10).join(method_blocks)}

  return {{
    state: readonly(state),
{return_entries}
  }};
}}

export default {store_export_name};
"""


def _render_runtime_services_composable(composable_name: str, service_ids: list[str]) -> str:
    imports = "\n".join(
        f'import {service_id} from "../services/{service_id.lower()}";'
        for service_id in service_ids
    )
    map_entries = ",\n    ".join(f"{service_id}: {service_id}" for service_id in service_ids) or "services: {}"
    alias_entries = "\n".join(f"    {service_id}: services.{service_id}," for service_id in service_ids)
    return f"""{imports}

export function {composable_name}() {{
  const services = {{
    {map_entries}
  }};

  return {{
    services,
    serviceList: Object.keys(services),
{alias_entries}
  }};
}}

export default {composable_name};
"""


def _render_runtime_services_composable_from_rules(workspace: Path, composable_id: str, service_ids: list[str], rules: dict[str, Any]) -> str:
    imports = "\n".join(
        f'import {service_id} from "../services/{service_id.lower()}";'
        for service_id in service_ids
    )
    map_entries = "\n".join(f"    {service_id}: {service_id}," for service_id in service_ids)
    alias_entries = "\n".join(f"    {service_id}: services.{service_id}," for service_id in service_ids)
    specialized = render_composable_from_rules(
        workspace=workspace,
        composable_id=composable_id,
        replacements={
            "{{IMPORTS}}": imports,
            "{{SERVICE_MAP_ENTRIES}}": map_entries,
            "{{SERVICE_ALIAS_ENTRIES}}": alias_entries,
        },
        rules=rules,
    )
    if specialized:
        return specialized
    return _render_runtime_services_composable(composable_id, service_ids)


def _render_dialog_state_composable(composable_name: str, dialog_names: list[str]) -> str:
    entries = "\n".join(f'  {name}: false,' for name in dialog_names)
    keys = ", ".join(f'"{name}"' for name in dialog_names)
    return f"""import {{ reactive }} from "vue";

const state = reactive({{
{entries}
}});

export function {composable_name}() {{
  const dialogKeys = [{keys}];

  function openDialog(name: string) {{
    if (name in state) {{
      state[name as keyof typeof state] = true;
    }}
  }}

  function closeDialog(name: string) {{
    if (name in state) {{
      state[name as keyof typeof state] = false;
    }}
  }}

  function toggleDialog(name: string, value?: boolean) {{
    if (name in state) {{
      state[name as keyof typeof state] = typeof value === "boolean" ? value : !state[name as keyof typeof state];
    }}
  }}

  function closeAllDialogs() {{
    for (const key of dialogKeys) {{
      state[key as keyof typeof state] = false;
    }}
  }}

  return {{
    state,
    dialogKeys,
    openDialog,
    closeDialog,
    toggleDialog,
    closeAllDialogs,
  }};
}}

export default {composable_name};
"""


def _render_dialog_state_composable_from_rules(workspace: Path, composable_id: str, dialog_names: list[str], rules: dict[str, Any]) -> str:
    specialized = render_composable_from_rules(
        workspace=workspace,
        composable_id=composable_id,
        replacements={
            "{{DIALOG_STATE_ENTRIES}}": "\n".join(f"  {name}: false," for name in dialog_names),
            "{{DIALOG_KEY_ENTRIES}}": ", ".join(f'"{name}"' for name in dialog_names),
        },
        rules=rules,
    )
    if specialized:
        return specialized
    return _render_dialog_state_composable(composable_id, dialog_names)


def _render_generic_composable(composable_name: str) -> str:
    return f"""export function {composable_name}() {{
  return {{}};
}}

export default {composable_name};
"""


def _render_generic_view_template(imports: str, title: str, dialog_buttons: str, dialog_usages: str, service_cards: str) -> str:
    return f"""<script setup lang="ts">
import {{ computed }} from "vue";
{imports}

const authStore = useAuthStore();
const {{ state: dialogState, openDialog, closeDialog }} = useDialogState();
const {{ serviceList }} = useRuntimeServices();
const titleText = computed(() => "{title}");
const serviceCount = computed(() => serviceList.length);
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <p class="eyebrow">RestoreX Generic Source Reconstruction</p>
      <h1>{{{{ titleText }}}}</h1>
      <p class="subtitle">This view was generated from runtime analysis rules when no project template was provided.</p>
    </section>
    <section class="panel">
      <h2>Recovered Dialogs</h2>
      <div class="actions">
{dialog_buttons}
      </div>
    </section>
    <section class="panel">
      <h2>Recovered Services</h2>
      <p class="subtitle">Recovered service facade count: {{{{ serviceCount }}}}</p>
      <ul>
{service_cards}
      </ul>
    </section>
{dialog_usages}
  </main>
</template>

<style scoped>
.app-shell {{
  min-height: 100vh;
  padding: 32px;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  color: #0f172a;
  font-family: "Helvetica Neue", "PingFang SC", sans-serif;
}}
.hero {{
  margin-bottom: 24px;
}}
.eyebrow {{
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
  color: #64748b;
}}
.subtitle {{
  max-width: 720px;
  line-height: 1.6;
}}
.panel {{
  margin-top: 20px;
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
}}
.actions {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}}
.action {{
  border: 0;
  border-radius: 999px;
  padding: 10px 16px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
}}
</style>
"""


def _render_app_content_vue(
    workspace: Path,
    dialog_names: list[str],
    service_items: list[dict[str, Any]],
    composable_items: list[dict[str, Any]],
    view_model: dict[str, Any],
    announcement_model: dict[str, Any],
    rules: dict[str, Any],
) -> str:
    main_rule = dict(rules.get("main_view_rule", {}))
    primary_store_id = str(rules.get("primary_store_id", "storeState")).strip() or "storeState"
    primary_store_export = f"use{_safe_name(primary_store_id, 'Store')[:1].upper()}{_safe_name(primary_store_id, 'Store')[1:]}"
    runtime_service_bindings = {
        str(k): str(v)
        for k, v in dict(main_rule.get("runtime_service_bindings", {})).items()
        if str(k).strip() and str(v).strip()
    }
    runtime_services_composable = next(
        (
            _safe_name(str(item.get("name", "")), "useRuntimeServices")
            for item in composable_items
            if str(item.get("kind", "")).strip() == "runtime_services"
        ),
        "useRuntimeServices",
    )
    dialog_state_composable = next(
        (
            _safe_name(str(item.get("name", "")), "useDialogState")
            for item in composable_items
            if str(item.get("kind", "")).strip() == "dialog_state"
        ),
        "useDialogState",
    )
    default_service_name = str(service_items[0].get("name", "runtimeService")).strip() if service_items else "runtimeService"
    runtime_binding_values = [value for key, value in runtime_service_bindings.items() if key != "auth"]
    runtime_service_destructure = ", ".join(["auth", *runtime_binding_values]).strip(", ") if runtime_service_bindings else default_service_name
    store_contract = dict(main_rule.get("primary_store_contract", {}))
    imports = "\n".join(
        [f'import {name} from "../components/{name}.vue";' for name in dialog_names]
        + [f'import {dialog_state_composable} from "../composables/{dialog_state_composable}";']
        + [f'import {runtime_services_composable} from "../composables/{runtime_services_composable}";']
        + [f'import {primary_store_export} from "../stores/{_safe_lower_file_stem(primary_store_id, "store")}";']
    )
    editor_options = list(view_model.get("editor_options", []))
    action_labels = list(view_model.get("action_labels", []))
    title = str(view_model.get("title", "App Content"))
    title_suffix = str(view_model.get("title_suffix", title))
    tutorial_hints = list(view_model.get("tutorial_hints", []))
    announcement_title = str(announcement_model.get("title", view_model.get("announcement_title", "Announcement")))
    proxy_toggle_label = str(view_model.get("proxy_toggle_label", "Runtime Toggle"))
    codex_service_label = str(view_model.get("codex_service_label", "Runtime Service"))
    purchase_entry_label = str(view_model.get("purchase_entry_label", "Open Flow"))
    editor_colors = dict(view_model.get("editor_colors", {}))
    dialog_buttons = "\n".join(
        f'      <button class="action" @click=\'openDialog("{name}")\'>{_component_display_title(name, rules)}</button>'
        for name in dialog_names
    )
    main_action_buttons = "\n".join(
        f'      <button class="action secondary" @click="runMainAction({idx})">{label}</button>'
        for idx, label in enumerate(action_labels)
    )
    editor_buttons = "\n".join(
        f'        <button class="chip" :class="{{ active: editorName === \'{name}\' }}" :style="editorButtonStyle(\'{name}\')" @click="selectEditor(\'{name}\')">{name}</button>'
        for name in editor_options
    )
    dialog_usages = "\n".join(
        f'  <{name} :visible="dialogState.{name}" @close=\'closeDialog("{name}")\' />' for name in dialog_names
    )
    service_cards = "\n".join(
        f'      <li><code>{str(item.get("service_key", ""))}</code> -> <strong>{str(item.get("name", ""))}</strong></li>'
        for item in service_items
    )
    tutorial_hints_html = "\n".join(f"        <li>{hint}</li>" for hint in tutorial_hints[:4]) or "        <li>自动提取到的引导提示将在这里展示。</li>"
    template = _read_project_template(workspace, str(view_model.get("template_path", "")))
    if not template:
        return _render_generic_view_template(imports, title, dialog_buttons, dialog_usages, service_cards)
    return _fill_template(
        template,
        {
            "{{IMPORTS}}": imports,
            "{{PRIMARY_STORE_EXPORT}}": primary_store_export,
            "{{DIALOG_STATE_COMPOSABLE}}": dialog_state_composable,
            "{{RUNTIME_SERVICES_COMPOSABLE}}": runtime_services_composable,
            "{{RUNTIME_SERVICE_DESTRUCTURE}}": runtime_service_destructure,
            "{{STORE_INITIALIZE_METHOD}}": str(store_contract.get("initialize_method", "initialize")),
            "{{STORE_REFRESH_METHOD}}": str(store_contract.get("refresh_method", "refresh")),
            "{{STORE_QUOTA_METHOD}}": str(store_contract.get("quota_method", "getQuota")),
            "{{STORE_DISABLE_PROXY_METHOD}}": str(store_contract.get("disable_proxy_method", "disableProxy")),
            "{{STORE_ANNOUNCEMENT_FIELD}}": str(store_contract.get("announcement_field", "announcement")),
            "{{STORE_ANNOUNCEMENT_DATE_FIELD}}": str(store_contract.get("announcement_date_field", "announcementDate")),
            "{{STORE_PROXY_ENABLED_FIELD}}": str(store_contract.get("proxy_enabled_field", "accelerateEnabled")),
            "{{TUTORIAL_DIALOG_ID}}": str(main_rule.get("tutorial_dialog_id", "")),
            "{{PURCHASE_DIALOG_ID}}": str(main_rule.get("purchase_dialog_id", "")),
            "{{PROXY_DIALOG_ID}}": str(main_rule.get("proxy_dialog_id", "")),
            "{{TUTORIAL_OPEN_LABEL}}": str(main_rule.get("tutorial_open_label", "Open Tutorial")),
            "{{PURCHASE_OPEN_LABEL}}": str(main_rule.get("purchase_open_label", "Open Related Flow")),
            "{{PROXY_SETTINGS_LABEL}}": str(main_rule.get("proxy_settings_label", "Open Settings")),
            "{{DEFAULT_EDITOR}}": editor_options[0] if editor_options else "Primary",
            "{{EDITOR_OPTIONS_LITERAL}}": repr(editor_options),
            "{{EDITOR_COLORS_LITERAL}}": repr(editor_colors),
            "{{ANNOUNCEMENT_ENABLED}}": str(bool(announcement_model.get("enabled"))).lower(),
            "{{PURCHASE_URL}}": str(view_model.get("purchase_url", "")),
            "{{TITLE_SUFFIX}}": title_suffix,
            "{{EDITOR_BUTTONS}}": editor_buttons,
            "{{MAIN_ACTION_BUTTONS}}": main_action_buttons,
            "{{PURCHASE_ENTRY_LABEL}}": purchase_entry_label,
            "{{HAS_PROXY_TOGGLE}}": str(bool(view_model.get("has_proxy_toggle"))).lower(),
            "{{PROXY_TOGGLE_LABEL}}": proxy_toggle_label,
            "{{CODEX_SERVICE_LABEL}}": codex_service_label,
            "{{ANNOUNCEMENT_TITLE}}": announcement_title,
            "{{DIALOG_BUTTONS}}": dialog_buttons,
            "{{SERVICE_CARDS}}": service_cards,
            "{{TUTORIAL_HINT_ITEMS}}": tutorial_hints_html,
            "{{DIALOG_USAGES}}": dialog_usages,
            "{{INSTALL_TARGET_DIALOG}}": str(view_model.get("install_target_dialog", "")),
        },
    )


def cmd_build_source_project(workspace: Path, run_id: str) -> None:
    paths, root = _source_root(workspace, run_id)
    rules = _load_source_reconstruction_rules(workspace, run_id)
    graph = _load_json(root / "module_graph.json", {"nodes": []})
    components = _load_json(root / "component_candidates.json", {"items": []}).get("items", [])
    services = _load_json(root / "service_candidates.json", {"items": []}).get("items", [])
    stores = _load_json(root / "store_candidates.json", {"items": []}).get("items", [])
    composables = _load_json(root / "composable_candidates.json", {"items": []}).get("items", [])
    bootstrap = _load_json(root / "bootstrap_candidates.json", {"items": []}).get("items", [])
    source_project = paths.base / "reconstructed_project_source"
    if source_project.exists():
        shutil.rmtree(source_project)
    for sub in (
        source_project / "src" / "components",
        source_project / "src" / "views",
        source_project / "src" / "services",
        source_project / "src" / "stores",
        source_project / "src" / "composables",
        source_project / "src" / "utils",
        source_project / "src" / "meta",
        source_project / "src" / "styles",
        source_project / "src" / "restored" / "bundle",
    ):
        sub.mkdir(parents=True, exist_ok=True)

    readable = paths.restore_v1 / "readable"
    if readable.is_dir():
        shutil.copytree(readable, source_project / "src" / "restored" / "bundle", dirs_exist_ok=True)

    package_json = {
        "name": f"restorex-source-{run_id}",
        "private": True,
        "version": "0.0.1",
        "type": "module",
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
            "typecheck": "vue-tsc --noEmit",
        },
        "dependencies": {"vue": "^3.5.0"},
        "devDependencies": {
            "@vitejs/plugin-vue": "^6.0.0",
            "typescript": "^5.9.0",
            "vite": "^7.0.0",
            "vue-tsc": "^3.0.0",
        },
    }
    write_json(source_project / "package.json", package_json)
    write_text(
        source_project / "tsconfig.json",
        """{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "types": ["vite/client"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
""",
    )
    write_text(
        source_project / "src" / "env.d.ts",
        """/// <reference types="vite/client" />
""",
    )
    write_text(
        source_project / "vite.config.ts",
        """import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
});
""",
    )
    write_text(
        source_project / "index.html",
        """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RestoreX Source Project</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
""",
    )
    write_text(
        source_project / "src" / "main.ts",
        """import { createApp } from "vue";
import App from "./App.vue";
import "./styles/base.css";

createApp(App).mount("#app");
""",
    )
    app_root = next((x for x in bootstrap if str(x.get("kind", "")).strip() == "app_root"), {})
    if not app_root:
        app_root = next((x for x in bootstrap if str(x.get("id", "")) == "AppRoot"), {})
    root_view_name = str((app_root.get("depends_on", []) or [str(rules.get("bootstrap_view_id", "")) or "RootView"])[0] or "RootView")
    write_text(
        source_project / "src" / "App.vue",
        f"""<script setup lang="ts">
import {root_view_name} from "./views/{root_view_name}.vue";
</script>

<template>
  <{root_view_name} />
</template>
""",
    )
    write_text(
        source_project / "src" / "styles" / "base.css",
        """:root {
  color: #1d2433;
  background: #ffffff;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

.restorex-dialog-shell {
  position: fixed;
  inset: 12vh 12vw auto;
  z-index: 20;
  padding: 20px;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.18);
}

.restorex-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.restorex-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.restorex-panel {
  margin-top: 16px;
  padding: 16px;
  border-radius: 14px;
  background: #f8fafc;
}

.restorex-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.restorex-block {
  padding: 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.restorex-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.7;
}

.restorex-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.restorex-tags code {
  padding: 4px 8px;
  border-radius: 999px;
  background: #e2e8f0;
}

.restorex-form {
  display: grid;
  gap: 12px;
}

.restorex-form-field {
  display: grid;
  gap: 6px;
}

.restorex-form-field span {
  font-size: 13px;
  color: #475569;
}

.restorex-form-field input {
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 10px 12px;
  font: inherit;
}

.restorex-action,
.restorex-close {
  border: 0;
  border-radius: 999px;
  padding: 8px 14px;
  cursor: pointer;
}

.restorex-action {
  background: #0f766e;
  color: #fff;
}

.restorex-close {
  background: #e5e7eb;
}
""",
    )
    write_text(
        source_project / "src" / "utils" / "runtime.ts",
        """export async function invokeRuntime(command: string, payload?: unknown) {
  console.info("[restorex-runtime]", command, payload ?? null);
  return {
    ok: true,
    command,
    payload: payload ?? null,
    mode: "source_project_stub",
  };
}
""",
    )

    logger_item = next((item for item in services if str(item.get("service_key", "")) == "logger"), None)
    if logger_item and str(logger_item.get("class_source", "")).strip():
        write_text(source_project / "src" / "utils" / "logger.ts", _render_logger_module(str(logger_item.get("class_source", ""))))
    else:
        write_text(
            source_project / "src" / "utils" / "logger.ts",
            """export class AppLogger {
  debug(tag: string, message: string, ...args: unknown[]) {
    console.debug(tag, message, ...args);
  }
  info(tag: string, message: string, ...args: unknown[]) {
    console.info(tag, message, ...args);
  }
  warn(tag: string, message: string, ...args: unknown[]) {
    console.warn(tag, message, ...args);
  }
  error(tag: string, message: string, ...args: unknown[]) {
    console.error(tag, message, ...args);
  }
}

export const logger = new AppLogger();
export default logger;
""",
        )

    dialog_names: list[str] = []
    for item in components:
        name = _safe_name(str(item.get("name", "")), "RecoveredComponent")
        output_path = str(item.get("output_path", ""))
        if output_path.endswith(".vue") and "/components/" in output_path:
            dialog_names.append(name)
            write_text(source_project / output_path, _render_component_module(workspace, item))

    for item in stores:
        output_path = str(item.get("output_path", "")).strip()
        if output_path:
            write_text(source_project / output_path, _render_store_module(workspace, item, rules))

    service_ids: list[str] = []
    for item in services:
        if str(item.get("module_type", "")) != "service":
            continue
        service_key = str(item.get("service_key", "")).strip()
        name = _safe_name(str(item.get("name", "")), "Service")
        service_ids.append(name)
        write_text(source_project / f"src/services/{service_key.lower()}.ts", _render_service_module(item))

    for item in composables:
        composable_id = _safe_name(str(item.get("name", "")), "RecoveredComposable")
        output_path = str(item.get("output_path", "")).strip()
        if not output_path:
            continue
        kind = str(item.get("kind", "generic_composable")).strip()
        if kind == "runtime_services":
            content = _render_runtime_services_composable_from_rules(workspace, composable_id, service_ids, rules)
        elif kind == "dialog_state":
            content = _render_dialog_state_composable_from_rules(workspace, composable_id, dialog_names, rules)
        else:
            content = _render_generic_composable(composable_id)
        write_text(source_project / output_path, content)
    view_model = dict(app_root.get("view_model", {})) if isinstance(app_root.get("view_model", {}), dict) else {}
    announcement_model = dict(app_root.get("announcement_model", {})) if isinstance(app_root.get("announcement_model", {}), dict) else {}
    write_text(
        source_project / "src" / "views" / f"{root_view_name}.vue",
        _render_app_content_vue(
            workspace,
            dialog_names,
            [x for x in services if str(x.get("module_type", "")) == "service"],
            composables,
            view_model,
            announcement_model,
            rules,
        ),
    )

    reconstruction_report = {
        "run_id": run_id,
        "source_entry_mode": "source_modules",
        "generated_at": "auto",
        "module_graph": graph,
        "component_count": len(components),
        "dialog_component_count": len(dialog_names),
        "service_count": len([x for x in services if str(x.get("module_type", "")) == "service"]),
        "stores_count": len(stores),
        "source_bundle_shell_remaining": 0,
    }
    write_json(source_project / "src" / "meta" / "reconstruction_report.json", reconstruction_report)
