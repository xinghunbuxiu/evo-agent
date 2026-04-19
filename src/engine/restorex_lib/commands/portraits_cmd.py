from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import collect_files, infer_entity_line_range, read_text, rel, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths
from restorex_lib.config_rules import load_json_if_exists


DEFAULT_PORTRAIT_RULES: dict[str, Any] = {
    "js_domain_keywords": [
        "token",
        "session",
        "config",
        "request",
        "response",
        "endpoint",
        "credential",
        "account",
        "profile",
        "state",
    ],
    "js_domain_regex": [
        r"\b(api|client|service|store|manager)\b",
    ],
}


def _load_portrait_rules(workspace: Path) -> dict[str, Any]:
    obj = load_json_if_exists(workspace / "cache" / "remote" / "portrait_rules.json")
    out = dict(DEFAULT_PORTRAIT_RULES)
    for k in ("js_domain_keywords", "js_domain_regex"):
        if k in obj and isinstance(obj.get(k), list):
            out[k] = obj[k]
    return out


def classify_restore_priority(origin_label: str, framework_hints: list[str], build_hints: list[str]) -> str:
    if origin_label == "app_business":
        return "high"
    if origin_label == "framework_compiled":
        return "medium"
    if origin_label in {"vendor_library", "bundler_runtime"}:
        return "low"
    # unknown 时结合特征兜底：带 UI/业务特征倾向中优先级。
    if any(h in {"ui_component", "vue_component_pattern", "bridge_invocation"} for h in framework_hints + build_hints):
        return "medium"
    return "low"


# FLOW_TAG_PATTERNS 从 spec/semantic_rules.json 加载，不在引擎代码里硬编码。
# 引擎启动时通过 _load_flow_tag_patterns(workspace) 获取，支持 project_hints.json 扩展。
_FLOW_TAG_PATTERNS_CACHE: dict[str, list[str]] | None = None


def _load_flow_tag_patterns(workspace: Path) -> dict[str, list[str]]:
    """从 semantic_rules.json 加载 flow_tag_patterns，并合并 project_hints.json 里的扩展词。"""
    global _FLOW_TAG_PATTERNS_CACHE
    if _FLOW_TAG_PATTERNS_CACHE is not None:
        return _FLOW_TAG_PATTERNS_CACHE
    sem = load_json_if_exists(workspace / "cache" / "project" / "semantic_rules.json")
    patterns: dict[str, list[str]] = {}
    raw = sem.get("flow_tag_patterns", {})
    if isinstance(raw, dict):
        for tag, pats in raw.items():
            if isinstance(pats, list):
                patterns[str(tag)] = [str(p) for p in pats]
    # 合并 project_hints.json 里的项目特定扩展词
    hints = load_json_if_exists(workspace / "cache" / "project" / "project_hints.json")
    extra = hints.get("flow_tag_extra_patterns", {})
    if isinstance(extra, dict):
        for tag, pats in extra.items():
            if isinstance(pats, list):
                existing = patterns.setdefault(str(tag), [])
                for p in pats:
                    if str(p) not in existing:
                        existing.append(str(p))
    _FLOW_TAG_PATTERNS_CACHE = patterns
    return patterns
def _infer_flow_tag_ranking(method_name: str, body: str) -> list[tuple[str, float]]:
    lower_name = str(method_name).lower()
    lower_body = str(body).lower()
    score_map: dict[str, float] = {}
    _patterns = _FLOW_TAG_PATTERNS_CACHE or {}
    for tag, pats in _patterns.items():
        name_hit = any(p.lower() in lower_name for p in pats)
        body_hit = any(p.lower() in lower_body for p in pats)
        if name_hit:
            score_map[tag] = score_map.get(tag, 0.0) + 3.0
        if body_hit:
            score_map[tag] = score_map.get(tag, 0.0) + 1.0
    # command literals: "create_payment_order" / "open_url" / "login_with_card_key" ...
    for m in re.finditer(r'"([a-z][a-z0-9_]{4,})"', body):
        token = str(m.group(1)).lower()
        if "login" in token:
            score_map["login"] = score_map.get("login", 0.0) + 2.5
        if "logout" in token:
            score_map["logout"] = score_map.get("logout", 0.0) + 2.5
        if "open" in token:
            score_map["open"] = score_map.get("open", 0.0) + 2.0
        if ("create" in token or "submit" in token):
            score_map["submit"] = score_map.get("submit", 0.0) + 2.0
        if "start" in token:
            score_map["start"] = score_map.get("start", 0.0) + 2.0
        if "stop" in token:
            score_map["stop"] = score_map.get("stop", 0.0) + 2.0
        if "cleanup" in token or "clear" in token or "reset" in token:
            score_map["cleanup"] = score_map.get("cleanup", 0.0) + 2.0
        if "install" in token and "uninstall" not in token:
            score_map["install"] = score_map.get("install", 0.0) + 2.0
        if "uninstall" in token:
            score_map["uninstall"] = score_map.get("uninstall", 0.0) + 2.0
        if "cancel" in token:
            score_map["cancel"] = score_map.get("cancel", 0.0) + 2.0
        if "retry" in token:
            score_map["retry"] = score_map.get("retry", 0.0) + 2.0
    order = [
        "init",
        "login",
        "logout",
        "cleanup",
        "install",
        "uninstall",
        "open",
        "start",
        "stop",
        "submit",
        "confirm",
        "cancel",
        "retry",
    ]
    ranked = sorted(
        [(tag, sc) for tag, sc in score_map.items() if sc > 0],
        key=lambda kv: (-kv[1], order.index(kv[0]) if kv[0] in order else 999),
    )
    return ranked


def _infer_flow_tags(method_name: str, body: str) -> list[str]:
    return [tag for tag, _ in _infer_flow_tag_ranking(method_name, body)]


