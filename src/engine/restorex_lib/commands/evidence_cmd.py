from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import collect_files, read_text, rel, write_json, write_text
from restorex_lib.config_rules import load_json_if_exists
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def _infer_enum_candidate(enum_keys: list[str]) -> str:
    """基于枚举键推断可读候选名（保守模式：仅命中明确模式时返回）。"""
    keys_upper = {str(k).strip().upper() for k in enum_keys if str(k).strip()}
    if {"DEBUG", "INFO", "WARN", "ERROR"}.issubset(keys_upper):
        return "logLevelEnum"
    if {"NSIS", "MSI", "DEB", "RPM", "APPIMAGE", "APP"}.issubset(keys_upper):
        return "installerPackageTypeEnum"
    return ""


def _kebab_to_camel(raw: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", str(raw).strip()) if p]
    if not parts:
        return ""
    head = parts[0].lower()
    tail = "".join(x[:1].upper() + x[1:] for x in parts[1:])
    return head + tail


def _snake_to_pascal(raw: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", str(raw).strip()) if p]
    return "".join(x[:1].upper() + x[1:] for x in parts)


def _registry_candidate_from_key(key: str) -> str:
    """
    服务注册表 key 的可读候选归一化：
    - 统一提升为 PascalCase，贴近“服务对象/模块对象”命名风格；
    - 例如：auth -> Auth，errorLog -> ErrorLog。
    """
    raw = str(key).strip()
    if not raw:
        return ""
    return raw[:1].upper() + raw[1:]


def _service_role_from_key(key: str) -> str:
    k = str(key).strip().lower()
    if any(tok in k for tok in ("auth", "login", "logout", "token", "quota", "verify")):
        return "authentication"
    if any(tok in k for tok in ("error", "log", "trace")):
        return "logging"
    if any(tok in k for tok in ("clipboard", "copy", "paste")):
        return "clipboard"
    if any(tok in k for tok in ("config", "setting", "storage", "cache")):
        return "configuration"
    if any(tok in k for tok in ("shell", "browser", "openurl", "open_url", "url")):
        return "shell_bridge"
    return "service_facade"


def _find_assigned_object_body(text: str, symbol: str) -> str:
    pat = re.compile(rf"\b{re.escape(symbol)}\s*=\s*\{{")
    m = pat.search(text)
    if not m:
        return ""
    open_pos = m.end() - 1
    if open_pos < 0 or open_pos >= len(text) or text[open_pos] != "{":
        return ""
    depth = 0
    close_pos = -1
    for idx in range(open_pos, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                close_pos = idx
                break
    if close_pos <= open_pos:
        return ""
    return text[open_pos + 1 : close_pos]


def _extract_object_method_names(text: str, symbol: str) -> list[str]:
    body = _find_assigned_object_body(text, symbol)
    if not body:
        return []
    names: set[str] = set()
    # 对象方法简写：async foo(...) { } / foo(...) { }
    for name in re.findall(r"(?:async\s+)?([A-Za-z_]\w{2,})\s*\(", body):
        if str(name).strip():
            names.add(str(name).strip())
    # 属性函数：foo: async (...) => / foo: function (...)
    for name in re.findall(r"([A-Za-z_]\w{2,})\s*:\s*(?:async\s*)?(?:function\s*)?\(", body):
        if str(name).strip():
            names.add(str(name).strip())
    return sorted(names)


def _service_method_verb_stats(methods: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in methods:
        mm = str(m).strip()
        if not mm:
            continue
        token = re.match(
            r"^(auto|init|initialize|refresh|get|set|open|start|stop|create|fetch|check|update|copy|toggle|select|restore|login|logout|verify|clear|read|write)",
            mm,
            re.I,
        )
        key = (token.group(1).lower() if token else "other")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _verb_to_candidate(verb: str, module_prefix: str, tail_pascal: str) -> str:
    """把动作动词映射为候选命名模板。"""
    v = str(verb).strip().lower()
    if v in {"get", "set", "open", "start", "stop", "create", "fetch", "check", "update", "copy", "toggle", "select", "restore", "refresh"}:
        return f"{v}{module_prefix}{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "login":
        return f"handle{module_prefix}Login{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "logout":
        return f"handle{module_prefix}Logout{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v in {"cleanup", "clear", "reset"}:
        return f"handle{module_prefix}Cleanup{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "install":
        return f"handle{module_prefix}Install{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "uninstall":
        return f"handle{module_prefix}Uninstall{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "submit":
        return f"handle{module_prefix}Submit{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "confirm":
        return f"handle{module_prefix}Confirm{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "cancel":
        return f"handle{module_prefix}Cancel{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v == "retry":
        return f"handle{module_prefix}Retry{tail_pascal}" if (module_prefix or tail_pascal) else ""
    if v in {"is", "has", "can", "verify", "validate"}:
        return f"check{module_prefix}{tail_pascal}" if (module_prefix or tail_pascal) else ""
    return ""


def _load_module_hint_rules(workspace: Path) -> list[tuple[str, str]]:
    # 优先从 project_hints.json 读取（项目特定配置）
    hints_obj = load_json_if_exists(workspace / "cache" / "project" / "project_hints.json")
    items = hints_obj.get("file_module_hints", []) if isinstance(hints_obj.get("file_module_hints"), list) else []
    # 兼容旧版：若 project_hints.json 不存在，回退到 module_rules.json
    if not items:
        obj = load_json_if_exists(workspace / "cache" / "remote" / "module_rules.json")
        items = obj.get("file_module_hints", []) if isinstance(obj.get("file_module_hints"), list) else []
    out: list[tuple[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        m = str(it.get("match", "")).strip().lower()
        l = str(it.get("label", "")).strip()
        if m and l:
            out.append((m, l))
    # 无任何配置时返回空列表（不硬编码项目信息）
    return out


def _module_hint_from_file(path: str, hint_rules: list[tuple[str, str]]) -> str:
    p = str(path).lower()
    for m, label in hint_rules:
        if m in p:
            return label
    return ""


def _load_dedupe_rules(workspace: Path) -> dict[str, Any]:
    """
    通用规则从 module_rules.json 读取；
    项目特定的 hotspot_candidates/target_prefixes 从 project_hints.json 读取。
    """
    obj = load_json_if_exists(workspace / "cache" / "remote" / "module_rules.json")
    raw = obj.get("dedupe_rules", {}) if isinstance(obj.get("dedupe_rules", {}), dict) else {}
    hints = load_json_if_exists(workspace / "cache" / "project" / "project_hints.json")
    project_prefixes = [str(x).strip() for x in (hints.get("dedupe_target_prefixes", []) or []) if str(x).strip()]
    project_hotspots = [str(x).strip() for x in (hints.get("hotspot_candidates", []) or []) if str(x).strip()]
    if not project_prefixes:
        project_prefixes = [str(x).strip() for x in (raw.get("target_prefixes", []) or []) if str(x).strip()]
    if not project_hotspots:
        project_hotspots = [str(x).strip() for x in (raw.get("hotspot_candidates", []) or []) if str(x).strip()]
    return {
        "enabled": bool(raw.get("enabled", False)),
        "target_prefixes": project_prefixes,
        "max_symbols_per_candidate": max(1, int(raw.get("max_symbols_per_candidate", 1) or 1)),
        "conflict_resolution": str(raw.get("conflict_resolution", "flow_cmd_hit > evidence_count > confidence > later_line")).strip(),
        "fallback_scope_only": bool(raw.get("fallback_scope_only", True)),
        "flow_context_consistency_boost": bool(raw.get("flow_context_consistency_boost", True)),
        "prefer_hotspot_candidates": bool(raw.get("prefer_hotspot_candidates", True)),
        "hotspot_candidates": project_hotspots,
        "prune_semantic_duplicates": bool(raw.get("prune_semantic_duplicates", False)),
    }


def _extract_line_hint_from_evidence_refs(evidence_refs: list[str]) -> int:
    """
    从 evidence_refs 中提取 line 作为冲突裁决的最后 tie-break。
    优先解析 `#method:*:<line>-<line_end>`；解析失败返回 0。
    """
    for ref in evidence_refs:
        s = str(ref)
        m = re.search(r"#method:[^:]+:(\d+)-(\d+)", s)
        if m:
            return int(m.group(1))
    return 0


def _extract_flow_refs(evidence_refs: list[str]) -> tuple[list[str], list[str]]:
    flow_cmds: list[str] = []
    flow_tags: list[str] = []
    for ref in evidence_refs:
        s = str(ref).strip()
        if s.startswith("flow_cmd:"):
            flow_cmds.append(s.split(":", 1)[1].strip().lower())
        elif s.startswith("flow_tag:"):
            flow_tags.append(s.split(":", 1)[1].strip().lower())
    return flow_cmds, flow_tags


def _candidate_matches_flow_tag(candidate: str, flow_tags: list[str]) -> int:
    cand = str(candidate).strip().lower()
    if not cand:
        return 0
    for tag in flow_tags:
        t = str(tag).strip().lower()
        if not t:
            continue
        if t in cand:
            return 1
    return 0


def _candidate_matches_flow_cmd(candidate: str, flow_cmds: list[str]) -> int:
    cand = str(candidate).strip()
    if not cand:
        return 0
    cl = cand.lower()
    for cmd in flow_cmds:
        token = str(cmd).strip().lower()
        if not token:
            continue
        # bridge::invoke_* 场景仅用于弱补证，不作为强匹配。
        if token.startswith("bridge::"):
            continue
        parts = [p for p in token.split("_") if p]
        if not parts:
            continue
        if parts[0] in cl:
            return 1
    return 0


def _command_token_to_candidate(token: str, module_hint: str) -> str:
    """
    将命令字面量映射为可读函数名（项目无关）。
    例如：create_payment_order -> createPurchasePaymentOrder
    """
    raw = str(token).strip().lower()
    if not raw or "_" not in raw:
        return ""
    parts = [p for p in raw.split("_") if p]
    if len(parts) < 2:
        return ""
    action_verbs = {
        "get",
        "set",
        "open",
        "start",
        "stop",
        "create",
        "fetch",
        "check",
        "update",
        "copy",
        "toggle",
        "select",
        "restore",
        "refresh",
        "login",
        "logout",
        "cleanup",
        "clear",
        "reset",
        "install",
        "uninstall",
        "submit",
        "confirm",
        "cancel",
        "retry",
        "is",
        "has",
        "can",
        "verify",
        "validate",
    }
    verb_idx = 0
    if parts[0] not in action_verbs:
        for idx, seg in enumerate(parts[1:], start=1):
            if seg in action_verbs:
                verb_idx = idx
                break
    verb = parts[verb_idx]
    domain_prefix = "".join(x[:1].upper() + x[1:] for x in parts[:verb_idx])
    tail_parts = parts[verb_idx + 1 :]
    tail_pascal = _snake_to_pascal("_".join(tail_parts)) if tail_parts else ""
    m = str(module_hint).strip()
    module_prefix = m
    if domain_prefix and module_prefix.lower() == domain_prefix.lower():
        merged_prefix = module_prefix
    else:
        merged_prefix = f"{module_prefix}{domain_prefix}"
    tail_cmp = tail_pascal.lower()
    if merged_prefix and tail_cmp.startswith(merged_prefix.lower()):
        merged_prefix = ""
    return _verb_to_candidate(verb, merged_prefix, tail_pascal)


def _flow_tag_to_candidate(tag: str, module_hint: str) -> str:
    t = str(tag).strip().lower()
    m = str(module_hint).strip()
    if t == "login":
        return f"handle{m}Login" if m else "handleLogin"
    if t == "logout":
        return f"handle{m}Logout" if m else "handleLogout"
    if t == "open":
        return f"open{m}Dialog" if m else "openDialog"
    if t == "start":
        return f"start{m}Process" if m else "startProcess"
    if t == "stop":
        return f"stop{m}Process" if m else "stopProcess"
    if t == "cleanup":
        return f"handle{m}Cleanup" if m else "handleCleanup"
    if t == "install":
        return f"handle{m}Install" if m else "handleInstall"
    if t == "uninstall":
        return f"handle{m}Uninstall" if m else "handleUninstall"
    if t == "submit":
        return f"handle{m}Submit" if m else "handleSubmit"
    if t == "confirm":
        return f"handle{m}Confirm" if m else "handleConfirm"
    if t == "cancel":
        return f"handle{m}Cancel" if m else "handleCancel"
    if t == "retry":
        return f"handle{m}Retry" if m else "handleRetry"
    if t == "init":
        return f"handle{m}Init" if m else "handleInit"
    return ""


def _normalize_module_label(raw: str) -> str:
    text = str(raw).strip()
    if not text:
        return ""
    segs = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    if len(segs) == 1:
        segs = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", segs[0]) or segs
    pascal = "".join(s[:1].upper() + s[1:] for s in segs if s)
    for suffix in ("Dialog", "Page", "View", "Panel", "Module", "Screen"):
        if pascal.endswith(suffix) and len(pascal) > len(suffix):
            pascal = pascal[: -len(suffix)]
            break
    return pascal


def _module_invoke_candidate(path: str, hint_rules: list[tuple[str, str]]) -> str:
    module_hint = _normalize_module_label(_module_hint_from_file(path, hint_rules))
    if module_hint:
        return f"handle{module_hint}InvokeCommand"
    stem = str(path).strip().split("/")[-1].rsplit(".", 1)[0]
    prefix = stem.split("-", 1)[0]
    fallback_hint = _normalize_module_label(prefix)
    if fallback_hint:
        return f"handle{fallback_hint}InvokeCommand"
    return "handleInvokeCommand"


def cmd_build_evidence(
    workspace: Path,
    run_id: str,
    cfg: Any,
    *,
    bridge_token_to_candidate: Callable[[str, tuple[str, ...]], str],
    load_library_exclude_files: Callable[[Any], set[str]],
    confidence_rank: Callable[[str], int],
) -> None:
    paths = run_paths(workspace, run_id)
    origin_path = paths.analysis / "build_origin_report.json"
    chain_path = paths.analysis / "chain_graph.json"
    if not origin_path.is_file() or not chain_path.is_file():
        raise SystemExit("E_RUNTIME: run infer-build-origin and extract-chains first")

    origin_obj = json.loads(read_text(origin_path))
    chain_obj = json.loads(read_text(chain_path))
    module_hint_rules = _load_module_hint_rules(workspace)
    origin_by_file = {i["file"]: i.get("origin_label", "unknown") for i in origin_obj.get("items", [])}
    library_excludes = load_library_exclude_files(paths)
    bridge_hints_by_file_symbol: dict[tuple[str, str], list[str]] = {}
    for ch in chain_obj.get("items", []) if isinstance(chain_obj.get("items", []), list) else []:
        p = str(ch.get("file", "")).strip()
        if not p:
            continue
        bridges = [str(b).strip() for b in (ch.get("bridge_calls", []) or []) if str(b).strip()]
        if not bridges:
            continue
        call_symbols = [str(s).strip() for s in (ch.get("call_symbols", []) or []) if str(s).strip()]
        for sym in call_symbols:
            if not (re.fullmatch(r"[A-Za-z_$]\w{0,2}", sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            fs = (p, sym)
            arr = bridge_hints_by_file_symbol.setdefault(fs, [])
            for b in bridges:
                if b not in arr:
                    arr.append(b)
    service_registry_seed: dict[tuple[str, str], dict[str, Any]] = {}
    service_registry_items: list[dict[str, Any]] = []

    # symbol_map_seed
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    symbol_items: list[dict[str, Any]] = []
    pair_pat = re.compile(r"([A-Za-z_]\w{3,})\s*:\s*([A-Za-z_$]\w{0,2})\b")
    method_portrait_path = paths.portraits / "method_portraits.json"
    logger_param_short_by_file: dict[str, set[str]] = {}
    flow_method_keys: set[tuple[str, str]] = set()
    flow_method_context_by_file_symbol: dict[tuple[str, str], dict[str, Any]] = {}
    method_ranges_by_file: dict[str, list[dict[str, Any]]] = {}
    source_lines_cache: dict[str, list[str]] = {}
    if method_portrait_path.is_file():
        method_obj = json.loads(read_text(method_portrait_path))
        for it in method_obj.get("items", []):
            p = str(it.get("file", "")).strip()
            sym = str(it.get("method_name", "")).strip()
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            if not p or not sym or line_start <= 0:
                continue
            method_ranges_by_file.setdefault(p, []).append(
                {
                    "entity_name": f"method:{sym}:{line_start}-{max(line_start, line_end)}",
                    "entity_type": str(it.get("method_kind", "method")).strip() or "method",
                    "line_start": line_start,
                    "line_end": max(line_start, line_end),
                }
            )
        for it in method_obj.get("items", []):
            if str(it.get("method_kind", "")) != "logger_method":
                continue
            p = str(it.get("file", "")).strip()
            if not p:
                continue
            for prm in it.get("params", []) or []:
                sym = str(prm).strip()
                if re.fullmatch(r"[A-Za-z_$]\w{0,2}", sym):
                    logger_param_short_by_file.setdefault(p, set()).add(sym)
        for cand in method_obj.get("logger_class_candidates", []) or []:
            p = str(cand.get("file", "")).strip()
            sym = str(cand.get("class_symbol", "")).strip()
            candidate = str(cand.get("candidate", "")).strip()
            if re.fullmatch(r"^[a-z][A-Za-z0-9]{2,40}Logger$", candidate):
                candidate = candidate[:1].upper() + candidate[1:]
            conf = str(cand.get("confidence", "low")).lower()
            if not p or p in library_excludes:
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            if not re.fullmatch(cfg.short_name_regex, sym):
                continue
            if not re.fullmatch(cfg.candidate_regex, candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": conf if conf in {"high", "medium", "low"} else "low",
                    "evidence_refs": [str(x) for x in (cand.get("evidence_refs", []) or [])][:4],
                    "source": "method_logger_class_infer",
                    "apply": False,
                }
            )
        for it in method_obj.get("items", []):
            p = str(it.get("file", "")).strip()
            sym = str(it.get("method_name", "")).strip()
            kind = str(it.get("method_kind", "")).strip()
            if kind != "flow_method":
                continue
            if p and sym:
                flow_method_keys.add((p, sym))
                flow_method_context_by_file_symbol[(p, sym)] = {
                    "line": int(it.get("line", 0) or 0),
                    "line_end": int(it.get("line_end", int(it.get("line", 0) or 0)) or int(it.get("line", 0) or 0)),
                    "flow_tags": [str(x).strip().lower() for x in (it.get("flow_tags", []) or []) if str(x).strip()],
                    "flow_commands": [str(x).strip().lower() for x in (it.get("flow_commands", []) or []) if str(x).strip()],
                    "params": [str(x).strip() for x in (it.get("params", []) or []) if str(x).strip()],
                }
            if not p or p in library_excludes:
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            flow_tags = [str(x).strip().lower() for x in it.get("flow_tags", []) if str(x).strip()]
            if not flow_tags:
                continue
            module_hint = _module_hint_from_file(p, module_hint_rules)
            selected_tag = flow_tags[0]
            flow_commands = [str(x).strip().lower() for x in it.get("flow_commands", []) if str(x).strip()]
            # 画像未给出 flow_commands 时，回退到方法源码片段中提取命令字面量补证（低风险、仅补证据）。
            if not flow_commands:
                line_start = int(it.get("line", 0) or 0)
                line_end = int(it.get("line_end", line_start) or line_start)
                if line_start > 0:
                    if p not in source_lines_cache:
                        src_fp = source_root / p
                        if src_fp.is_file():
                            source_lines_cache[p] = read_text(src_fp).splitlines()
                        else:
                            source_lines_cache[p] = []
                    lines = source_lines_cache.get(p, [])
                    if lines:
                        seg = "\n".join(lines[max(0, line_start - 1) : min(len(lines), max(line_start, line_end))])
                        literal_cmds = re.findall(
                            r"['\"]((?:get|set|open|start|stop|create|fetch|check|update|copy|toggle|select|restore|refresh|login|logout|cleanup|clear|reset|install|uninstall|submit|confirm|cancel|retry|verify|validate)_[a-z0-9_]{2,80})['\"]",
                            seg,
                            flags=re.I,
                        )
                        flow_commands = [str(x).strip().lower() for x in literal_cmds if str(x).strip()]
            candidate = ""
            command_hit = ""
            for tok in flow_commands:
                cmd_cand = _command_token_to_candidate(tok, module_hint)
                if not cmd_cand:
                    continue
                candidate = cmd_cand
                command_hit = tok
                break
            if not candidate:
                candidate = _flow_tag_to_candidate(selected_tag, module_hint)
            # 若仍缺少 flow_cmd 证据，尝试用 chain_graph 反向补证（仅补证据，不强改候选）。
            if not command_hit:
                hints = bridge_hints_by_file_symbol.get((p, sym), [])
                if hints:
                    command_hit = f"bridge::{hints[0]}"
            if not candidate:
                continue
            if not re.fullmatch(cfg.candidate_regex, candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
                continue
            conf = str(it.get("confidence", "low")).lower()
            if conf not in {"high", "medium", "low"}:
                conf = "low"
            # 命令字面量命中时，允许将 medium 提升为 high（仅限高动词命令）。
            if conf == "medium" and command_hit:
                if re.match(r"^(create|get|set|open|start|stop|login|logout|install|uninstall|cleanup|clear|reset|submit|confirm|cancel|retry|verify|validate)_", command_hit):
                    conf = "high"
            # 业务流规则只在高置信进入自动改名，medium 保留为可审阅证据。
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            evidence_refs = [
                f"{p}#method:{sym}:{line_start}-{line_end}",
                (f"flow_cmd:{command_hit}" if command_hit else ""),
                f"flow_tag:{selected_tag}",
            ]
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": conf,
                    "evidence_refs": [x for x in evidence_refs if x],
                    "source": "method_business_flow_infer",
                    "apply": False,
                }
            )
    for f in collect_files(source_root, {".js"}):
        p = rel(f, source_root)
        if p in library_excludes:
            continue
        text = read_text(f)
        origin_label = origin_by_file.get(p, "unknown")
        if origin_label != "app_business":
            continue
        registry_pat = re.compile(r"(?:(?:\b(?:const|let|var)\s+)?([A-Za-z_$]\w{0,2})\s*=\s*\{)", re.S)
        prop_pat = re.compile(r"([A-Za-z_]\w{2,})\s*:\s*([A-Za-z_$]\w{0,2})\b")
        for reg in registry_pat.finditer(text):
            registry_symbol = str(reg.group(1))
            open_pos = reg.end() - 1
            if open_pos < 0 or open_pos >= len(text) or text[open_pos] != "{":
                continue
            depth = 0
            close_pos = -1
            for idx in range(open_pos, len(text)):
                ch = text[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        close_pos = idx
                        break
            if close_pos <= open_pos:
                continue
            body = text[open_pos + 1 : close_pos]
            props = [(str(k), str(v)) for k, v in prop_pat.findall(body)]
            # 通用服务注册表画像：至少 3 个语义键，值为短符号。
            filtered = [
                (k, v)
                for k, v in props
                if re.fullmatch(r"[a-z][A-Za-z0-9]{2,}", k) and re.fullmatch(r"[A-Za-z_$]\w{0,2}", v)
            ]
            if len(filtered) < 3:
                continue
            key_set = {k for k, _ in filtered}
            val_set = {v for _, v in filtered}
            avg_key_len = (sum(len(k) for k, _ in filtered) / max(1, len(filtered)))
            # 降低误报：要求键名更像“语义字段”，值短符号离散度较高。
            if len(key_set) != len(filtered):
                continue
            if len(val_set) < max(3, int(len(filtered) * 0.8)):
                continue
            if avg_key_len < 5:
                continue
            service_registry_items.append(
                {
                    "file": p,
                    "registry_symbol": registry_symbol,
                    "line": text.count("\n", 0, reg.start()) + 1,
                    "line_end": text.count("\n", 0, close_pos) + 1,
                    "entries": [{"key": k, "symbol": v} for k, v in filtered],
                    "evidence_ref": f"{p}#service_registry:{registry_symbol}",
                }
            )
            for key, short in filtered:
                fs = (p, short)
                old = service_registry_seed.get(fs)
                candidate = _registry_candidate_from_key(key)
                rank = len(key)
                if old is None or int(old.get("rank", 0)) < rank:
                    service_registry_seed[fs] = {
                        "candidate": candidate,
                        "raw_key": key,
                        "registry_symbol": registry_symbol,
                        "rank": rank,
                        "line": text.count("\n", 0, reg.start()) + 1,
                        "line_end": text.count("\n", 0, close_pos) + 1,
                        "evidence_ref": f"{p}#service_registry:{registry_symbol}:{key}->{short}",
                    }
        match_count = 0
        for semantic, short in pair_pat.findall(text):
            match_count += 1
            if semantic in cfg.generic_candidates:
                continue
            if not re.fullmatch(cfg.candidate_regex, semantic):
                continue
            if not re.fullmatch(r"[A-Za-z_$]\w{0,2}", short):
                continue
            # logger 参数短符号保护：避免被 pair_semantic 错映射为 safeDialog/safeMessage 一类语义。
            if short in logger_param_short_by_file.get(p, set()) and semantic.lower().startswith("safe"):
                continue
            if len(short) <= 2 and re.fullmatch(cfg.short_name_regex, short) and semantic[0].islower():
                confidence = "high"
            elif len(short) <= 2:
                confidence = "medium"
            else:
                confidence = "low"
            symbol_items.append(
                {
                    "file": p,
                    "symbol": short,
                    "candidate": semantic,
                    "confidence": confidence,
                    "evidence_refs": [f"{p}#pair:{match_count}"],
                    "source": "pair_semantic",
                    "apply": False,
                }
            )
        # 对服务注册表映射补证：将 key->short 关系显式回写为 pair_semantic 证据。
        for (file_key, short), seed in service_registry_seed.items():
            if file_key != p:
                continue
            candidate = str(seed.get("candidate", "")).strip()
            if not candidate:
                continue
            allow_registry_pascal_seed = bool(re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", candidate))
            if not (
                re.fullmatch(cfg.candidate_regex, candidate)
                or re.fullmatch(r"^[a-z][A-Za-z0-9]{3,}$", candidate)
                or allow_registry_pascal_seed
            ):
                continue
            symbol_items.append(
                {
                    "file": p,
                    "symbol": short,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": [str(seed.get("evidence_ref", ""))],
                    "source": "pair_semantic",
                    "apply": False,
                }
            )
        # Pinia store 实例名推断：
        # 匹配 const X = Ye("storeId", { state:()=>({...}), ... }) 模式
        # 生成候选名：storeId -> storeIdStore（如 ne -> authStore）
        for m_pinia in re.finditer(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]{0,2})\s*=\s*[A-Za-z_$][\w$]*\(\s*[\"']([a-zA-Z][a-zA-Z0-9_]{1,40})[\"']\s*,\s*\{",
            text,
        ):
            sym = str(m_pinia.group(1)).strip()
            store_id = str(m_pinia.group(2)).strip()
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            # 验证后面有 state:()=>({ 或 actions:{ 特征，确认是 Pinia store
            tail = text[m_pinia.end() : m_pinia.end() + 200]
            compact_tail = re.sub(r"\s+", "", tail).lower()
            if "state:()=>({" not in compact_tail and "actions:{" not in compact_tail:
                continue
            # 生成候选名：authStore、proxyStore 等
            candidate = f"{store_id[0].lower()}{store_id[1:]}Store"
            if not re.fullmatch(cfg.candidate_regex, candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            line_num = text.count("\n", 0, m_pinia.start()) + 1
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": [
                        f"{p}#pinia_store:{sym}:{line_num}",
                        f"store_id:{store_id}",
                    ],
                    "source": "pinia_store_infer",
                    "apply": False,
                }
            )
        # Vue SFC 组件变量名推断：
        # 匹配 const X = b({__name: "ComponentName", props:{...}, setup(...){...}}) 模式
        # 生成候选名：ComponentName -> componentNameComponent（如 j -> kiroAuthDialogComponent）
        for m_sfc in re.finditer(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]{0,2})\s*=\s*[A-Za-z_$][\w$]*\(\s*\{[^{]*__name\s*:\s*[\"']([A-Za-z][A-Za-z0-9]{2,60})[\"']",
            text,
        ):
            sym = str(m_sfc.group(1)).strip()
            component_name = str(m_sfc.group(2)).strip()
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            # 生成候选名：KiroAuthDialog -> kiroAuthDialogComponent
            camel = component_name[0].lower() + component_name[1:]
            candidate = f"{camel}Component"
            if not re.fullmatch(r"^[a-z][A-Za-z0-9]{5,60}Component$", candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            line_num = text.count("\n", 0, m_sfc.start()) + 1
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": [
                        f"{p}#vue_sfc:{sym}:{line_num}",
                        f"__name:{component_name}",
                    ],
                    "source": "vue_sfc_component_infer",
                    "apply": False,
                }
            )

    # 实体画像增强：根据 class_portraits + chain_graph 推断短符号语义名。
    class_portrait_path = paths.portraits / "class_portraits.json"
    constant_portrait_path = paths.portraits / "constant_portraits.json"
    chain_by_entity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in chain_obj.get("items", []):
        file_key = str(c.get("file", ""))
        ent = c.get("entity", {}) if isinstance(c.get("entity"), dict) else {}
        ent_name = str(ent.get("name", "")).strip()
        if not file_key or not ent_name:
            continue
        chain_by_entity.setdefault((file_key, ent_name), []).append(c)
    if class_portrait_path.is_file():
        cp_obj = json.loads(read_text(class_portrait_path))
        for ent in cp_obj.get("items", []):
            p = str(ent.get("file", "")).strip()
            sym = str(ent.get("entity_name", "")).strip()
            if not p or p in library_excludes:
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            chains = chain_by_entity.get((p, sym), [])
            if not chains:
                continue
            # 选择“高置信 + 高优先级 + 有 bridge 调用”的链路作为命名依据。
            chains_sorted = sorted(
                chains,
                key=lambda x: (
                    0 if str(x.get("confidence", "low")) == "high" else 1,
                    0 if str(x.get("restore_priority", "low")) == "high" else 1,
                    -len(x.get("bridge_calls", [])),
                ),
            )
            top = chains_sorted[0]
            bridges = [str(b) for b in top.get("bridge_calls", []) if str(b).strip()]
            if not bridges:
                continue
            candidate = bridge_token_to_candidate(bridges[0], cfg.auto_rename_prefixes)
            if not candidate or candidate in cfg.generic_candidates:
                continue
            if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
                continue
            conf = "high" if str(top.get("confidence", "low")) == "high" else "medium"
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": conf,
                    "evidence_refs": [f"{p}#entity:{sym}", str(top.get("chain_id", ""))],
                    "source": "entity_chain_infer",
                    "apply": False,
                }
            )
    # 常量画像增强：将高置信业务枚举接入符号映射（仅命中明确模式，避免过度推断）。
    if constant_portrait_path.is_file():
        const_obj = json.loads(read_text(constant_portrait_path))
        for it in const_obj.get("items", []):
            p = str(it.get("file", "")).strip()
            sym = str(it.get("entity_name", "")).strip()
            if not p or p in library_excludes:
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            if str(it.get("constant_kind", "")) not in {"enum_iife", "enum_object", "frozen_object"}:
                continue
            if str(it.get("confidence", "low")).lower() != "high":
                continue
            if not bool(it.get("allow_auto_restore", False)):
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            enum_keys = [str(x) for x in it.get("enum_keys", []) if str(x).strip()]
            candidate = _infer_enum_candidate(enum_keys)
            if not candidate:
                continue
            if candidate in cfg.generic_candidates:
                continue
            if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
                continue
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            evidence_refs = [f"{p}#constant:{sym}:{line_start}-{line_end}"]
            signal_tags = [str(x) for x in it.get("signal_tags", []) if str(x).strip()]
            if signal_tags:
                evidence_refs.extend(signal_tags[:4])
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": evidence_refs,
                    "source": "constant_enum_infer",
                    "apply": False,
                }
            )
            continue
        # class 锚点常量：const X = { class: "codex-auth-content" }
        for it in const_obj.get("items", []):
            p = str(it.get("file", "")).strip()
            sym = str(it.get("entity_name", "")).strip()
            if not p or p in library_excludes:
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            if str(it.get("constant_kind", "")) != "upper_decl":
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            value_head = str(it.get("value_head", "")).strip()
            m = re.search(r'class\s*:\s*"([a-zA-Z0-9_-]{4,})"', value_head)
            if not m:
                continue
            class_name = m.group(1)
            if "-" not in class_name:
                continue
            camel = _kebab_to_camel(class_name)
            if not camel:
                continue
            candidate = f"{camel}ClassRef"
            if not re.fullmatch(r"^[a-zA-Z][A-Za-z0-9]{5,48}$", candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
                continue
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": [
                        f"{p}#constant:{sym}:{line_start}-{line_end}",
                        f"class_anchor:{class_name}",
                    ],
                    "source": "constant_class_anchor",
                    "apply": False,
                }
            )
    # class anchor 补充扫描：直接从源文件扫描 `const x = { class: "kebab-name" }` 模式，
    # 覆盖 constant_portraits 未提取的小写变量名（如 h = { class: "kiro-auth-content" }）。
    for f in collect_files(source_root, {".js"}):
        p = rel(f, source_root)
        if p in library_excludes:
            continue
        if origin_by_file.get(p, "unknown") != "app_business":
            continue
        txt_src = read_text(f)
        for m_anchor in re.finditer(
            r"(?:const\s+|,\s*)([A-Za-z_$][\w$]{0,2})\s*=\s*\{\s*class\s*:\s*\"([a-zA-Z0-9_-]{4,})\"",
            txt_src,
        ):
            sym = str(m_anchor.group(1)).strip()
            class_name = str(m_anchor.group(2)).strip()
            if "-" not in class_name:
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            camel = _kebab_to_camel(class_name)
            if not camel:
                continue
            candidate = f"{camel}ClassRef"
            if not re.fullmatch(r"^[a-zA-Z][A-Za-z0-9]{5,48}$", candidate):
                continue
            if candidate in cfg.generic_candidates:
                continue
            if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
                continue
            line_num = txt_src.count("\n", 0, m_anchor.start()) + 1
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "confidence": "high",
                    "evidence_refs": [
                        f"{p}#constant:{sym}:{line_num}-{line_num}",
                        f"class_anchor:{class_name}",
                    ],
                    "source": "constant_class_anchor",
                    "apply": False,
                }
            )

    # 调用符号增强：直接利用链路中的 call_symbols + bridge_calls 做命名恢复。
    for ch in chain_obj.get("items", []):
        p = str(ch.get("file", "")).strip()
        if not p or p in library_excludes:
            continue
        if origin_by_file.get(p, "unknown") != "app_business":
            continue
        bridges = [str(b).strip() for b in ch.get("bridge_calls", []) if str(b).strip()]
        if not bridges:
            continue
        call_symbols = [str(s).strip() for s in ch.get("call_symbols", []) if str(s).strip()]
        if not call_symbols:
            continue
        base_candidate = bridge_token_to_candidate(bridges[0], cfg.auto_rename_prefixes)
        if not base_candidate:
            continue
        for sym in call_symbols:
            if not re.fullmatch(cfg.short_name_regex, sym):
                continue
            conf = "high" if str(ch.get("confidence", "low")) == "high" else "medium"
            symbol_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": base_candidate,
                    "confidence": conf,
                    "evidence_refs": [str(ch.get("chain_id", "")), f"{p}#call_symbol:{sym}"],
                    "source": "chain_call_symbol_infer",
                    "apply": False,
                }
            )
    # dedupe
    # 去重按 file+symbol+candidate 维度，避免把“局部语义”误扩散为全局改名。
    uniq: dict[tuple[str, str, str], dict[str, Any]] = {}
    for it in symbol_items:
        key = (it["file"], it["symbol"], it["candidate"])
        if key not in uniq:
            uniq[key] = it
    symbol_out = sorted(uniq.values(), key=lambda x: (x["symbol"], x["candidate"]))

    # 调用符号聚合：同一 file+symbol 若存在多个 chain_call_symbol_infer 候选，先按证据强度收敛为主候选。
    # 目的：减少 symbol_multi_candidates 对自动还原的阻断，同时保持“证据驱动”。
    by_file_symbol_all: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_all.setdefault(fs, []).append(it)

    pruned_symbol_out: list[dict[str, Any]] = []
    collapse_notes: dict[tuple[str, str], dict[str, Any]] = {}
    for fs, items in by_file_symbol_all.items():
        call_items = [x for x in items if str(x.get("source", "")) == "chain_call_symbol_infer"]
        if len(call_items) <= 1:
            pruned_symbol_out.extend(items)
            continue
        cand_score: dict[str, float] = {}
        cand_refs: dict[str, set[str]] = {}
        for ci in call_items:
            cand = str(ci.get("candidate", ""))
            if not cand:
                continue
            conf = str(ci.get("confidence", "low"))
            conf_weight = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(conf, 1.0)
            ev_count = max(1, len(ci.get("evidence_refs", [])))
            score = conf_weight + min(1.0, 0.25 * ev_count)
            cand_score[cand] = cand_score.get(cand, 0.0) + score
            cand_refs.setdefault(cand, set()).update(str(r) for r in ci.get("evidence_refs", []))
        ranked = sorted(cand_score.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) < 2:
            pruned_symbol_out.extend(items)
            continue
        top_cand, top_score = ranked[0]
        second_score = ranked[1][1]
        # 仅在“优势明确”时收敛，避免过度激进：
        # 1) top 至少比 second 高 2 分；或 2) top 证据覆盖量明显更高（>=2x）。
        top_refs = len(cand_refs.get(top_cand, set()))
        second_refs = len(cand_refs.get(ranked[1][0], set()))
        decisive = bool((top_score >= second_score + 2.0) or (top_refs >= max(2, second_refs * 2)))
        if not decisive:
            # 兜底：若该符号候选全部来自调用符号推断，且多候选长期打平，
            # 将其收敛为“桥接命令处理器”语义，避免流程被 symbol_multi_candidates 长期阻断。
            all_from_call_infer = len(call_items) == len(items)
            if not all_from_call_infer:
                pruned_symbol_out.extend(items)
                continue
            merged_refs: set[str] = set()
            max_conf_rank = 0
            for ci in call_items:
                merged_refs.update(str(r) for r in ci.get("evidence_refs", []))
                max_conf_rank = max(max_conf_rank, confidence_rank(str(ci.get("confidence", "low"))))
            merged_conf = "high" if max_conf_rank >= 3 else ("medium" if max_conf_rank >= 2 else "low")
            consolidated_candidate = _module_invoke_candidate(fs[0], module_hint_rules)
            pruned_symbol_out.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "candidate": consolidated_candidate,
                    "confidence": merged_conf,
                    "evidence_refs": sorted(merged_refs),
                    "source": "chain_call_symbol_consolidated",
                    "apply": False,
                }
            )
            collapse_notes[fs] = {
                "dominant_candidate": consolidated_candidate,
                "top_score": round(top_score, 3),
                "second_score": round(second_score, 3),
                "top_refs": top_refs,
                "second_refs": second_refs,
                "candidates": [{"candidate": c, "score": round(s, 3)} for c, s in ranked],
                "decision": "fallback_consolidated",
            }
            continue
        collapse_notes[fs] = {
            "dominant_candidate": top_cand,
            "top_score": round(top_score, 3),
            "second_score": round(second_score, 3),
            "top_refs": top_refs,
            "second_refs": second_refs,
            "candidates": [{"candidate": c, "score": round(s, 3)} for c, s in ranked],
            "decision": "dominant_candidate",
        }
        for it in items:
            if str(it.get("source", "")) != "chain_call_symbol_infer":
                pruned_symbol_out.append(it)
                continue
            if str(it.get("candidate", "")) == top_cand:
                pruned_symbol_out.append(it)
    symbol_out = sorted(pruned_symbol_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))

    # pair_semantic 多候选收敛：
    # 同 file+symbol 下若 pair_semantic 候选存在多项，但仅 1 个命中动词/安全前缀白名单，
    # 则保留该候选并去除同组其它 pair_semantic 候选，降低 symbol_multi_candidates 噪声。
    by_file_symbol_after_call: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_after_call.setdefault(fs, []).append(it)

    pruned_pair_out: list[dict[str, Any]] = []
    pair_collapse_notes: list[dict[str, Any]] = []
    service_registry_collapse_notes: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_after_call.items():
        pair_items = [x for x in items if str(x.get("source", "")) == "pair_semantic"]
        if len(pair_items) <= 1:
            pruned_pair_out.extend(items)
            continue
        pair_candidates = sorted({str(x.get("candidate", "")).strip() for x in pair_items if str(x.get("candidate", "")).strip()})
        if len(pair_candidates) <= 1:
            pruned_pair_out.extend(items)
            continue
        preferred = [
            c
            for c in pair_candidates
            if c.startswith(cfg.auto_rename_prefixes)
            and c not in cfg.generic_candidates
            and all(tok not in c for tok in cfg.forbidden_rename_tokens)
        ]
        preferred = sorted(set(preferred))
        if len(preferred) != 1:
            pruned_pair_out.extend(items)
            continue
        chosen = preferred[0]
        for it in items:
            src = str(it.get("source", ""))
            cand = str(it.get("candidate", ""))
            if src != "pair_semantic":
                pruned_pair_out.append(it)
                continue
            if cand == chosen:
                pruned_pair_out.append(it)
        pair_collapse_notes.append(
            {
                "file": fs[0],
                "symbol": fs[1],
                "chosen_candidate": chosen,
                "candidates": pair_candidates,
                "decision": "pair_semantic_unique_prefix",
            }
        )
    symbol_out = sorted(pruned_pair_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))
    # 服务注册表优先收敛：
    # 若同 file+symbol 命中 registry seed，且存在对应 pair_semantic 候选，则优先保留该候选并裁剪其它 pair_semantic 候选。
    by_file_symbol_after_pair2: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_after_pair2.setdefault(fs, []).append(it)
    pruned_registry_out: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_after_pair2.items():
        seed = service_registry_seed.get(fs)
        if not seed:
            pruned_registry_out.extend(items)
            continue
        preferred = str(seed.get("candidate", "")).strip()
        if not preferred:
            pruned_registry_out.extend(items)
            continue
        pair_pref = [x for x in items if str(x.get("source", "")) == "pair_semantic" and str(x.get("candidate", "")) == preferred]
        if len(pair_pref) != 1:
            pruned_registry_out.extend(items)
            continue
        kept_items: list[dict[str, Any]] = []
        dropped_candidates: list[str] = []
        for it in items:
            src = str(it.get("source", ""))
            cand = str(it.get("candidate", ""))
            if src == "pair_semantic" and cand != preferred:
                dropped_candidates.append(cand)
                continue
            kept_items.append(it)
        pruned_registry_out.extend(kept_items)
        if dropped_candidates:
            service_registry_collapse_notes.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "registry_symbol": str(seed.get("registry_symbol", "")),
                    "chosen_candidate": preferred,
                    "dropped_candidates": sorted(set(x for x in dropped_candidates if x)),
                    "decision": "service_registry_preferred_pair_semantic",
                }
            )
    symbol_out = sorted(pruned_registry_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))
    # 主候选保守收敛：
    # 若同 file+symbol 下存在唯一“主证据候选”（entity_chain_infer / chain_call_symbol_consolidated），
    # 且其余候选均为非白名单前缀的语义噪声，则裁剪噪声候选，降低 symbol_multi_candidates 阻断。
    by_file_symbol_after_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_after_pair.setdefault(fs, []).append(it)
    dominant_collapse_notes: list[dict[str, Any]] = []
    dominant_pruned_out: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_after_pair.items():
        if len(items) <= 1:
            dominant_pruned_out.extend(items)
            continue

        const_high_items = [
            x
            for x in items
            if str(x.get("source", "")) == "constant_enum_infer" and str(x.get("confidence", "low")) == "high"
        ]
        if const_high_items:
            dominant_pruned_out.extend(const_high_items)
            dominant_collapse_notes.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "chosen_candidate": str(const_high_items[0].get("candidate", "")),
                    "chosen_source": "constant_enum_infer",
                    "dropped_candidates": sorted(
                        {
                            str(x.get("candidate", "")).strip()
                            for x in items
                            if x not in const_high_items and str(x.get("candidate", "")).strip()
                        }
                    ),
                    "decision": "dominant_constant_enum_high",
                }
            )
            continue

        method_logger_high_items = [
            x
            for x in items
            if str(x.get("source", "")) == "method_logger_class_infer" and str(x.get("confidence", "low")) == "high"
        ]
        if len(method_logger_high_items) == 1:
            dominant_pruned_out.extend(method_logger_high_items)
            dominant_collapse_notes.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "chosen_candidate": str(method_logger_high_items[0].get("candidate", "")),
                    "chosen_source": "method_logger_class_infer",
                    "dropped_candidates": sorted(
                        {
                            str(x.get("candidate", "")).strip()
                            for x in items
                            if x not in method_logger_high_items and str(x.get("candidate", "")).strip()
                        }
                    ),
                    "decision": "dominant_method_logger_high",
                }
            )
            continue

        business_flow_high_items = [
            x
            for x in items
            if str(x.get("source", "")) == "method_business_flow_infer" and str(x.get("confidence", "low")) == "high"
        ]
        if len(business_flow_high_items) == 1:
            dominant_pruned_out.extend(business_flow_high_items)
            dominant_collapse_notes.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "chosen_candidate": str(business_flow_high_items[0].get("candidate", "")),
                    "chosen_source": "method_business_flow_infer",
                    "dropped_candidates": sorted(
                        {
                            str(x.get("candidate", "")).strip()
                            for x in items
                            if x not in business_flow_high_items and str(x.get("candidate", "")).strip()
                        }
                    ),
                    "decision": "dominant_method_business_flow_high",
                }
            )
            continue

        def _is_whitelisted_candidate(cand: str) -> bool:
            return bool(
                cand.startswith(cfg.auto_rename_prefixes)
                and cand not in cfg.generic_candidates
                and all(tok not in cand for tok in cfg.forbidden_rename_tokens)
            )

        strong_items = [
            x
            for x in items
            if str(x.get("source", "")) in {"entity_chain_infer", "chain_call_symbol_consolidated"}
            and _is_whitelisted_candidate(str(x.get("candidate", "")).strip())
        ]
        if len(strong_items) != 1:
            dominant_pruned_out.extend(items)
            continue
        chosen = strong_items[0]
        non_chosen = [x for x in items if x is not chosen]
        # 只在“其余候选全部非白名单”时收敛，保持保守。
        if any(_is_whitelisted_candidate(str(x.get("candidate", "")).strip()) for x in non_chosen):
            dominant_pruned_out.extend(items)
            continue
        dominant_pruned_out.append(chosen)
        dominant_collapse_notes.append(
            {
                "file": fs[0],
                "symbol": fs[1],
                "chosen_candidate": str(chosen.get("candidate", "")),
                "chosen_source": str(chosen.get("source", "")),
                "dropped_candidates": sorted(
                    {
                        str(x.get("candidate", "")).strip()
                        for x in non_chosen
                        if str(x.get("candidate", "")).strip()
                    }
                ),
                "decision": "dominant_whitelisted_candidate",
            }
        )
    symbol_out = sorted(dominant_pruned_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))

    # 混合来源冲突收敛：
    # 1) 同组内存在 entity_chain_infer 与 pair_semantic 时，若某一方置信度更高，则保留更高者。
    # 2) 同组已有白名单前缀候选时，剔除非前缀候选噪声，降低 symbol_multi_candidates。
    by_file_symbol_mixed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_mixed.setdefault(fs, []).append(it)
    mixed_source_collapse_notes: list[dict[str, Any]] = []
    mixed_pruned_out: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_mixed.items():
        current = list(items)
        if len(current) > 1:
            entity_items = [x for x in current if str(x.get("source", "")) == "entity_chain_infer"]
            pair_items = [x for x in current if str(x.get("source", "")) == "pair_semantic"]
            if entity_items and pair_items:

                def _best_conf_rank(xs: list[dict[str, Any]]) -> int:
                    if not xs:
                        return 0
                    return max(confidence_rank(str(x.get("confidence", "low"))) for x in xs)

                entity_rank = _best_conf_rank(entity_items)
                pair_rank = _best_conf_rank(pair_items)
                if entity_rank != pair_rank:
                    prefer_source = "entity_chain_infer" if entity_rank > pair_rank else "pair_semantic"
                    kept = [x for x in current if str(x.get("source", "")) == prefer_source]
                    dropped = [x for x in current if str(x.get("source", "")) != prefer_source]
                    current = kept
                    mixed_source_collapse_notes.append(
                        {
                            "file": fs[0],
                            "symbol": fs[1],
                            "decision": "mixed_source_by_confidence",
                            "preferred_source": prefer_source,
                            "entity_rank": entity_rank,
                            "pair_rank": pair_rank,
                            "dropped_candidates": sorted(
                                {
                                    str(x.get("candidate", "")).strip()
                                    for x in dropped
                                    if str(x.get("candidate", "")).strip()
                                }
                            ),
                        }
                    )
        if len(current) > 1:
            const_high = [
                x
                for x in current
                if str(x.get("source", "")) == "constant_enum_infer" and str(x.get("confidence", "low")) == "high"
            ]
            if const_high:
                dropped = [x for x in current if x not in const_high]
                current = const_high
                mixed_source_collapse_notes.append(
                    {
                        "file": fs[0],
                        "symbol": fs[1],
                        "decision": "constant_enum_high_priority",
                        "dropped_candidates": sorted(
                            {
                                str(x.get("candidate", "")).strip()
                                for x in dropped
                                if str(x.get("candidate", "")).strip()
                            }
                        ),
                    }
                )
        if len(current) > 1:
            prefixed = [x for x in current if str(x.get("candidate", "")).strip().startswith(cfg.auto_rename_prefixes)]
            if prefixed and len(prefixed) < len(current):
                dropped = [x for x in current if x not in prefixed]
                current = prefixed
                mixed_source_collapse_notes.append(
                    {
                        "file": fs[0],
                        "symbol": fs[1],
                        "decision": "drop_non_prefixed_when_prefixed_exists",
                        "dropped_candidates": sorted(
                            {
                                str(x.get("candidate", "")).strip()
                                for x in dropped
                                if str(x.get("candidate", "")).strip()
                            }
                        ),
                    }
                )
        if len(current) > 1:
            # 同前缀高置信 tie-break：
            # 仅在“全部来自 pair_semantic + 全高置信 + 共享同一动词前缀”时启用，
            # 以最小化风险地消除残余 symbol_multi_candidates。
            def _verb_prefix(cand: str) -> str:
                m = re.match(r"^([a-z]+)", cand)
                return m.group(1) if m else ""

            cands = [str(x.get("candidate", "")).strip() for x in current]
            sources = {str(x.get("source", "")) for x in current}
            confs = {str(x.get("confidence", "low")) for x in current}
            verbs = {_verb_prefix(c) for c in cands if c}
            if sources == {"pair_semantic"} and confs == {"high"} and len(verbs) == 1 and next(iter(verbs), "") in cfg.auto_rename_prefixes:
                rank_map = {}
                for it in current:
                    cand = str(it.get("candidate", "")).strip()
                    ev_count = len(it.get("evidence_refs", []))
                    # 先按证据条数，再按名字长度（更具体），最后字典序。
                    rank_map[cand] = (ev_count, len(cand), cand)
                chosen_cand = sorted(rank_map.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[1][2]))[0][0]
                dropped = [x for x in current if str(x.get("candidate", "")).strip() != chosen_cand]
                current = [x for x in current if str(x.get("candidate", "")).strip() == chosen_cand]
                mixed_source_collapse_notes.append(
                    {
                        "file": fs[0],
                        "symbol": fs[1],
                        "decision": "pair_same_prefix_tiebreak",
                        "chosen_candidate": chosen_cand,
                        "dropped_candidates": sorted(
                            {
                                str(x.get("candidate", "")).strip()
                                for x in dropped
                                if str(x.get("candidate", "")).strip()
                            }
                        ),
                    }
                )
        mixed_pruned_out.extend(current)
    symbol_out = sorted(mixed_pruned_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))
    # 服务注册表主导收敛（最终兜底）：
    # 若命中 registry seed，则优先保留 registry 对应候选，防止被其它来源（如前缀候选）挤出。
    by_file_symbol_after_mixed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_after_mixed.setdefault(fs, []).append(it)
    service_registry_dominant_notes: list[dict[str, Any]] = []
    registry_dominant_out: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_after_mixed.items():
        seed = service_registry_seed.get(fs)
        if not seed:
            registry_dominant_out.extend(items)
            continue
        preferred = str(seed.get("candidate", "")).strip()
        matched = [x for x in items if str(x.get("candidate", "")) == preferred]
        if not matched:
            registry_dominant_out.extend(items)
            continue
        kept = [matched[0]]
        dropped = [x for x in items if x is not matched[0]]
        registry_dominant_out.extend(kept)
        if dropped:
            service_registry_dominant_notes.append(
                {
                    "file": fs[0],
                    "symbol": fs[1],
                    "registry_symbol": str(seed.get("registry_symbol", "")),
                    "chosen_candidate": preferred,
                    "dropped_candidates": sorted({str(x.get("candidate", "")) for x in dropped if str(x.get("candidate", ""))}),
                    "decision": "service_registry_dominant_final",
                }
            )
    symbol_out = sorted(registry_dominant_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))

    # 不可执行候选抑制：
    # 若某 file+symbol 分组内不存在任何“可白名单自动改名”候选，
    # 则该组不进入 symbol_map_seed 主集合，避免把纯噪声候选计入未收敛指标。
    by_file_symbol_after_dominant: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol_after_dominant.setdefault(fs, []).append(it)
    actionable_symbol_out: list[dict[str, Any]] = []
    suppressed_symbol_items: list[dict[str, Any]] = []
    for fs, items in by_file_symbol_after_dominant.items():
        registry_seed = service_registry_seed.get(fs)
        if registry_seed:
            preferred = str(registry_seed.get("candidate", "")).strip()
            preferred_items = [x for x in items if str(x.get("candidate", "")).strip() == preferred]
            if preferred_items:
                actionable_symbol_out.append(preferred_items[0])
                for it in items:
                    if it is preferred_items[0]:
                        continue
                    suppressed_symbol_items.append(
                        {
                            "file": str(it.get("file", "")),
                            "symbol": str(it.get("symbol", "")),
                            "candidate": str(it.get("candidate", "")),
                            "confidence": str(it.get("confidence", "low")),
                            "source": str(it.get("source", "unknown")),
                            "reason": "service_registry_preferred_candidate_selected",
                            "evidence_refs": list(it.get("evidence_refs", [])),
                        }
                    )
                continue
        prefix_hits = [x for x in items if str(x.get("candidate", "")).strip().startswith(cfg.auto_rename_prefixes)]
        # 针对“纯 pair_semantic + 多候选 + 全非前缀名”的噪声分组进行抑制：
        # 这类分组通常难以从静态证据判定唯一语义，且会持续制造 symbol_multi_candidates 阻断。
        if len(items) > 1 and not prefix_hits and all(str(x.get("source", "")) == "pair_semantic" for x in items):
            for it in items:
                suppressed_symbol_items.append(
                    {
                        "file": str(it.get("file", "")),
                        "symbol": str(it.get("symbol", "")),
                        "candidate": str(it.get("candidate", "")),
                        "confidence": str(it.get("confidence", "low")),
                        "source": str(it.get("source", "unknown")),
                        "reason": "pair_semantic_multi_without_prefix",
                        "evidence_refs": list(it.get("evidence_refs", [])),
                    }
                )
            continue

        def _is_actionable_candidate(it: dict[str, Any]) -> bool:
            cand = str(it.get("candidate", "")).strip()
            src = str(it.get("source", ""))
            conf = str(it.get("confidence", "low"))
            refs = [str(x) for x in (it.get("evidence_refs", []) or []) if str(x).strip()]
            is_registry_pair = bool(src == "pair_semantic" and any("#service_registry:" in r for r in refs))
            if not cand or cand in cfg.generic_candidates or any(tok in cand for tok in cfg.forbidden_rename_tokens):
                return False
            by_prefix = cand.startswith(cfg.auto_rename_prefixes)
            relaxed_pair_semantic = bool(
                src == "pair_semantic"
                and conf == "high"
                and (re.fullmatch(cfg.candidate_regex, cand) or (is_registry_pair and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,}$", cand)))
                and len(cand) >= 4
                and cand[:1].islower()
            )
            relaxed_registry_pascal = bool(
                src == "pair_semantic"
                and conf == "high"
                and is_registry_pair
                and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", cand)
            )
            relaxed_pair_brand = bool(src == "pair_semantic" and conf == "medium" and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,24}$", cand))
            # medium 置信 + 白名单前缀 + 唯一映射 → 受控放行（仅限两字符以上符号，降低误报）
            relaxed_pair_medium_prefix = bool(
                getattr(cfg, "allow_pair_semantic_medium_prefix_two_char", False)
                and src == "pair_semantic"
                and conf == "medium"
                and by_prefix
                and len(cand) >= 6
                and re.fullmatch(cfg.candidate_regex, cand)
            )
            relaxed_constant_enum = bool(
                src == "constant_enum_infer"
                and conf == "high"
                and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{3,40}Enum$", cand)
            )
            relaxed_class_anchor = bool(
                src == "constant_class_anchor"
                and conf == "high"
                and re.fullmatch(r"^[a-zA-Z][A-Za-z0-9]{5,48}ClassRef$", cand)
            )
            relaxed_method_logger_class = bool(
                src == "method_logger_class_infer"
                and conf == "high"
                and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{2,40}Logger$", cand)
            )
            relaxed_method_business_flow = bool(
                src == "method_business_flow_infer"
                and conf == "high"
                and re.fullmatch(r"^(handle|open|start|stop|login|logout)[A-Za-z0-9]{3,60}$", cand)
            )
            relaxed_pinia_store = bool(
                src == "pinia_store_infer"
                and conf == "high"
                and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,48}Store$", cand)
            )
            relaxed_vue_sfc = bool(
                src == "vue_sfc_component_infer"
                and conf == "high"
                and re.fullmatch(r"^[a-z][A-Za-z0-9]{5,60}Component$", cand)
            )
            return bool(
                by_prefix
                or relaxed_pair_semantic
                or relaxed_registry_pascal
                or relaxed_pair_brand
                or relaxed_pair_medium_prefix
                or relaxed_constant_enum
                or relaxed_class_anchor
                or relaxed_method_logger_class
                or relaxed_method_business_flow
                or relaxed_pinia_store
                or relaxed_vue_sfc
            )

        has_actionable = any(_is_actionable_candidate(x) for x in items)
        if has_actionable:
            actionable_symbol_out.extend(items)
            continue
        for it in items:
            suppressed_symbol_items.append(
                {
                    "file": str(it.get("file", "")),
                    "symbol": str(it.get("symbol", "")),
                    "candidate": str(it.get("candidate", "")),
                    "confidence": str(it.get("confidence", "low")),
                    "source": str(it.get("source", "unknown")),
                    "reason": "group_without_actionable_whitelisted_candidate",
                    "evidence_refs": list(it.get("evidence_refs", [])),
                }
            )
    symbol_out = sorted(actionable_symbol_out, key=lambda x: (str(x.get("file", "")), x["symbol"], x["candidate"]))

    # method_business_flow_infer 预裁剪：
    # 对“同文件 + 同候选 + 同语义流签名（优先 flow_cmd, 其次 flow_tag）”的重复符号做保守收敛，
    # 仅保留最优一条，避免别名重复放大后续 dedupe 冲突组。
    dedupe_rules = _load_dedupe_rules(workspace)
    if bool(dedupe_rules.get("prune_semantic_duplicates", True)):
        def _semantic_signature(entry: dict[str, Any]) -> str:
            refs = [str(x) for x in (entry.get("evidence_refs", []) or []) if str(x).strip()]
            flow_cmds, flow_tags = _extract_flow_refs(refs)
            cmd_tokens = [x for x in flow_cmds if x and not str(x).startswith("bridge::")]
            if cmd_tokens:
                return f"cmd:{cmd_tokens[0]}"
            if flow_tags:
                return f"tag:{flow_tags[0]}"
            return "none"

        def _semantic_rank(entry: dict[str, Any]) -> tuple[int, int, int]:
            refs = [str(x) for x in (entry.get("evidence_refs", []) or []) if str(x).strip()]
            evidence_count = len(refs)
            conf_rank = confidence_rank(str(entry.get("confidence", "low")))
            line_hint = _extract_line_hint_from_evidence_refs(refs)
            return (evidence_count, conf_rank, line_hint)

        grouped_semantic: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for it in symbol_out:
            src = str(it.get("source", ""))
            if src != "method_business_flow_infer":
                continue
            f = str(it.get("file", ""))
            cand = str(it.get("candidate", ""))
            if not f or not cand:
                continue
            sig = _semantic_signature(it)
            grouped_semantic.setdefault((f, cand, sig), []).append(it)

        for (f, cand, sig), items in grouped_semantic.items():
            if len(items) <= 1:
                continue
            ranked = sorted(items, key=lambda x: _semantic_rank(x), reverse=True)
            keep = ranked[0]
            for loser in ranked[1:]:
                key = (str(loser.get("file", "")), str(loser.get("symbol", "")), str(loser.get("candidate", "")))
                if not all(key):
                    continue
                loser["apply"] = False
                loser["dedupe_scope_only"] = True
                loser["dedupe_semantic_pruned"] = True
                suppressed_symbol_items.append(
                    {
                        "file": key[0],
                        "symbol": key[1],
                        "candidate": key[2],
                        "confidence": str(loser.get("confidence", "low")),
                        "source": str(loser.get("source", "unknown")),
                        "reason": "method_business_flow_semantic_duplicate_pruned",
                        "semantic_signature": sig,
                        "kept_symbol": str(keep.get("symbol", "")),
                        "evidence_refs": [str(x) for x in (loser.get("evidence_refs", []) or []) if str(x).strip()],
                    }
                )

    # method_business_flow_infer 候选去重（配置驱动）：
    # 对 (file, candidate) 维度冲突按固定优先级裁决，仅改变自动应用资格，不删除证据。
    dedupe_report_items: list[dict[str, Any]] = []
    dedupe_hotspots: list[dict[str, Any]] = []
    dedupe_tuning_suggestions: list[dict[str, Any]] = []
    dedupe_summary = {
        "enabled": bool(dedupe_rules.get("enabled", False)),
        "target_prefixes": list(dedupe_rules.get("target_prefixes", [])),
        "max_symbols_per_candidate": int(dedupe_rules.get("max_symbols_per_candidate", 1)),
        "conflict_resolution": str(dedupe_rules.get("conflict_resolution", "")),
        "fallback_scope_only": bool(dedupe_rules.get("fallback_scope_only", True)),
        "flow_context_consistency_boost": bool(dedupe_rules.get("flow_context_consistency_boost", True)),
        "prefer_hotspot_candidates": bool(dedupe_rules.get("prefer_hotspot_candidates", True)),
        "hotspot_candidates": list(dedupe_rules.get("hotspot_candidates", [])),
        "conflict_groups": 0,
        "kept": 0,
        "dropped": 0,
        "scope_bridged": 0,
    }
    if dedupe_summary["enabled"]:
        prefixes = tuple(str(x) for x in dedupe_summary["target_prefixes"] if str(x).strip())
        max_keep = max(1, dedupe_summary["max_symbols_per_candidate"])
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for it in symbol_out:
            src = str(it.get("source", ""))
            f = str(it.get("file", ""))
            cand = str(it.get("candidate", ""))
            if src != "method_business_flow_infer" or not f or not cand:
                continue
            if bool(it.get("dedupe_semantic_pruned", False)):
                continue
            if prefixes and not any(f.startswith(pref) for pref in prefixes):
                continue
            grouped.setdefault((f, cand), []).append(it)

        for (f, cand), items in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if len(items) <= max_keep:
                continue
            dedupe_summary["conflict_groups"] += 1

            def _rank_key(entry: dict[str, Any]) -> tuple[int, int, int, int, int, int, int]:
                refs = [str(x) for x in (entry.get("evidence_refs", []) or []) if str(x).strip()]
                flow_cmds, flow_tags = _extract_flow_refs(refs)
                flow_cmd_hit = 1 if flow_cmds or flow_tags else 0
                cmd_candidate_match = _candidate_matches_flow_cmd(str(entry.get("candidate", "")), flow_cmds) if dedupe_summary["flow_context_consistency_boost"] else 0
                tag_candidate_match = _candidate_matches_flow_tag(str(entry.get("candidate", "")), flow_tags) if dedupe_summary["flow_context_consistency_boost"] else 0
                hotspot_hit = (
                    1
                    if dedupe_summary["prefer_hotspot_candidates"]
                    and str(entry.get("candidate", "")) in set(str(x) for x in dedupe_summary["hotspot_candidates"])
                    else 0
                )
                evidence_count = len(refs)
                conf_rank = confidence_rank(str(entry.get("confidence", "low")))
                line_hint = _extract_line_hint_from_evidence_refs(refs)
                return (flow_cmd_hit, cmd_candidate_match, tag_candidate_match, hotspot_hit, evidence_count, conf_rank, line_hint)

            ranked = sorted(items, key=lambda x: _rank_key(x), reverse=True)
            kept = ranked[:max_keep]
            dropped = ranked[max_keep:]
            dedupe_summary["kept"] += len(kept)
            dedupe_summary["dropped"] += len(dropped)
            top_rank = _rank_key(ranked[0]) if ranked else (0, 0, 0, 0)
            second_rank = _rank_key(ranked[1]) if len(ranked) > 1 else (0, 0, 0, 0)

            for loser in dropped:
                loser["apply"] = False
                if dedupe_summary["fallback_scope_only"]:
                    loser["dedupe_scope_only"] = True
                    if (f, str(loser.get("symbol", ""))) in flow_method_keys:
                        dedupe_summary["scope_bridged"] += 1

            dedupe_report_items.append(
                {
                    "file": f,
                    "candidate": cand,
                    "group_size": len(items),
                    "max_symbols_per_candidate": max_keep,
                    "kept_symbols": [str(x.get("symbol", "")) for x in kept],
                    "dropped_symbols": [str(x.get("symbol", "")) for x in dropped],
                    "kept_rank": [
                        {
                            "symbol": str(x.get("symbol", "")),
                            "rank": {
                                "flow_cmd_hit": _rank_key(x)[0],
                                "cmd_candidate_match": _rank_key(x)[1],
                                "tag_candidate_match": _rank_key(x)[2],
                                "hotspot_hit": _rank_key(x)[3],
                                "evidence_count": _rank_key(x)[4],
                                "confidence_rank": _rank_key(x)[5],
                                "line_hint": _rank_key(x)[6],
                            },
                            "evidence_refs": [str(r) for r in (x.get("evidence_refs", []) or []) if str(r).strip()],
                        }
                        for x in kept
                    ],
                    "dropped_rank": [
                        {
                            "symbol": str(x.get("symbol", "")),
                            "rank": {
                                "flow_cmd_hit": _rank_key(x)[0],
                                "cmd_candidate_match": _rank_key(x)[1],
                                "tag_candidate_match": _rank_key(x)[2],
                                "hotspot_hit": _rank_key(x)[3],
                                "evidence_count": _rank_key(x)[4],
                                "confidence_rank": _rank_key(x)[5],
                                "line_hint": _rank_key(x)[6],
                            },
                            "apply": False,
                            "scope_only": bool(dedupe_summary["fallback_scope_only"]),
                            "scope_candidate_exists": bool((f, str(x.get("symbol", ""))) in flow_method_keys),
                            "reason": "dedupe_conflict_loser",
                            "evidence_refs": [str(r) for r in (x.get("evidence_refs", []) or []) if str(r).strip()],
                        }
                        for x in dropped
                    ],
                    "resolution": str(dedupe_summary["conflict_resolution"]),
                }
            )
            dedupe_hotspots.append(
                {
                    "file": f,
                    "candidate": cand,
                    "group_size": len(items),
                    "top_rank": {
                        "flow_cmd_hit": top_rank[0],
                        "cmd_candidate_match": top_rank[1],
                        "tag_candidate_match": top_rank[2],
                        "hotspot_hit": top_rank[3],
                        "evidence_count": top_rank[4],
                        "confidence_rank": top_rank[5],
                        "line_hint": top_rank[6],
                    },
                    "second_rank": {
                        "flow_cmd_hit": second_rank[0],
                        "cmd_candidate_match": second_rank[1],
                        "tag_candidate_match": second_rank[2],
                        "hotspot_hit": second_rank[3],
                        "evidence_count": second_rank[4],
                        "confidence_rank": second_rank[5],
                        "line_hint": second_rank[6],
                    },
                    "near_tie": bool(top_rank == second_rank),
                    "symbols": [
                        {
                            "symbol": str(x.get("symbol", "")),
                            "rank": {
                                "flow_cmd_hit": _rank_key(x)[0],
                                "cmd_candidate_match": _rank_key(x)[1],
                                "tag_candidate_match": _rank_key(x)[2],
                                "hotspot_hit": _rank_key(x)[3],
                                "evidence_count": _rank_key(x)[4],
                                "confidence_rank": _rank_key(x)[5],
                                "line_hint": _rank_key(x)[6],
                            },
                            "method_context": flow_method_context_by_file_symbol.get((f, str(x.get("symbol", ""))), {}),
                            "evidence_refs": [str(r) for r in (x.get("evidence_refs", []) or []) if str(r).strip()],
                        }
                        for x in ranked
                    ],
                }
            )
            has_any_flow_cmd = any(_rank_key(x)[0] == 1 for x in ranked)
            if not has_any_flow_cmd:
                dedupe_tuning_suggestions.append(
                    {
                        "file": f,
                        "candidate": cand,
                        "suggestion": "no_flow_cmd_evidence",
                        "message": "冲突组缺少 flow_cmd 证据，建议优先增强命令字面量抽取规则。",
                        "symbols": [str(x.get("symbol", "")) for x in ranked],
                    }
                )
            if top_rank == second_rank:
                dedupe_tuning_suggestions.append(
                    {
                        "file": f,
                        "candidate": cand,
                        "suggestion": "rank_near_tie",
                        "message": "冲突组前两名评分相同，建议补充参数/调用上下文画像信号用于裁决。",
                        "symbols": [str(x.get("symbol", "")) for x in ranked[:2]],
                    }
                )

    by_file_symbol: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in symbol_out:
        fs_key = (str(it.get("file", "")), str(it.get("symbol", "")))
        by_file_symbol.setdefault(fs_key, []).append(it)
    for it in symbol_out:
        src_file = str(it.get("file", ""))
        sym = it["symbol"]
        cand = it["candidate"]
        src = str(it.get("source", ""))
        conf = str(it.get("confidence", "low"))
        evidence_refs = [str(x) for x in (it.get("evidence_refs", []) or []) if str(x).strip()]
        is_registry_pair = bool(src == "pair_semantic" and any("#service_registry:" in r for r in evidence_refs))
        dedupe_scope_only = bool(it.get("dedupe_scope_only", False))
        unique_mapping = len(by_file_symbol.get((src_file, sym), [])) == 1
        allow_prefix = cand.startswith(cfg.auto_rename_prefixes)
        # 对 pair_semantic 的高置信唯一映射，允许不走动词前缀白名单，
        # 以提升“语义键值对”还原覆盖率；其余来源保持原有严格约束。
        relaxed_pair_semantic = bool(
            cfg.allow_pair_semantic_high_unique_without_prefix
                and src == "pair_semantic"
                and conf == "high"
                and unique_mapping
                and (re.fullmatch(cfg.candidate_regex, cand) or (is_registry_pair and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,}$", cand)))
                and len(cand) >= 4
                and cand[:1].islower()
        )
        relaxed_registry_pascal = bool(
            src == "pair_semantic"
            and conf == "high"
            and unique_mapping
            and is_registry_pair
            and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", cand)
        )
        relaxed_pair_brand = bool(
            cfg.allow_pair_semantic_medium_brand_without_prefix
            and src == "pair_semantic"
            and conf == "medium"
            and unique_mapping
            and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,24}$", cand)
        )
        relaxed_constant_enum = bool(
            src == "constant_enum_infer"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{3,40}Enum$", cand)
        )
        relaxed_class_anchor = bool(
            src == "constant_class_anchor"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^[a-zA-Z][A-Za-z0-9]{5,48}ClassRef$", cand)
        )
        relaxed_method_logger_class = bool(
            src == "method_logger_class_infer"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{2,40}Logger$", cand)
        )
        relaxed_method_business_flow = bool(
            src == "method_business_flow_infer"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^(handle|open|start|stop|login|logout)[A-Za-z0-9]{3,60}$", cand)
        )
        relaxed_pinia_store = bool(
            src == "pinia_store_infer"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,48}Store$", cand)
        )
        relaxed_vue_sfc = bool(
            src == "vue_sfc_component_infer"
            and conf == "high"
            and unique_mapping
            and re.fullmatch(r"^[a-z][A-Za-z0-9]{5,60}Component$", cand)
        )
        ok_unique = unique_mapping or not cfg.require_unique_mapping
        allow_medium_chain_infer = bool(
            src in {"chain_call_symbol_infer", "chain_call_symbol_consolidated"}
            and conf == "medium"
            and cand.startswith(cfg.auto_rename_prefixes)
        )
        # 两字符符号 + medium 置信 + 白名单前缀 pair_semantic 放行（风险低于单字符）
        allow_medium_pair_two_char = bool(
            getattr(cfg, "allow_pair_semantic_medium_prefix_two_char", False)
            and src == "pair_semantic"
            and conf == "medium"
            and unique_mapping
            and len(sym) == 2
            and re.fullmatch(r"[A-Za-z]{2}", sym)
            and cand.startswith(cfg.auto_rename_prefixes)
            and len(cand) >= 6
        )
        ok_conf = conf == "high" or allow_medium_chain_infer or allow_medium_pair_two_char or not cfg.require_high_confidence
        it["apply"] = bool(
            (not dedupe_scope_only)
            and
            ok_conf
            and ok_unique
            and (
                re.fullmatch(cfg.short_name_regex, sym)
                or (
                    src in {
                        "constant_enum_infer",
                        "constant_class_anchor",
                        "method_logger_class_infer",
                        "method_business_flow_infer",
                        "pinia_store_infer",
                        "vue_sfc_component_infer",
                    }
                    and re.fullmatch(r"[A-Za-z]{1,2}", sym)
                )
                or (
                    # pair_semantic 高置信唯一映射的 PascalCase 服务对象（如 At→Config, Ct→Shell）
                    getattr(cfg, "allow_pascal_short_service_rename", False)
                    and src == "pair_semantic"
                    and conf == "high"
                    and re.fullmatch(r"[A-Za-z]{1,2}", sym)
                    and re.fullmatch(r"[A-Z][a-zA-Z]{2,}", cand)
                )
            )
            and (
                allow_prefix
                or relaxed_pair_semantic
                or relaxed_registry_pascal
                or relaxed_pair_brand
                or relaxed_constant_enum
                or relaxed_class_anchor
                or relaxed_method_logger_class
                or relaxed_method_business_flow
                or relaxed_pinia_store
                or relaxed_vue_sfc
            )
            and cand not in cfg.generic_candidates
            and all(tok not in cand for tok in cfg.forbidden_rename_tokens)
        )
    write_json(paths.analysis / "symbol_map_seed.json", {"run_id": run_id, "count": len(symbol_out), "items": symbol_out})
    if collapse_notes:
        collapse_items = []
        for (file_key, symbol_key), note in sorted(collapse_notes.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            collapse_items.append({"file": file_key, "symbol": symbol_key, **note})
        write_json(paths.analysis / "chain_call_symbol_collapse.json", {"run_id": run_id, "count": len(collapse_items), "items": collapse_items})
    if pair_collapse_notes:
        write_json(paths.analysis / "pair_semantic_collapse.json", {"run_id": run_id, "count": len(pair_collapse_notes), "items": pair_collapse_notes})
    if service_registry_items:
        write_json(
            paths.analysis / "service_registry_map.json",
            {"run_id": run_id, "count": len(service_registry_items), "items": service_registry_items},
        )
        # 服务门面职责画像：从 registry 的 key->symbol 映射回溯实现体的方法簇，产出可读职责标签。
        service_facade_items: list[dict[str, Any]] = []
        file_text_cache: dict[str, str] = {}
        for (file_key, short), seed in sorted(service_registry_seed.items(), key=lambda kv: (kv[0][0], str(kv[1].get("raw_key", "")))):
            raw_key = str(seed.get("raw_key", "")).strip()
            if not file_key or not raw_key:
                continue
            if file_key not in file_text_cache:
                fp = source_root / file_key
                file_text_cache[file_key] = read_text(fp) if fp.is_file() else ""
            src_text = file_text_cache.get(file_key, "")
            methods = _extract_object_method_names(src_text, short)
            facade = {
                "file": file_key,
                "registry_symbol": str(seed.get("registry_symbol", "")),
                "service_key": raw_key,
                "service_candidate": str(seed.get("candidate", "")),
                "service_symbol": short,
                "role_bucket": _service_role_from_key(raw_key),
                "method_count": len(methods),
                "methods": methods[:60],
                "method_verb_stats": _service_method_verb_stats(methods),
                "evidence_ref": str(seed.get("evidence_ref", "")),
            }
            service_facade_items.append(facade)
        if service_facade_items:
            write_json(
                paths.analysis / "service_facade_profile.json",
                {"run_id": run_id, "count": len(service_facade_items), "items": service_facade_items},
            )
            md = [
                "# Service Facade Profile",
                "",
                f"- run_id: `{run_id}`",
                f"- count: `{len(service_facade_items)}`",
                "",
                "| File | ServiceKey | Candidate | Role | Methods |",
                "|---|---|---|---|---:|",
            ]
            for it in service_facade_items[:200]:
                md.append(
                    f"| {it.get('file','')} | {it.get('service_key','')} | {it.get('service_candidate','')} | {it.get('role_bucket','')} | {it.get('method_count',0)} |"
                )
            write_text(paths.analysis / "service_facade_profile.md", "\n".join(md))
    if service_registry_collapse_notes:
        write_json(
            paths.analysis / "service_registry_symbol_collapse.json",
            {"run_id": run_id, "count": len(service_registry_collapse_notes), "items": service_registry_collapse_notes},
        )
    if service_registry_dominant_notes:
        write_json(
            paths.analysis / "service_registry_dominant.json",
            {"run_id": run_id, "count": len(service_registry_dominant_notes), "items": service_registry_dominant_notes},
        )
    if dominant_collapse_notes:
        write_json(paths.analysis / "dominant_symbol_collapse.json", {"run_id": run_id, "count": len(dominant_collapse_notes), "items": dominant_collapse_notes})
    if mixed_source_collapse_notes:
        write_json(
            paths.analysis / "mixed_source_symbol_collapse.json",
            {"run_id": run_id, "count": len(mixed_source_collapse_notes), "items": mixed_source_collapse_notes},
        )
    if suppressed_symbol_items:
        write_json(paths.analysis / "symbol_map_suppressed.json", {"run_id": run_id, "count": len(suppressed_symbol_items), "items": suppressed_symbol_items})
    write_json(
        paths.analysis / "business_flow_dedupe_report.json",
        {
            "run_id": run_id,
            "summary": dedupe_summary,
            "count": len(dedupe_report_items),
            "items": dedupe_report_items,
        },
    )
    md_dedupe = [
        "# Business Flow Dedupe Report",
        "",
        f"- run_id: `{run_id}`",
        f"- enabled: `{dedupe_summary['enabled']}`",
        f"- target_prefixes: `{','.join(dedupe_summary['target_prefixes'])}`",
        f"- conflict_groups: `{dedupe_summary['conflict_groups']}`",
        f"- kept: `{dedupe_summary['kept']}`",
        f"- dropped: `{dedupe_summary['dropped']}`",
        f"- scope_bridged: `{dedupe_summary['scope_bridged']}`",
        f"- resolution: `{dedupe_summary['conflict_resolution']}`",
        "",
        "| File | Candidate | GroupSize | Kept | Dropped |",
        "|---|---|---:|---|---|",
    ]
    for item in dedupe_report_items[:300]:
        md_dedupe.append(
            f"| {item.get('file','')} | {item.get('candidate','')} | {item.get('group_size',0)} | {','.join(item.get('kept_symbols',[]))} | {','.join(item.get('dropped_symbols',[]))} |"
        )
    write_text(paths.analysis / "business_flow_dedupe_report.md", "\n".join(md_dedupe))
    dedupe_hotspots.sort(key=lambda x: (-int(x.get("group_size", 0)), str(x.get("file", "")), str(x.get("candidate", ""))))
    write_json(
        paths.analysis / "business_flow_conflict_hotspots.json",
        {
            "run_id": run_id,
            "count": len(dedupe_hotspots),
            "items": dedupe_hotspots,
        },
    )
    md_hotspots = [
        "# Business Flow Conflict Hotspots",
        "",
        f"- run_id: `{run_id}`",
        f"- hotspots: `{len(dedupe_hotspots)}`",
        "",
        "| File | Candidate | GroupSize | NearTie | TopRank(flow/evidence/conf/line) |",
        "|---|---|---:|---|---|",
    ]
    for item in dedupe_hotspots[:300]:
        tr = item.get("top_rank", {})
        md_hotspots.append(
            f"| {item.get('file','')} | {item.get('candidate','')} | {item.get('group_size',0)} | {item.get('near_tie',False)} | {tr.get('flow_cmd_hit',0)}/{tr.get('evidence_count',0)}/{tr.get('confidence_rank',0)}/{tr.get('line_hint',0)} |"
        )
    write_text(paths.analysis / "business_flow_conflict_hotspots.md", "\n".join(md_hotspots))
    write_json(
        paths.analysis / "business_flow_dedupe_tuning_suggestions.json",
        {
            "run_id": run_id,
            "count": len(dedupe_tuning_suggestions),
            "items": dedupe_tuning_suggestions,
        },
    )
    md_suggestions = [
        "# Business Flow Dedupe Tuning Suggestions",
        "",
        f"- run_id: `{run_id}`",
        f"- suggestions: `{len(dedupe_tuning_suggestions)}`",
        "",
        "| File | Candidate | Suggestion | Message | Symbols |",
        "|---|---|---|---|---|",
    ]
    for item in dedupe_tuning_suggestions[:300]:
        md_suggestions.append(
            f"| {item.get('file','')} | {item.get('candidate','')} | {item.get('suggestion','')} | {item.get('message','')} | {','.join(item.get('symbols',[]))} |"
        )
    write_text(paths.analysis / "business_flow_dedupe_tuning_suggestions.md", "\n".join(md_suggestions))
    rename_plan_items: list[dict[str, Any]] = []
    for it in symbol_out:
        sym = it["symbol"]
        cand = it["candidate"]
        src = str(it.get("source", ""))
        conf = str(it.get("confidence", "low"))
        evidence_refs = [str(x) for x in (it.get("evidence_refs", []) or []) if str(x).strip()]
        is_registry_pair = bool(src == "pair_semantic" and any("#service_registry:" in r for r in evidence_refs))
        dedupe_scope_only = bool(it.get("dedupe_scope_only", False))
        reason = []
        allow_short = bool(re.fullmatch(cfg.short_name_regex, sym))
        allow_const_short = bool(
            src in {"constant_enum_infer", "constant_class_anchor", "method_logger_class_infer", "method_business_flow_infer"}
            and re.fullmatch(r"[A-Za-z]{1,2}", sym)
        )
        allow_pascal_service = bool(
            getattr(cfg, "allow_pascal_short_service_rename", False)
            and src == "pair_semantic"
            and conf == "high"
            and re.fullmatch(r"[A-Za-z]{1,2}", sym)
            and re.fullmatch(r"[A-Z][a-zA-Z]{2,}", cand)
        )
        if not allow_short and not allow_const_short and not allow_pascal_service:
            reason.append("short_not_lower_1_2")
        src_file = str(it.get("file", ""))
        symbol_choices = len(by_file_symbol.get((src_file, sym), []))
        if symbol_choices != 1:
            reason.append(f"symbol_multi_candidates:{symbol_choices}")
        relaxed_pair_semantic = bool(
            cfg.allow_pair_semantic_high_unique_without_prefix
            and src == "pair_semantic"
            and conf == "high"
            and symbol_choices == 1
            and (re.fullmatch(cfg.candidate_regex, cand) or (is_registry_pair and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,}$", cand)))
            and len(cand) >= 4
            and cand[:1].islower()
        )
        relaxed_registry_pascal = bool(
            src == "pair_semantic"
            and conf == "high"
            and symbol_choices == 1
            and is_registry_pair
            and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", cand)
        )
        relaxed_pair_brand = bool(
            cfg.allow_pair_semantic_medium_brand_without_prefix
            and src == "pair_semantic"
            and conf == "medium"
            and symbol_choices == 1
            and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,24}$", cand)
        )
        relaxed_constant_enum = bool(
            src == "constant_enum_infer"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{3,40}Enum$", cand)
        )
        relaxed_class_anchor = bool(
            src == "constant_class_anchor"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^[a-zA-Z][A-Za-z0-9]{5,48}ClassRef$", cand)
        )
        relaxed_method_logger_class = bool(
            src == "method_logger_class_infer"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^[A-Za-z][A-Za-z0-9]{2,40}Logger$", cand)
        )
        relaxed_method_business_flow = bool(
            src == "method_business_flow_infer"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^(handle|open|start|stop|login|logout)[A-Za-z0-9]{3,60}$", cand)
        )
        relaxed_pinia_store = bool(
            src == "pinia_store_infer"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,48}Store$", cand)
        )
        relaxed_vue_sfc = bool(
            src == "vue_sfc_component_infer"
            and conf == "high"
            and symbol_choices == 1
            and re.fullmatch(r"^[a-z][A-Za-z0-9]{5,60}Component$", cand)
        )
        if (
            not cand.startswith(cfg.auto_rename_prefixes)
            and not relaxed_pair_semantic
            and not relaxed_registry_pascal
            and not relaxed_pair_brand
            and not relaxed_constant_enum
            and not relaxed_class_anchor
            and not relaxed_method_logger_class
            and not relaxed_method_business_flow
            and not relaxed_pinia_store
            and not relaxed_vue_sfc
        ):
            reason.append("candidate_prefix_not_whitelisted")
        if cand in cfg.generic_candidates:
            reason.append("candidate_generic")
        if any(tok in cand for tok in cfg.forbidden_rename_tokens):
            reason.append("candidate_hits_forbidden_tokens")
        if dedupe_scope_only:
            reason.append("dedupe_scope_only")
        rename_plan_items.append(
            {
                "file": it.get("file", ""),
                "symbol": sym,
                "candidate": cand,
                "confidence": it["confidence"],
                "source": str(it.get("source", "unknown")),
                "apply": it["apply"],
                "reasons": reason if reason else ["pass"],
                "evidence_refs": it["evidence_refs"],
            }
        )
    write_json(paths.analysis / "rename_plan_focus.json", {"run_id": run_id, "count": len(rename_plan_items), "items": rename_plan_items})
    md_plan = [
        "# Rename Plan Focus",
        "",
        f"- run_id: `{run_id}`",
        f"- total: `{len(rename_plan_items)}`",
        f"- auto_apply: `{sum(1 for i in rename_plan_items if i['apply'])}`",
        "",
        "| Symbol | Candidate | Confidence | Source | Apply | Reasons | File |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in rename_plan_items[:300]:
        md_plan.append(
            f"| {i['symbol']} | {i['candidate']} | {i['confidence']} | {i.get('source','')} | {i['apply']} | {','.join(i['reasons'])} | {i['file']} |"
        )
    write_text(paths.analysis / "rename_plan_focus.md", "\n".join(md_plan))

    # scope_rename_candidates：为下一阶段“作用域改名”准备候选（不直接自动替换）。
    scope_items: list[dict[str, Any]] = []
    scope_uniq: set[tuple[str, str, str, int, int, str]] = set()
    for ch in chain_obj.get("items", []):
        p = str(ch.get("file", "")).strip()
        if not p or p in library_excludes:
            continue
        if origin_by_file.get(p, "unknown") != "app_business":
            continue
        ent = ch.get("entity", {}) if isinstance(ch.get("entity"), dict) else {}
        ent_name = str(ent.get("name", "")).strip()
        ent_type = str(ent.get("type", "")).strip()
        line_start = int(ent.get("line", 0) or 0)
        line_end = int(ent.get("line_end", line_start) or line_start)
        if not ent_name or ent_name == "__module__" or line_start <= 0:
            continue
        bridges = [str(b).strip() for b in ch.get("bridge_calls", []) if str(b).strip()]
        if not bridges:
            continue
        candidate = bridge_token_to_candidate(bridges[0], cfg.auto_rename_prefixes)
        if not candidate or candidate in cfg.generic_candidates:
            continue
        if any(tok in candidate for tok in cfg.forbidden_rename_tokens):
            continue
        call_symbols = [str(s).strip() for s in ch.get("call_symbols", []) if str(s).strip()]
        for sym in call_symbols:
            if not re.fullmatch(cfg.short_name_regex, sym):
                continue
            skey = (p, sym, ent_name, line_start, line_end, candidate)
            if skey in scope_uniq:
                continue
            scope_uniq.add(skey)
            scope_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "entity_name": ent_name,
                    "entity_type": ent_type,
                    "line_start": line_start,
                    "line_end": max(line_start, line_end),
                    "confidence": str(ch.get("confidence", "low")),
                    "bridge_calls": bridges,
                    "evidence_refs": [str(ch.get("chain_id", "")), f"{p}#entity:{ent_name}:{line_start}-{line_end}"],
                }
            )
    # 方法画像增强：为 method_business_flow_infer 生成“函数体内”作用域候选，
    # 用于承接全局风控拦截后的局部可读化替换（尤其是 main-* 的单字符符号）。
    business_candidate_by_file_symbol: dict[tuple[str, str], dict[str, Any]] = {}
    for it in symbol_out:
        src = str(it.get("source", ""))
        if src != "method_business_flow_infer":
            continue
        p = str(it.get("file", "")).strip()
        sym = str(it.get("symbol", "")).strip()
        cand = str(it.get("candidate", "")).strip()
        conf = str(it.get("confidence", "low")).lower()
        if not p or p in library_excludes:
            continue
        if origin_by_file.get(p, "unknown") != "app_business":
            continue
        if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
            continue
        if not cand or not re.fullmatch(cfg.candidate_regex, cand):
            continue
        if cand in cfg.generic_candidates or any(tok in cand for tok in cfg.forbidden_rename_tokens):
            continue
        fs = (p, sym)
        old = business_candidate_by_file_symbol.get(fs)
        if old is None or confidence_rank(conf) > confidence_rank(str(old.get("confidence", "low"))):
            business_candidate_by_file_symbol[fs] = {
                "candidate": cand,
                "confidence": conf,
                "evidence_refs": [str(x) for x in (it.get("evidence_refs", []) or []) if str(x).strip()],
            }
    if method_portrait_path.is_file():
        try:
            method_obj2 = json.loads(read_text(method_portrait_path))
        except Exception:
            method_obj2 = {"items": []}
        for it in method_obj2.get("items", []):
            if str(it.get("method_kind", "")) != "flow_method":
                continue
            p = str(it.get("file", "")).strip()
            sym = str(it.get("method_name", "")).strip()
            if not p or not sym:
                continue
            if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
                continue
            if origin_by_file.get(p, "unknown") != "app_business":
                continue
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            if line_start <= 0:
                continue
            pick = business_candidate_by_file_symbol.get((p, sym))
            if not pick:
                continue
            candidate = str(pick.get("candidate", "")).strip()
            if not candidate:
                continue
            conf = str(pick.get("confidence", "low"))
            method_refs = [f"{p}#method:{sym}:{line_start}-{line_end}"]
            flow_cmds = [str(x).strip() for x in (it.get("flow_commands", []) or []) if str(x).strip()]
            if flow_cmds:
                method_refs.append(f"flow_cmd:{flow_cmds[0]}")
            evidence_refs = method_refs + [str(x) for x in pick.get("evidence_refs", []) if str(x).strip()]
            entity_name = f"method:{sym}:{line_start}-{line_end}"
            skey = (p, sym, entity_name, line_start, max(line_start, line_end), candidate)
            if skey in scope_uniq:
                continue
            scope_uniq.add(skey)
            scope_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "entity_name": entity_name,
                    "entity_type": "flow_method",
                    "line_start": line_start,
                    "line_end": max(line_start, line_end),
                    "confidence": conf,
                    "bridge_calls": [],
                    "evidence_refs": evidence_refs[:8],
                    "source": "scope_method_business_flow_infer",
                }
            )
    # 服务注册表增强：将 K={auth:vt,...} 类映射转为“方法作用域”候选，避免全局替换污染。
    file_lines_cache: dict[str, list[str]] = {}
    file_text_cache: dict[str, str] = {}
    for (p, sym), seed in service_registry_seed.items():
        if not p or p in library_excludes:
            continue
        if origin_by_file.get(p, "unknown") != "app_business":
            continue
        if not (re.fullmatch(cfg.short_name_regex, sym) or re.fullmatch(r"[A-Za-z]{1,2}", sym)):
            continue
        candidate = str(seed.get("candidate", "")).strip()
        if not candidate:
            continue
        allow_registry_pascal_scope = bool(re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", candidate))
        if not (
            re.fullmatch(cfg.candidate_regex, candidate)
            or re.fullmatch(r"^[a-z][A-Za-z0-9]{3,}$", candidate)
            or allow_registry_pascal_scope
        ):
            continue
        ranges = method_ranges_by_file.get(p, [])
        if not ranges:
            continue
        if p not in file_lines_cache:
            src_path = source_root / p
            if not src_path.is_file():
                continue
            raw_text = read_text(src_path)
            file_lines_cache[p] = raw_text.splitlines()
            file_text_cache[p] = raw_text
        lines = file_lines_cache.get(p, [])
        if not lines:
            continue
        matched = 0
        token_pat = re.compile(rf"\b{re.escape(sym)}\b")
        for rg in ranges:
            l1 = int(rg.get("line_start", 0) or 0)
            l2 = int(rg.get("line_end", l1) or l1)
            if l1 <= 0:
                continue
            segment = "\n".join(lines[max(0, l1 - 1) : min(len(lines), l2)])
            if not token_pat.search(segment):
                continue
            entity_name = str(rg.get("entity_name", "")).strip()
            skey = (p, sym, entity_name, l1, max(l1, l2), candidate)
            if skey in scope_uniq:
                continue
            scope_uniq.add(skey)
            matched += 1
            scope_items.append(
                {
                    "file": p,
                    "symbol": sym,
                    "candidate": candidate,
                    "entity_name": entity_name,
                    "entity_type": str(rg.get("entity_type", "method")),
                    "line_start": l1,
                    "line_end": max(l1, l2),
                    "confidence": "high",
                    "bridge_calls": [],
                    "evidence_refs": [
                        str(seed.get("evidence_ref", "")),
                        f"{p}#scope_registry:{entity_name}",
                    ],
                    "source": "scope_service_registry_infer",
                }
            )
        if matched <= 0:
            # 兜底：至少记录 registry 定义区间，便于后续诊断。
            l1 = int(seed.get("line", 0) or 0)
            l2 = int(seed.get("line_end", l1) or l1)
            if l1 > 0:
                entity_name = f"registry:{str(seed.get('registry_symbol', ''))}:{l1}-{max(l1, l2)}"
                skey = (p, sym, entity_name, l1, max(l1, l2), candidate)
                if skey not in scope_uniq:
                    scope_uniq.add(skey)
                    scope_items.append(
                        {
                            "file": p,
                            "symbol": sym,
                            "candidate": candidate,
                            "entity_name": entity_name,
                            "entity_type": "registry_object",
                            "line_start": l1,
                            "line_end": max(l1, l2),
                            "confidence": "high",
                            "bridge_calls": [],
                            "evidence_refs": [str(seed.get("evidence_ref", ""))],
                            "source": "scope_service_registry_infer",
                        }
                    )
        # 补充：显式覆盖“声明+注册表映射”所在语句区间，保证 symbol 定义与引用一致替换。
        # 目标是避免只改 K={...} 映射而未改短符号定义，导致可读代码出现未定义标识符。
        full_text = file_text_cache.get(p, "")
        if full_text:
            # 先精确补充“符号声明位”作用域：优先命中 `sym =` 的定义行，
            # 让 registry 映射值与其声明形成闭环，不依赖宽范围语句回溯。
            decl_pat_line = re.compile(rf"(?m)^\s*{re.escape(sym)}\s*=")
            m_decl_line = decl_pat_line.search(full_text)
            if not m_decl_line:
                # 兼容压缩/拼接场景：同一行链式声明里可能是 `, sym = ...`
                decl_pat_inline = re.compile(rf"(?:^|,)\s*{re.escape(sym)}\s*=")
                m_decl_line = decl_pat_inline.search(full_text)
            if m_decl_line:
                decl_line = full_text.count("\n", 0, m_decl_line.start()) + 1
                entity_name = f"registry_symbol_decl:{str(seed.get('registry_symbol', ''))}:{sym}:{decl_line}"
                skey = (p, sym, entity_name, decl_line, decl_line, candidate)
                if skey not in scope_uniq:
                    scope_uniq.add(skey)
                    scope_items.append(
                        {
                            "file": p,
                            "symbol": sym,
                            "candidate": candidate,
                            "entity_name": entity_name,
                            "entity_type": "registry_symbol_decl",
                            "line_start": decl_line,
                            "line_end": decl_line,
                            "confidence": "high",
                            "bridge_calls": [],
                            "evidence_refs": [
                                str(seed.get("evidence_ref", "")),
                                f"{p}#registry_symbol_decl:{entity_name}",
                            ],
                            "source": "scope_service_registry_infer",
                        }
                    )
            line_num = int(seed.get("line", 0) or 0)
            if line_num > 0:
                line_starts = [0]
                for m in re.finditer(r"\n", full_text):
                    line_starts.append(m.end())
                if 1 <= line_num <= len(line_starts):
                    line_offset = line_starts[line_num - 1]
                    # 旧逻辑按“最近 const/let/var”回溯，容易落到对象字面量内部局部声明，
                    # 导致 registry_decl 只覆盖半段，出现“映射已改、声明未改”的半闭环。
                    # 新逻辑优先按语句边界回溯：从当前行回看最近分号，覆盖同一声明语句链。
                    prev_semi = full_text.rfind(";", 0, line_offset)
                    stmt_start = prev_semi + 1 if prev_semi >= 0 else 0
                    while stmt_start < len(full_text) and full_text[stmt_start] in {" ", "\t", "\r", "\n"}:
                        stmt_start += 1
                    semicolon = full_text.find(";", line_offset)
                    stmt_end = semicolon if semicolon >= 0 else len(full_text) - 1
                    decl_l1 = full_text.count("\n", 0, stmt_start) + 1
                    decl_l2 = full_text.count("\n", 0, stmt_end) + 1
                    if decl_l1 > 0 and decl_l2 >= decl_l1:
                        entity_name = f"registry_decl:{str(seed.get('registry_symbol', ''))}:{decl_l1}-{decl_l2}"
                        skey = (p, sym, entity_name, decl_l1, decl_l2, candidate)
                        if skey not in scope_uniq:
                            scope_uniq.add(skey)
                            scope_items.append(
                                {
                                    "file": p,
                                    "symbol": sym,
                                    "candidate": candidate,
                                    "entity_name": entity_name,
                                    "entity_type": "registry_decl",
                                    "line_start": decl_l1,
                                    "line_end": decl_l2,
                                    "confidence": "high",
                                    "bridge_calls": [],
                                    "evidence_refs": [
                                        str(seed.get("evidence_ref", "")),
                                        f"{p}#registry_decl:{entity_name}",
                                    ],
                                    "source": "scope_service_registry_infer",
                                }
                            )
    scope_items.sort(key=lambda x: (x["file"], x["line_start"], x["line_end"], x["symbol"], x["candidate"]))
    write_json(paths.analysis / "scope_rename_candidates.json", {"run_id": run_id, "count": len(scope_items), "items": scope_items})

    # restore_priority_queue：把文件优先级、实体、链路置信度、UI流证据融合成可执行还原队列。
    queue_map: dict[tuple[str, str], dict[str, Any]] = {}
    for c in chain_obj.get("items", []):
        file_path = str(c.get("file", ""))
        ent = c.get("entity", {}) if isinstance(c.get("entity"), dict) else {}
        ent_name = str(ent.get("name", "__unknown__"))
        ent_type = str(ent.get("type", "unknown"))
        key = (file_path, ent_name)
        cur = queue_map.get(
            key,
            {
                "file": file_path,
                "entity_name": ent_name,
                "entity_type": ent_type,
                "restore_priority": str(c.get("restore_priority", "low")),
                "chain_count": 0,
                "high_conf_count": 0,
                "bridge_calls": set(),
                "ui_refs": set(),
                "state_ops": set(),
                "ui_entry_hits": set(),
                "ui_chain_count": 0,
                "ui_flow_score": 0,
                "line_min": int(ent.get("line", 0) or 0),
            },
        )
        cur["chain_count"] += 1
        if str(c.get("confidence", "low")) == "high":
            cur["high_conf_count"] += 1
        for b in c.get("bridge_calls", []):
            cur["bridge_calls"].add(str(b))
        for u in c.get("ui_refs", []):
            cur["ui_refs"].add(str(u))
        for s in c.get("state_ops", []):
            cur["state_ops"].add(str(s))
        for h in c.get("ui_entry_hits", []):
            cur["ui_entry_hits"].add(str(h))
        uis = int(c.get("ui_flow_score", 0) or 0)
        cur["ui_flow_score"] += uis
        if uis > 0 or str(c.get("trigger", "")) == "ui_event":
            cur["ui_chain_count"] += 1
        queue_map[key] = cur

    queue_items: list[dict[str, Any]] = []
    for _, q in queue_map.items():
        p_rank = {"high": 3, "medium": 2, "low": 1}.get(str(q["restore_priority"]), 0)
        file_name_low = str(q["file"]).lower()
        helper_penalty = 0
        if any(x in file_name_low for x in ("vue_export_helper", "_plugin-", "naive-ui", "runtime", "vendor")):
            helper_penalty = 420
        score = p_rank * 100 + int(q["high_conf_count"]) * 10 + int(q["chain_count"]) + int(q["ui_flow_score"]) * 3 + int(q["ui_chain_count"]) * 5 - helper_penalty
        queue_items.append(
            {
                "file": q["file"],
                "entity_name": q["entity_name"],
                "entity_type": q["entity_type"],
                "line_min": q["line_min"],
                "restore_priority": q["restore_priority"],
                "chain_count": q["chain_count"],
                "high_conf_count": q["high_conf_count"],
                "bridge_calls": sorted(q["bridge_calls"]),
                "ui_refs": sorted(q["ui_refs"]),
                "state_ops": sorted(q["state_ops"]),
                "ui_entry_hits": sorted(q["ui_entry_hits"]),
                "ui_chain_count": int(q["ui_chain_count"]),
                "ui_flow_score": int(q["ui_flow_score"]),
                "helper_penalty": int(helper_penalty),
                "score": score,
            }
        )
    queue_items.sort(key=lambda x: (-int(x["score"]), x["file"], x["line_min"], x["entity_name"]))
    write_json(paths.analysis / "restore_priority_queue.json", {"run_id": run_id, "count": len(queue_items), "items": queue_items})
    mdq = [
        "# Restore Priority Queue",
        "",
        f"- run_id: `{run_id}`",
        f"- items: `{len(queue_items)}`",
        "",
        "| Score | Priority | File | Entity | Type | Chains(high/total) | UI(chains/score) | BridgeCalls |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for it in queue_items[:300]:
        mdq.append(
            f"| {it['score']} | {it['restore_priority']} | {it['file']} | {it['entity_name']} | {it['entity_type']} | {it['high_conf_count']}/{it['chain_count']} | {it['ui_chain_count']}/{it['ui_flow_score']} | {','.join(it['bridge_calls'][:3])} |"
        )
    write_text(paths.analysis / "restore_priority_queue.md", "\n".join(mdq))

    # entity_restore_batch_{1,2,3}：分层候选池切片（实体优先 -> 高置信已通过 -> 中置信已通过）。
    file_score: dict[str, int] = {}
    for q in queue_items:
        f = str(q.get("file", ""))
        sc = int(q.get("score", 0))
        file_score[f] = max(file_score.get(f, 0), sc)

    candidate_pool: list[dict[str, Any]] = []
    service_facade_priority_items: list[dict[str, Any]] = []
    for i in rename_plan_items:
        f = str(i.get("file", ""))
        sname = str(i.get("symbol", ""))
        cand = str(i.get("candidate", ""))
        src = str(i.get("source", ""))
        conf = str(i.get("confidence", "low"))
        reasons = [str(x) for x in i.get("reasons", [])]
        evidence_refs = [str(x) for x in i.get("evidence_refs", [])]
        is_service_registry_ref = any("#service_registry:" in r for r in evidence_refs)
        if not f or not sname or not cand:
            continue
        if any(r.startswith("symbol_multi_candidates:") and r != "symbol_multi_candidates:1" for r in reasons):
            continue
        if "candidate_prefix_not_whitelisted" in reasons or "candidate_generic" in reasons or "candidate_hits_forbidden_tokens" in reasons:
            continue

        tier = 0
        reason = ""
        if is_service_registry_ref and bool(i.get("apply")) and conf == "high":
            tier = 1
            reason = "service_facade_registry_high_apply"
        elif src == "entity_chain_infer" and conf in {"high", "medium"}:
            tier = 1
            reason = "entity_chain_infer_priority"
        elif src == "constant_enum_infer" and bool(i.get("apply")) and conf == "high":
            tier = 1
            reason = "constant_enum_high_apply"
        elif src == "constant_class_anchor" and bool(i.get("apply")) and conf == "high":
            tier = 2
            reason = "constant_class_anchor_high_apply"
        elif src == "method_logger_class_infer" and bool(i.get("apply")) and conf == "high":
            tier = 2
            reason = "method_logger_class_high_apply"
        elif src == "method_business_flow_infer" and bool(i.get("apply")) and conf == "high":
            tier = 2
            reason = "method_business_flow_high_apply"
        elif src == "pair_semantic" and bool(i.get("apply")) and conf == "high":
            tier = 2
            reason = "pair_semantic_high_apply"
        elif src == "pair_semantic" and bool(i.get("apply")) and conf == "medium":
            tier = 3
            reason = "pair_semantic_medium_apply"
        elif src == "pair_semantic" and (not bool(i.get("apply"))) and conf == "high":
            tier = 4
            reason = "pair_semantic_high_review_only"
        elif src == "pair_semantic" and (not bool(i.get("apply"))) and conf == "medium":
            tier = 5
            reason = "pair_semantic_medium_review_only"
        else:
            continue

        candidate_pool.append(
            {
                "file": f,
                "symbol": sname,
                "candidate": cand,
                "confidence": conf,
                "source": src,
                "reason": reason,
                "evidence_refs": evidence_refs,
                "tier": tier,
                "file_score": file_score.get(f, 0),
                "force_apply": tier <= 3,
            }
        )
        if is_service_registry_ref:
            service_facade_priority_items.append(
                {
                    "file": f,
                    "symbol": sname,
                    "candidate": cand,
                    "confidence": conf,
                    "source": src,
                    "reason": reason,
                    "tier": tier,
                    "apply": bool(i.get("apply")),
                    "file_score": file_score.get(f, 0),
                    "evidence_refs": evidence_refs[:6],
                }
            )

    # 去重 + 排序
    uniq_pool: dict[tuple[str, str, str], dict[str, Any]] = {}
    for it in candidate_pool:
        key = (it["file"], it["symbol"], it["candidate"])
        old = uniq_pool.get(key)
        if old is None:
            uniq_pool[key] = it
            continue
        old_rank = (int(old.get("tier", 9)), -int(old.get("file_score", 0)))
        new_rank = (int(it.get("tier", 9)), -int(it.get("file_score", 0)))
        if new_rank < old_rank:
            uniq_pool[key] = it
    pool = list(uniq_pool.values())
    pool.sort(key=lambda x: (int(x.get("tier", 9)), -int(x.get("file_score", 0)), x["file"], x["symbol"]))
    if service_facade_priority_items:
        service_facade_priority_items.sort(
            key=lambda x: (int(x.get("tier", 9)), -int(x.get("file_score", 0)), str(x.get("file", "")), str(x.get("symbol", "")))
        )
        write_json(
            paths.analysis / "service_facade_priority.json",
            {"run_id": run_id, "count": len(service_facade_priority_items), "items": service_facade_priority_items},
        )
        md = [
            "# Service Facade Priority",
            "",
            f"- run_id: `{run_id}`",
            f"- count: `{len(service_facade_priority_items)}`",
            "",
            "| Tier | File | Symbol | Candidate | Source | Confidence | Apply |",
            "|---:|---|---|---|---|---|---|",
        ]
        for it in service_facade_priority_items[:200]:
            md.append(
                f"| {it.get('tier',9)} | {it.get('file','')} | {it.get('symbol','')} | {it.get('candidate','')} | {it.get('source','')} | {it.get('confidence','')} | {it.get('apply',False)} |"
            )
        write_text(paths.analysis / "service_facade_priority.md", "\n".join(md))

    batch_sizes = {1: 4, 2: 4, 3: 4}
    idx = 0
    for batch_no in (1, 2, 3):
        batch_items = []
        size = int(batch_sizes[batch_no])
        while idx < len(pool) and len(batch_items) < size:
            it = pool[idx]
            idx += 1
            b = dict(it)
            b["reason"] = f"{b['reason']}_batch_{batch_no}"
            batch_items.append(b)

        write_json(
            paths.analysis / f"entity_restore_batch_{batch_no}.json",
            {
                "run_id": run_id,
                "batch_no": batch_no,
                "count": len(batch_items),
                "items": batch_items,
            },
        )
        mdb = [
            f"# Entity Restore Batch {batch_no}",
            "",
            f"- run_id: `{run_id}`",
            f"- item_count: `{len(batch_items)}`",
            "",
            "| File | Symbol | Candidate | Confidence | Source | Tier | ForceApply | Reason |",
            "|---|---|---|---|---|---:|---|---|",
        ]
        for it in batch_items:
            mdb.append(
                f"| {it['file']} | {it['symbol']} | {it['candidate']} | {it['confidence']} | {it['source']} | {it['tier']} | {it.get('force_apply', False)} | {it['reason']} |"
            )
        write_text(paths.analysis / f"entity_restore_batch_{batch_no}.md", "\n".join(mdb))

    evidence_items: list[dict[str, Any]] = []
    for item in origin_obj.get("items", []):
        evidence_items.append(
            {
                "id": f"EVID_ORIGIN_{len(evidence_items)+1:04d}",
                "guess": f"{item['file']} -> {item['origin_label']}",
                "evidence": item["signals"],
                "verification": item["status"],
                "confidence": item["confidence"],
            }
        )
    for item in chain_obj.get("items", []):
        evidence_items.append(
            {
                "id": f"EVID_CHAIN_{len(evidence_items)+1:04d}",
                "guess": f"{item['chain_id']} trigger={item['trigger']}",
                "evidence": item["bridge_calls"] + item["ui_refs"] + item["state_ops"],
                "verification": "verified" if item["confidence"] == "high" else "guessed",
                "confidence": item["confidence"],
            }
        )
    write_json(paths.analysis / "evidence_matrix.json", {"run_id": run_id, "count": len(evidence_items), "items": evidence_items})

    md = [
        "# Evidence Matrix",
        "",
        f"- run_id: `{run_id}`",
        f"- evidence_count: `{len(evidence_items)}`",
        "",
        "| ID | Guess | Evidence | Verification | Confidence |",
        "|---|---|---|---|---|",
    ]
    for e in evidence_items[:300]:
        ev = ", ".join(map(str, e["evidence"][:5])) if isinstance(e["evidence"], list) else str(e["evidence"])
        md.append(f"| {e['id']} | {e['guess']} | {ev} | {e['verification']} | {e['confidence']} |")
    write_text(paths.analysis / "evidence_matrix.md", "\n".join(md))