def _extract_command_literals(body: str) -> list[str]:
    """提取函数体内可能的命令字面量（snake_case），用于后续证据命名增强。"""
    hits: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"""['"]([a-z][a-z0-9_]{3,80})['"]""", str(body)):
        token = str(m.group(1)).strip().lower()
        if "_" not in token:
            continue
        if token in seen:
            continue
        seen.add(token)
        hits.append(token)
        if len(hits) >= 12:
            break
    return hits


def _infer_dialog_param_candidates(raw_params: list[str], body: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    lower_body = str(body).lower()
    for raw in raw_params:
        short = str(raw).strip().lstrip(".")
        if not re.fullmatch(r"[A-Za-z_$]\w{0,2}", short):
            continue
        if "update:visible" in lower_body or "visible" in lower_body:
            out.append({"param": raw, "candidate": "visible", "confidence": "high", "source_rule": "dialog_visible_token"})
            continue
        if "loading" in lower_body or "duration" in lower_body:
            out.append({"param": raw, "candidate": "loading", "confidence": "medium", "source_rule": "dialog_loading_token"})
            continue
        if "error" in lower_body or ".error(" in lower_body:
            out.append({"param": raw, "candidate": "error", "confidence": "medium", "source_rule": "dialog_error_token"})
            continue
        if "message" in lower_body or "safemessage" in lower_body:
            out.append({"param": raw, "candidate": "message", "confidence": "medium", "source_rule": "dialog_message_token"})
            continue
        if "type" in lower_body:
            out.append({"param": raw, "candidate": "type", "confidence": "medium", "source_rule": "dialog_type_token"})
            continue
    return out


def cmd_build_file_portraits(workspace: Path, run_id: str) -> None:
    """文件级画像：每个输入文件一条，可用于后续自动还原排序与策略分流。"""
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    origin_path = paths.analysis / "build_origin_report.json"
    structure_path = paths.analysis / "structure_scan.json"
    if not origin_path.is_file() or not structure_path.is_file():
        raise SystemExit("E_RUNTIME: run infer-build-origin and scan-structure first")

    origin_obj = json.loads(read_text(origin_path))
    structure_obj = json.loads(read_text(structure_path))
    portrait_rules = _load_portrait_rules(workspace)
    domain_keywords = [str(x) for x in portrait_rules.get("js_domain_keywords", []) if str(x).strip()]
    domain_regex = [str(x) for x in portrait_rules.get("js_domain_regex", []) if str(x).strip()]
    origin_by_file = {str(i.get("file", "")): i for i in origin_obj.get("items", [])}
    js_import_map = {str(i.get("file", "")): i.get("imports", []) for i in structure_obj.get("js_files", [])}
    html_entry_set = {str(i.get("file", "")) for i in structure_obj.get("html_files", [])}

    # 文件画像是后续所有阶段（chains/evidence/script-plan）的公共输入。
    portrait_items: list[dict[str, Any]] = []
    out_dir = paths.portraits / "file_portraits"
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in collect_files(source_root):
        rel_path = rel(f, source_root)
        text = read_text(f)
        ext = f.suffix.lower()
        origin_item = origin_by_file.get(rel_path, {})
        origin_label = str(origin_item.get("origin_label", "unknown"))
        origin_conf = str(origin_item.get("confidence", "low"))

        framework_hints: list[str] = []
        build_hints: list[str] = []
        ui_hints: list[str] = []
        domain_hints: list[str] = []

        if ext == ".js":
            if re.search(r"\bcreateApp\(", text):
                framework_hints.append("vue_create_app")
            if re.search(r"\bdefineComponent\(", text):
                framework_hints.append("vue_component_pattern")
            if "naive-ui" in rel_path.lower() or "naive-ui" in text.lower():
                framework_hints.append("naive_ui_related")
            if "__vite__mapDeps" in text or "modulepreload" in text:
                build_hints.append("vite_bundler_runtime")
            if re.search(r"plugin:[a-zA-Z0-9_-]+\|[a-zA-Z0-9_]+", text) or "tauri://" in text:
                build_hints.append("bridge_invocation")
            if re.search(r"[A-Za-z_$]\w{0,2}\s*=", text):
                build_hints.append("minified_short_symbol")
            if "onClick" in text or "onChange" in text or "addEventListener" in text:
                ui_hints.append("event_handler")
            if re.search(r"[\u4e00-\u9fff]{2,}", text):
                ui_hints.append("contains_zh_text")
            lower_text = text.lower()
            if domain_keywords and any(k.lower() in lower_text for k in domain_keywords):
                domain_hints.append("domain_keyword_detected")
            if domain_regex and any(re.search(p, lower_text) for p in domain_regex):
                domain_hints.append("domain_regex_detected")
        elif ext == ".css":
            if re.search(r"\.[A-Za-z_-][A-Za-z0-9_-]{2,}\s*[{,]", text):
                ui_hints.append("style_class_rules")
            if re.search(r"--[A-Za-z0-9_-]+\s*:", text):
                build_hints.append("css_var_tokens")
            if re.search(r"@media\s*\(", text):
                ui_hints.append("responsive_layout")
        elif ext == ".html":
            if rel_path in html_entry_set:
                build_hints.append("entry_html")
            if "<script" in text and "type=\"module\"" in text:
                build_hints.append("esm_entry")
            if re.search(r"id=[\"']app[\"']", text):
                framework_hints.append("spa_mount_point")
        elif ext == ".svg":
            ui_hints.append("vector_asset")

        imports = js_import_map.get(rel_path, []) if ext == ".js" else []
        if imports:
            build_hints.append("module_imports")

        restore_priority = classify_restore_priority(origin_label, framework_hints, build_hints)

        item = {
            "file": rel_path,
            "ext": ext,
            "size": len(text),
            "origin_label": origin_label,
            "origin_confidence": origin_conf,
            "framework_hints": sorted(set(framework_hints)),
            "build_hints": sorted(set(build_hints)),
            "ui_hints": sorted(set(ui_hints)),
            "domain_hints": sorted(set(domain_hints)),
            "imports_count": len(imports),
            "is_entry_html": rel_path in html_entry_set,
            "restore_priority": restore_priority,
        }
        portrait_items.append(item)

        # 文件级独立画像，方便后续“逐文件还原”。
        file_md = [
            f"# File Portrait: {rel_path}",
            "",
            f"- ext: `{ext}`",
            f"- size: `{len(text)}`",
            f"- origin: `{origin_label}` (confidence={origin_conf})",
            f"- restore_priority: `{restore_priority}`",
            f"- imports_count: `{len(imports)}`",
            f"- is_entry_html: `{rel_path in html_entry_set}`",
            "",
            "## Framework Hints",
        ]
        if item["framework_hints"]:
            file_md.extend([f"- {x}" for x in item["framework_hints"]])
        else:
            file_md.append("- none")
        file_md.extend(["", "## Build Hints"])
        if item["build_hints"]:
            file_md.extend([f"- {x}" for x in item["build_hints"]])
        else:
            file_md.append("- none")
        file_md.extend(["", "## UI Hints"])
        if item["ui_hints"]:
            file_md.extend([f"- {x}" for x in item["ui_hints"]])
        else:
            file_md.append("- none")
        file_md.extend(["", "## Domain Hints"])
        if item["domain_hints"]:
            file_md.extend([f"- {x}" for x in item["domain_hints"]])
        else:
            file_md.append("- none")
        safe_name = rel_path.replace("/", "__")
        write_text(out_dir / f"{safe_name}.md", "\n".join(file_md))

    portrait_items.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x["restore_priority"], 9), x["file"]))
    write_json(
        paths.portraits / "file_portraits.json",
        {
            "run_id": run_id,
            "count": len(portrait_items),
            "items": portrait_items,
        },
    )

    by_priority = {"high": 0, "medium": 0, "low": 0}
    for it in portrait_items:
        by_priority[it["restore_priority"]] = by_priority.get(it["restore_priority"], 0) + 1
    md = [
        "# File Portraits",
        "",
        f"- run_id: `{run_id}`",
        f"- file_count: `{len(portrait_items)}`",
        f"- high_priority: `{by_priority.get('high', 0)}`",
        f"- medium_priority: `{by_priority.get('medium', 0)}`",
        f"- low_priority: `{by_priority.get('low', 0)}`",
        "",
        "## Top High Priority Files",
    ]
    tops = [x for x in portrait_items if x["restore_priority"] == "high"][:30]
    if tops:
        for it in tops:
            md.append(f"- {it['file']} (origin={it['origin_label']}, hints={','.join(it['domain_hints'] + it['ui_hints']) or 'none'})")
    else:
        md.append("- none")
    write_text(paths.portraits / "file_portraits.md", "\n".join(md))


def cmd_build_class_portraits(workspace: Path, run_id: str) -> None:
    """实体级画像：类/组件/函数（每个 JS 文件至少一个实体画像）。"""
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    file_portrait_path = paths.portraits / "file_portraits.json"
    if not file_portrait_path.is_file():
        raise SystemExit("E_RUNTIME: run build-file-portraits first")
    fp_obj = json.loads(read_text(file_portrait_path))
    fp_by_file = {str(i.get("file", "")): i for i in fp_obj.get("items", [])}

    out_dir = paths.portraits / "class_portraits"
    out_dir.mkdir(parents=True, exist_ok=True)

    entity_items: list[dict[str, Any]] = []
    for f in collect_files(source_root, {".js"}):
        rel_path = rel(f, source_root)
        txt = read_text(f)
        fp = fp_by_file.get(rel_path, {})
        fp_origin = str(fp.get("origin_label", "unknown"))
        entities: list[dict[str, Any]] = []

        for m in re.finditer(r"\bclass\s+([A-Za-z_$][\w$]*)\b", txt):
            name = m.group(1)
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            entities.append({"entity_type": "class", "entity_name": name, "line": line_start, "line_end": line_end})

        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*defineComponent\(", txt):
            name = m.group(1)
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            entities.append({"entity_type": "component", "entity_name": name, "line": line_start, "line_end": line_end})

        for m in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", txt):
            name = m.group(1)
            # 函数实体只在业务文件采集，并过滤短名噪声，避免 minified 产物爆量。
            if fp_origin != "app_business":
                continue
            if len(name) <= 2:
                continue
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            entities.append({"entity_type": "function", "entity_name": name, "line": line_start, "line_end": line_end})
        # 兼容编译产物常见写法：const x = (...) => {} / const x = function(...) {}
        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", txt):
            if fp_origin != "app_business":
                continue
            name = m.group(1)
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            entities.append({"entity_type": "function", "entity_name": name, "line": line_start, "line_end": line_end})
        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function\s*\(", txt):
            if fp_origin != "app_business":
                continue
            name = m.group(1)
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            entities.append({"entity_type": "function", "entity_name": name, "line": line_start, "line_end": line_end})

        # 兜底：即使没有可识别实体，也要产出 module 级实体，保证可追踪性。
        if not entities:
            entities.append({"entity_type": "module", "entity_name": "__module__", "line": 1, "line_end": max(1, txt.count('\n') + 1)})

        # 去重（同类型同名按最早行保留）
        uniq: dict[tuple[str, str], dict[str, Any]] = {}
        for e in entities:
            k = (str(e["entity_type"]), str(e["entity_name"]))
            if k not in uniq or int(e["line"]) < int(uniq[k]["line"]):
                uniq[k] = e
        entities = sorted(uniq.values(), key=lambda x: (int(x["line"]), str(x["entity_type"]), str(x["entity_name"])))
        max_fn = 80
        kept: list[dict[str, Any]] = []
        fn_count = 0
        for e in entities:
            if e["entity_type"] == "function":
                fn_count += 1
                if fn_count > max_fn:
                    continue
            kept.append(e)
        entities = kept

        for e in entities:
            item = {
                "file": rel_path,
                "entity_type": e["entity_type"],
                "entity_name": e["entity_name"],
                "line": e["line"],
                "line_end": int(e.get("line_end", e["line"])),
                "origin_label": fp.get("origin_label", "unknown"),
                "restore_priority": fp.get("restore_priority", "low"),
                "framework_hints": fp.get("framework_hints", []),
                "build_hints": fp.get("build_hints", []),
            }
            entity_items.append(item)

        file_md = [
            f"# Class Portrait: {rel_path}",
            "",
            f"- origin: `{fp.get('origin_label', 'unknown')}`",
            f"- restore_priority: `{fp.get('restore_priority', 'low')}`",
            "",
            "## Entities",
        ]
        for e in entities:
            file_md.append(f"- line {e['line']}-{int(e.get('line_end', e['line']))}: {e['entity_type']} `{e['entity_name']}`")
        safe_name = rel_path.replace("/", "__")
        write_text(out_dir / f"{safe_name}.md", "\n".join(file_md))

    write_json(
        paths.portraits / "class_portraits.json",
        {
            "run_id": run_id,
            "count": len(entity_items),
            "items": entity_items,
        },
    )
    by_type: dict[str, int] = {}
    for it in entity_items:
        by_type[it["entity_type"]] = by_type.get(it["entity_type"], 0) + 1
    md = [
        "# Class Portraits",
        "",
        f"- run_id: `{run_id}`",
        f"- entity_count: `{len(entity_items)}`",
    ]
    for k in sorted(by_type):
        md.append(f"- {k}: `{by_type[k]}`")
    write_text(paths.portraits / "class_portraits.md", "\n".join(md))


def cmd_build_constant_portraits(workspace: Path, run_id: str) -> None:
    """常量画像：提取常量声明与枚举风格对象，供后续可读化改名/职责判断使用。"""
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    file_portrait_path = paths.portraits / "file_portraits.json"
    if not file_portrait_path.is_file():
        raise SystemExit("E_RUNTIME: run build-file-portraits first")
    fp_obj = json.loads(read_text(file_portrait_path))
    fp_by_file = {str(i.get("file", "")): i for i in fp_obj.get("items", [])}

    out_dir = paths.portraits / "constant_portraits"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _infer_semantic_bucket(it: dict[str, Any]) -> str:
        kind = str(it.get("constant_kind", ""))
        keys = {str(x).upper() for x in it.get("enum_keys", []) if str(x).strip()}
        value_head = str(it.get("value_head", ""))
        if {"DEBUG", "INFO", "WARN", "ERROR"}.issubset(keys):
            return "log_level"
        if {"NSIS", "MSI", "DEB", "RPM", "APPIMAGE", "APP"}.issubset(keys):
            return "installer_package_type"
        if "class:" in value_head or "class :" in value_head:
            return "ui_class_anchor"
        if kind in {"enum_object", "enum_iife", "frozen_object"}:
            return "generic_enum"
        if kind == "upper_decl":
            return "generic_constant"
        return "unknown"

    def _constant_confidence(
        *,
        kind: str,
        entity_name: str,
        origin_label: str,
        enum_key_count: int = 0,
        value_head: str = "",
    ) -> tuple[str, list[str], bool]:
        """常量画像置信度评估。

        返回:
        - confidence: high|medium|low
        - tags: 证据标签
        - allow_auto_restore: 是否建议进入自动还原候选
        """
        tags: list[str] = [f"kind:{kind}", f"origin:{origin_label}"]
        single_char = len(entity_name) == 1

        if kind == "enum_object":
            if origin_label in {"bundler_runtime", "vendor_library", "framework_compiled"}:
                tags.append("third_party_or_runtime_enum")
                return ("low", tags, False)
            if enum_key_count >= 3:
                tags.append("enum_keys>=3")
                if origin_label == "app_business":
                    return ("high", tags, True)
                return ("medium", tags, True)
            tags.append("enum_keys<3")
            return ("low", tags, False)

        if kind == "enum_iife":
            if origin_label in {"bundler_runtime", "vendor_library", "framework_compiled"}:
                tags.append("third_party_or_runtime_enum")
                return ("low", tags, False)
            if enum_key_count >= 3:
                tags.append("enum_iife_keys>=3")
                if origin_label in {"app_business", "unknown"}:
                    return ("high", tags, True)
                return ("medium", tags, True)
            tags.append("enum_iife_keys<3")
            return ("low", tags, False)

        if kind == "frozen_object":
            if origin_label in {"bundler_runtime", "vendor_library", "framework_compiled"}:
                tags.append("third_party_or_runtime_enum")
                return ("low", tags, False)
            if enum_key_count >= 3:
                tags.append("frozen_keys>=3")
                return ("medium", tags, True)
            tags.append("frozen_keys<3")
            return ("low", tags, False)

        # upper_decl
        if single_char:
            tags.append("single_char_symbol")
            if value_head.startswith("{") or value_head.startswith("y("):
                tags.append("compiled_temp_pattern")
                return ("low", tags, False)
            return ("low", tags, False)
        if origin_label == "app_business":
            tags.append("business_decl")
            return ("medium", tags, True)
        return ("low", tags, False)

    items: list[dict[str, Any]] = []
    for f in collect_files(source_root, {".js"}):
        rel_path = rel(f, source_root)
        txt = read_text(f)
        fp = fp_by_file.get(rel_path, {})
        file_items: list[dict[str, Any]] = []

        # 1) 直接常量声明：const MAX_RETRY = 3
        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Z][A-Z0-9_]*)\s*=\s*([^;\n]+)", txt):
            name = m.group(1)
            value_head = m.group(2).strip()[:120]
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            file_items.append(
                {
                    "file": rel_path,
                    "entity_type": "constant",
                    "constant_kind": "upper_decl",
                    "entity_name": name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "value_head": value_head,
                    "origin_label": fp.get("origin_label", "unknown"),
                    "restore_priority": fp.get("restore_priority", "low"),
                }
            )

        # 2) 枚举风格对象：const LEVEL = { DEBUG: 1, INFO: 2, ... }
        for m in re.finditer(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\{([\s\S]{0,1200}?)\}\s*;?",
            txt,
        ):
            obj_name = m.group(1)
            body = m.group(2)
            keys = re.findall(r"([A-Z][A-Z0-9_]{2,})\s*:", body)
            if len(keys) < 2:
                continue
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            file_items.append(
                {
                    "file": rel_path,
                    "entity_type": "constant",
                    "constant_kind": "enum_object",
                    "entity_name": obj_name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "enum_keys": sorted(set(keys))[:40],
                    "enum_key_count": len(set(keys)),
                    "origin_label": fp.get("origin_label", "unknown"),
                    "restore_priority": fp.get("restore_priority", "low"),
                }
            )

        # 3) 冻结对象：const x = Object.freeze({ ... })
        for m in re.finditer(
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*Object\.freeze\(\s*\{([\s\S]{0,1200}?)\}\s*\)",
            txt,
        ):
            obj_name = m.group(1)
            body = m.group(2)
            keys = re.findall(r"([A-Za-z_$][\w$]*)\s*:", body)
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            file_items.append(
                {
                    "file": rel_path,
                    "entity_type": "constant",
                    "constant_kind": "frozen_object",
                    "entity_name": obj_name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "enum_keys": sorted(set(keys))[:40],
                    "enum_key_count": len(set(keys)),
                    "origin_label": fp.get("origin_label", "unknown"),
                    "restore_priority": fp.get("restore_priority", "low"),
                }
            )

        # 4) TS enum 编译产物（IIFE 形式）：
        # var H = ((e) => ((e[(e.DEBUG=0)]="DEBUG"), ... , e))(H || {});
        for m in re.finditer(
            r"\bvar\s+([A-Za-z_$][\w$]*)\s*=\s*\(\(\s*([A-Za-z_$][\w$]*)\s*\)\s*=>\s*\(([\s\S]{0,2400}?)\)\)\(\s*\1\s*\|\|\s*\{\}\s*\)",
            txt,
        ):
            enum_name = m.group(1)
            param_name = m.group(2)
            body = m.group(3)
            keys = re.findall(rf"{re.escape(param_name)}\.\s*([A-Z][A-Z0-9_]{{2,}})\s*=", body)
            if len(keys) < 2:
                keys = re.findall(rf"{re.escape(param_name)}\[\(\s*{re.escape(param_name)}\.([A-Z][A-Z0-9_]{{2,}})\s*=", body)
            if len(keys) < 2:
                continue
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            file_items.append(
                {
                    "file": rel_path,
                    "entity_type": "constant",
                    "constant_kind": "enum_iife",
                    "entity_name": enum_name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "enum_keys": sorted(set(keys))[:80],
                    "enum_key_count": len(set(keys)),
                    "origin_label": fp.get("origin_label", "unknown"),
                    "restore_priority": fp.get("restore_priority", "low"),
                }
            )

        # 5) TS enum 编译产物（function IIFE 形式）：
        # var xe; (function(e){...})(xe || (xe = {}));
        for m in re.finditer(
            r"\bvar\s+([A-Za-z_$][\w$]*)\s*;\s*\(\s*function\s*\(\s*([A-Za-z_$][\w$]*)\s*\)\s*\{([\s\S]{0,2600}?)\}\s*\)\(\s*\1\s*\|\|\s*\(\s*\1\s*=\s*\{\}\s*\)\s*\)",
            txt,
        ):
            enum_name = m.group(1)
            param_name = m.group(2)
            body = m.group(3)
            keys = re.findall(rf"{re.escape(param_name)}\.([A-Za-z][A-Za-z0-9_]*)\s*=", body)
            enum_like_keys = [k for k in keys if re.fullmatch(r"[A-Z][A-Za-z0-9_]{2,}", k) or re.fullmatch(r"[A-Z][a-zA-Z0-9_]+", k)]
            if len(enum_like_keys) < 2:
                continue
            line_start, line_end = infer_entity_line_range(txt, m.start(), m.end())
            file_items.append(
                {
                    "file": rel_path,
                    "entity_type": "constant",
                    "constant_kind": "enum_iife",
                    "entity_name": enum_name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "enum_keys": sorted(set(enum_like_keys))[:80],
                    "enum_key_count": len(set(enum_like_keys)),
                    "origin_label": fp.get("origin_label", "unknown"),
                    "restore_priority": fp.get("restore_priority", "low"),
                }
            )

        # 去重：同名同类型保留最早行
        uniq: dict[tuple[str, str], dict[str, Any]] = {}
        for it in file_items:
            key = (str(it.get("constant_kind", "")), str(it.get("entity_name", "")))
            if key not in uniq or int(it["line"]) < int(uniq[key]["line"]):
                uniq[key] = it
        deduped = sorted(uniq.values(), key=lambda x: (int(x["line"]), str(x.get("entity_name", ""))))

        for it in deduped:
            kind = str(it.get("constant_kind", "unknown"))
            entity_name = str(it.get("entity_name", ""))
            origin_label = str(it.get("origin_label", "unknown"))
            enum_key_count = int(it.get("enum_key_count", 0) or 0)
            value_head = str(it.get("value_head", ""))
            conf, tags, allow_auto = _constant_confidence(
                kind=kind,
                entity_name=entity_name,
                origin_label=origin_label,
                enum_key_count=enum_key_count,
                value_head=value_head,
            )
            it["confidence"] = conf
            it["signal_tags"] = tags
            it["allow_auto_restore"] = allow_auto
            it["semantic_bucket"] = _infer_semantic_bucket(it)
        items.extend(deduped)

        file_md = [
            f"# Constant Portrait: {rel_path}",
            "",
            f"- origin: `{fp.get('origin_label', 'unknown')}`",
            f"- restore_priority: `{fp.get('restore_priority', 'low')}`",
            "",
            "## Constants",
        ]
        if deduped:
            for it in deduped:
                kind = str(it.get("constant_kind", "unknown"))
                line = int(it.get("line", 1))
                line_end = int(it.get("line_end", line))
                entity = str(it.get("entity_name", ""))
                if kind == "upper_decl":
                    file_md.append(
                        f"- line {line}-{line_end}: {kind} `{entity}` = `{str(it.get('value_head', ''))[:80]}` "
                        f"(conf={it.get('confidence', 'low')}, auto={it.get('allow_auto_restore', False)})"
                    )
                else:
                    file_md.append(
                        f"- line {line}-{line_end}: {kind} `{entity}` (keys={int(it.get('enum_key_count', 0))}, "
                        f"conf={it.get('confidence', 'low')}, auto={it.get('allow_auto_restore', False)})"
                    )
        else:
            file_md.append("- none")
        safe_name = rel_path.replace("/", "__")
        write_text(out_dir / f"{safe_name}.md", "\n".join(file_md))

    write_json(
        paths.portraits / "constant_portraits.json",
        {
            "run_id": run_id,
            "count": len(items),
            "items": items,
        },
    )
    by_kind: dict[str, int] = {}
    by_conf: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    auto_restore_count = 0
    for it in items:
        k = str(it.get("constant_kind", "unknown"))
        by_kind[k] = by_kind.get(k, 0) + 1
        c = str(it.get("confidence", "low")).lower()
        by_conf[c] = by_conf.get(c, 0) + 1
        if bool(it.get("allow_auto_restore", False)):
            auto_restore_count += 1
    md = [
        "# Constant Portraits",
        "",
        f"- run_id: `{run_id}`",
        f"- constant_count: `{len(items)}`",
        f"- auto_restore_candidates: `{auto_restore_count}`",
        f"- high_conf: `{by_conf.get('high', 0)}`",
        f"- medium_conf: `{by_conf.get('medium', 0)}`",
        f"- low_conf: `{by_conf.get('low', 0)}`",
    ]
    for k in sorted(by_kind):
        md.append(f"- {k}: `{by_kind[k]}`")
    write_text(paths.portraits / "constant_portraits.md", "\n".join(md))


def cmd_build_method_portraits(workspace: Path, run_id: str) -> None:
    """方法画像：聚焦 class method 与典型 logger 方法签名。"""
    # 初始化 flow_tag_patterns 缓存（从 spec/semantic_rules.json + project_hints.json 加载）
    _load_flow_tag_patterns(workspace)
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    file_portrait_path = paths.portraits / "file_portraits.json"
    if not file_portrait_path.is_file():
        raise SystemExit("E_RUNTIME: run build-file-portraits first")
    fp_obj = json.loads(read_text(file_portrait_path))
    fp_by_file = {str(i.get("file", "")): i for i in fp_obj.get("items", [])}

    out_dir = paths.portraits / "method_portraits"
    out_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    logger_method_total = 0
    logger_class_candidates: list[dict[str, Any]] = []

    def _find_matching_brace(text: str, open_idx: int) -> int:
        depth = 0
        i = open_idx
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1
    for f in collect_files(source_root, {".js"}):
        rel_path = rel(f, source_root)
        txt = read_text(f)
        fp = fp_by_file.get(rel_path, {})
        origin_label = str(fp.get("origin_label", "unknown"))

        file_items: list[dict[str, Any]] = []
        class_blocks: list[dict[str, Any]] = []
        for cm in re.finditer(r"\bclass\s+([A-Za-z_$][\w$]*)\b", txt):
            class_name = cm.group(1)
            class_kw_end = cm.end()
            open_brace = txt.find("{", class_kw_end)
            if open_brace < 0:
                continue
            close_brace = _find_matching_brace(txt, open_brace)
            if close_brace < 0 or close_brace <= open_brace:
                continue
            class_blocks.append(
                {
                    "class_name": class_name,
                    "class_start": cm.start(),
                    "body_start": open_brace + 1,
                    "body_end": close_brace,
                }
            )
        # 无论是否存在 class，都补一份模块级扫描：
        # - 有 class 时：避免漏掉文件顶层/闭包内的函数定义（main-* 常见）。
        # - 无 class 时：等价于原先兜底逻辑。
        class_blocks.append(
            {
                "class_name": "__module__",
                "class_start": 0,
                "body_start": 0,
                "body_end": len(txt),
            }
        )

        for block in class_blocks:
            class_name = str(block["class_name"])
            body = txt[int(block["body_start"]) : int(block["body_end"])]
            method_hits: list[dict[str, Any]] = []
            for m in re.finditer(r"\b(debug|info|warn|error)\s*\(([^)]*)\)\s*\{", body):
                method_name = m.group(1)
                raw_params = [x.strip() for x in m.group(2).split(",") if x.strip()]
                if not raw_params:
                    continue
                abs_start = int(block["body_start"]) + m.start()
                abs_end = int(block["body_start"]) + m.end()
                line_start, line_end = infer_entity_line_range(txt, abs_start, abs_end)
                body_head = txt[abs_end : min(len(txt), abs_end + 300)]
                is_logger_like = bool(
                    re.search(r"console\.(?:log|warn|error)\s*\(", body_head)
                    and re.search(r"\[(?:DEBUG|INFO|WARN|ERROR)\]", body_head)
                )
                inferred_params: list[dict[str, Any]] = []
                if len(raw_params) >= 1:
                    inferred_params.append(
                        {
                            "param": raw_params[0],
                            "candidate": "logTag",
                            "confidence": "high" if is_logger_like else "medium",
                            "source_rule": "logger_signature_positional",
                        }
                    )
                if len(raw_params) >= 2:
                    inferred_params.append(
                        {
                            "param": raw_params[1],
                            "candidate": "logMessage",
                            "confidence": "high" if is_logger_like else "medium",
                            "source_rule": "logger_signature_positional",
                        }
                    )
                if len(raw_params) >= 3:
                    for p in raw_params[2:]:
                        inferred_params.append(
                            {
                                "param": p,
                                "candidate": "extraArgs",
                                "confidence": "low",
                                "source_rule": "logger_variadic_fallback",
                            }
                        )
                item = {
                    "file": rel_path,
                    "entity_type": "method",
                    "method_kind": "logger_method" if is_logger_like else "generic_method",
                    "class_name": class_name,
                    "method_name": method_name,
                    "line": line_start,
                    "line_end": int(line_end),
                    "params": raw_params,
                    "flow_tags": [],
                    "inferred_param_candidates": inferred_params,
                    "origin_label": origin_label,
                    "restore_priority": fp.get("restore_priority", "low"),
                    "confidence": "high" if is_logger_like else "medium",
                }
                file_items.append(item)
                method_hits.append(item)

            method_names = {str(x.get("method_name", "")) for x in method_hits}
            logger_hit_count = sum(1 for x in method_hits if str(x.get("method_kind", "")) == "logger_method")
            has_logger_signature = {"debug", "info", "warn", "error"}.issubset(method_names) and logger_hit_count >= 3
            # logger 类的补充方法画像：setLevel(t) 这类参数语义可高置信恢复为 level。
            if has_logger_signature:
                for m in re.finditer(r"\bsetLevel\s*\(([^)]*)\)\s*\{", body):
                    raw_params = [x.strip() for x in m.group(1).split(",") if x.strip()]
                    if len(raw_params) != 1:
                        continue
                    p0 = raw_params[0].lstrip(".")
                    if not re.fullmatch(r"[A-Za-z_$]\w{0,2}", p0):
                        continue
                    abs_start = int(block["body_start"]) + m.start()
                    abs_end = int(block["body_start"]) + m.end()
                    line_start, line_end = infer_entity_line_range(txt, abs_start, abs_end)
                    file_items.append(
                        {
                            "file": rel_path,
                            "entity_type": "method",
                            "method_kind": "logger_setter_method",
                            "class_name": class_name,
                            "method_name": "setLevel",
                            "line": line_start,
                            "line_end": int(line_end),
                            "params": raw_params,
                            "flow_tags": ["init"],
                            "inferred_param_candidates": [
                                {
                                    "param": raw_params[0],
                                    "candidate": "level",
                                    "confidence": "high",
                                    "source_rule": "logger_setter_param",
                                }
                            ],
                            "origin_label": origin_label,
                            "restore_priority": fp.get("restore_priority", "low"),
                            "confidence": "high",
                        }
                    )
            # 业务流方法画像：从编译产物函数签名与函数体关键字恢复“动作语义”。
            # 兼容三类写法：
            # 1) function a(...) {}
            # 2) const a = (...) => {}
            # 3) 逗号链赋值中的 a = (...) => {}（常见于压缩后 setup 内联定义）
            seen_flow_keys: set[tuple[str, int, int]] = set()

            def _append_flow_method(method_name: str, raw_params: list[str], abs_start: int, abs_end: int) -> None:
                key = (str(method_name), int(abs_start), int(abs_end))
                if key in seen_flow_keys:
                    return
                seen_flow_keys.add(key)
                line_start, line_end = infer_entity_line_range(txt, abs_start, abs_end)
                # 精确截取当前函数体，避免把后续函数内容混入当前画像导致语义串味。
                body_end = _find_matching_brace(txt, max(0, abs_end - 1))
                if body_end > abs_end:
                    body_head = txt[abs_end : min(body_end, abs_end + 2400)]
                else:
                    body_head = txt[abs_end : min(len(txt), abs_end + 1200)]
                flow_ranking = _infer_flow_tag_ranking(method_name, body_head)
                flow_tags = [tag for tag, _ in flow_ranking]
                if not flow_tags:
                    return
                flow_commands = _extract_command_literals(body_head)
                param_candidates = _infer_dialog_param_candidates(raw_params, body_head)
                has_literal_signal = ("\"" in body_head or "'" in body_head)
                top_score = float(flow_ranking[0][1]) if flow_ranking else 0.0
                second_score = float(flow_ranking[1][1]) if len(flow_ranking) > 1 else 0.0
                has_dominant_primary = top_score >= second_score + 1.5
                # has_strong_flow: 用 flow_tag_patterns 里的信号词检测，不硬编码正则
                _strong_tags = ("login", "logout", "open", "cancel", "confirm")
                _loaded_pats = _FLOW_TAG_PATTERNS_CACHE or {}
                has_strong_flow = bool(
                    any(tag in flow_tags for tag in _strong_tags)
                    and any(
                        any(str(sig).lower() in body_head.lower() for sig in _loaded_pats.get(tag, []))
                        for tag in _strong_tags
                        if tag in flow_tags
                    )
                )
                conf = "high" if (has_literal_signal and (len(flow_tags) == 1 or has_strong_flow or has_dominant_primary)) else "medium"
                file_items.append(
                    {
                        "file": rel_path,
                        "entity_type": "method",
                        "method_kind": "flow_method",
                        "class_name": class_name,
                        "method_name": method_name,
                        "line": line_start,
                        "line_end": int(line_end),
                        "params": raw_params,
                        "flow_tags": flow_tags,
                        "flow_commands": flow_commands,
                        "inferred_param_candidates": param_candidates,
                        "origin_label": origin_label,
                        "restore_priority": fp.get("restore_priority", "low"),
                        "confidence": conf,
                    }
                )

            for m in re.finditer(
                r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]{0,2})\s*\(([^)]*)\)\s*\{",
                body,
            ):
                method_name = m.group(1)
                raw_params = [x.strip() for x in m.group(2).split(",") if x.strip()]
                abs_start = int(block["body_start"]) + m.start()
                abs_end = int(block["body_start"]) + m.end()
                _append_flow_method(method_name, raw_params, abs_start, abs_end)
            for m in re.finditer(
                r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]{0,2})\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
                body,
            ):
                method_name = m.group(1)
                raw_params = [x.strip() for x in m.group(2).split(",") if x.strip()]
                abs_start = int(block["body_start"]) + m.start()
                abs_end = int(block["body_start"]) + m.end()
                _append_flow_method(method_name, raw_params, abs_start, abs_end)
            for m in re.finditer(
                r",\s*([A-Za-z_$][\w$]{0,2})\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
                body,
            ):
                method_name = m.group(1)
                raw_params = [x.strip() for x in m.group(2).split(",") if x.strip()]
                abs_start = int(block["body_start"]) + m.start()
                abs_end = int(block["body_start"]) + m.end()
                _append_flow_method(method_name, raw_params, abs_start, abs_end)
            # Pinia actions 方法提取：
            # 匹配 actions: { async methodName() {...}, methodName() {...} } 内的方法定义。
            # 典型结构：Ye("storeId", { state:()=>({...}), getters:{...}, actions:{ async login(e){...} } })
            for m_actions in re.finditer(r"\bactions\s*:\s*\{", body):
                actions_open = int(block["body_start"]) + m_actions.end() - 1
                actions_close = _find_matching_brace(txt, actions_open)
                if actions_close <= actions_open:
                    continue
                actions_body = txt[actions_open + 1 : actions_close]
                actions_body_offset = actions_open + 1
                for m_act in re.finditer(
                    r"(?:async\s+)?([A-Za-z_$][\w$]{0,40})\s*\(([^)]*)\)\s*\{",
                    actions_body,
                ):
                    act_name = m_act.group(1)
                    if act_name in {"if", "for", "while", "switch", "catch", "return", "async"}:
                        continue
                    raw_params = [x.strip() for x in m_act.group(2).split(",") if x.strip()]
                    abs_start = actions_body_offset + m_act.start()
                    abs_end = actions_body_offset + m_act.end()
                    _append_flow_method(act_name, raw_params, abs_start, abs_end)
            # Vue SFC setup() 内方法提取：
            # 匹配 setup(p, { emit: v }) { const ..., methodName = async (...) => {...} }
            # 以及 setup(p) { const ..., methodName = (...) => {...} }
            for m_setup in re.finditer(
                r"\bsetup\s*\(\s*([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\})?\s*\)\s*\{",
                body,
            ):
                setup_open = int(block["body_start"]) + m_setup.end() - 1
                setup_close = _find_matching_brace(txt, setup_open)
                if setup_close <= setup_open:
                    continue
                setup_body = txt[setup_open + 1 : setup_close]
                setup_body_offset = setup_open + 1
                # 提取 setup 内的箭头函数方法（含逗号链赋值）
                for m_sf in re.finditer(
                    r"(?:(?:const|let|var)\s+|,\s*)([A-Za-z_$][\w$]{0,2})\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
                    setup_body,
                ):
                    sf_name = m_sf.group(1)
                    raw_params = [x.strip() for x in m_sf.group(2).split(",") if x.strip()]
                    abs_start = setup_body_offset + m_sf.start()
                    abs_end = setup_body_offset + m_sf.end()
                    _append_flow_method(sf_name, raw_params, abs_start, abs_end)
            if has_logger_signature and class_name != "__module__":
                # 类画像候选：仅记录证据，不直接自动重命名。
                conf = "high" if origin_label == "app_business" else "medium"
                logger_class_candidates.append(
                    {
                        "file": rel_path,
                        "class_symbol": class_name,
                        "candidate": "appLogger",
                        "confidence": conf,
                        "evidence_refs": [f"{rel_path}#class:{class_name}", "logger_signature:debug+info+warn+error"],
                        "apply": False,
                    }
                )

        uniq: dict[tuple[str, int, str], dict[str, Any]] = {}
        for it in file_items:
            key = (str(it.get("method_name", "")), int(it.get("line", 0)), str(it.get("method_kind", "")))
            uniq[key] = it
        deduped = sorted(uniq.values(), key=lambda x: (int(x["line"]), str(x["method_name"])))
        items.extend(deduped)
        logger_method_total += sum(1 for x in deduped if x.get("method_kind") == "logger_method")

        file_md = [
            f"# Method Portrait: {rel_path}",
            "",
            f"- origin: `{origin_label}`",
            f"- restore_priority: `{fp.get('restore_priority', 'low')}`",
            "",
            "## Methods",
        ]
        if deduped:
            for it in deduped:
                file_md.append(
                    f"- line {it['line']}-{it['line_end']}: {it['method_name']} "
                    f"(class={it['class_name']}, kind={it['method_kind']}, conf={it['confidence']}, params={','.join(it['params'])})"
                )
        else:
            file_md.append("- none")
        safe_name = rel_path.replace("/", "__")
        write_text(out_dir / f"{safe_name}.md", "\n".join(file_md))

    write_json(
        paths.portraits / "method_portraits.json",
        {
            "run_id": run_id,
            "count": len(items),
            "logger_method_count": logger_method_total,
            "logger_class_candidates": logger_class_candidates,
            "items": items,
        },
    )
    md = [
        "# Method Portraits",
        "",
        f"- run_id: `{run_id}`",
        f"- method_count: `{len(items)}`",
        f"- logger_method_count: `{logger_method_total}`",
        f"- logger_class_candidates: `{len(logger_class_candidates)}`",
    ]
    write_text(paths.portraits / "method_portraits.md", "\n".join(md))
