from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from restorex_lib.config_rules import load_json_if_exists
from restorex_lib.fs_utils import collect_files, read_text, rel, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def cmd_restore_v1(
    workspace: Path,
    run_id: str,
    cfg: Any,
    emit_raw_runtime: bool = False,
    *,
    safe_symbol_replace: Callable[[str, str, str], tuple[str, int]],
    try_external_format: Callable[[str, str, str], tuple[str, str]],
    normalize_code_text: Callable[[str, str], str],
    run_scope_rename_pass: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]],
) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    symbol_path = paths.analysis / "symbol_map_seed.json"
    scope_path = paths.analysis / "scope_rename_candidates.json"
    batch_files = sorted(paths.analysis.glob("entity_restore_batch_*.json"), key=lambda p: p.name)
    if not symbol_path.is_file():
        raise SystemExit("E_RUNTIME: run build-evidence first")
    symbols_obj = json.loads(read_text(symbol_path))
    symbol_items = symbols_obj.get("items", [])
    module_rules = load_json_if_exists(workspace / "cache" / "remote" / "module_rules.json")
    # 项目特定配置从 project_hints.json 读取，兼容旧版回退到 module_rules.json
    project_hints = load_json_if_exists(workspace / "cache" / "project" / "project_hints.json")
    _note_targets = project_hints.get("module_restore_note_targets") or module_rules.get("module_restore_note_targets")
    note_target_prefixes = tuple(
        str(x).strip()
        for x in (_note_targets if isinstance(_note_targets, list) else [])
        if str(x).strip()
    )
    _guard_targets = project_hints.get("single_char_business_flow_guard_targets") or module_rules.get("single_char_business_flow_guard_targets")
    single_char_guard_prefixes = tuple(
        str(x).strip()
        for x in (_guard_targets if isinstance(_guard_targets, list) else [])
        if str(x).strip()
    ) or ("assets/main-",)
    scope_items = []
    if scope_path.is_file():
        try:
            scope_items = json.loads(read_text(scope_path)).get("items", [])
        except Exception:
            scope_items = []
    scope_by_file_symbol: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in scope_items:
        f = str(it.get("file", "")).strip()
        s = str(it.get("symbol", "")).strip()
        if not f or not s:
            continue
        scope_by_file_symbol.setdefault((f, s), []).append(it)
    skip_global_consolidated: set[tuple[str, str]] = set()
    for fs, arr in scope_by_file_symbol.items():
        cand_set = {str(i.get("candidate", "")).strip() for i in arr if str(i.get("candidate", "")).strip()}
        ent_set = {str(i.get("entity_name", "")).strip() for i in arr if str(i.get("entity_name", "")).strip()}
        if len(cand_set) > 1 or len(ent_set) > 1:
            skip_global_consolidated.add(fs)
    batch_force_keys = set()
    for bf in batch_files:
        try:
            batch_obj = json.loads(read_text(bf))
        except Exception:
            continue
        for i in batch_obj.get("items", []):
            key = (str(i.get("file", "")), str(i.get("symbol", "")), str(i.get("candidate", "")))
            if key[0] and key[1] and key[2] and bool(i.get("force_apply", False)):
                batch_force_keys.add(key)

    raw_runtime = paths.restore_v1 / "raw_runtime"
    readable = paths.restore_v1 / "readable"
    if raw_runtime.exists():
        shutil.rmtree(raw_runtime)
    if readable.exists():
        shutil.rmtree(readable)
    if emit_raw_runtime:
        shutil.copytree(raw_snapshot, raw_runtime)
    shutil.copytree(source_root, readable)

    global_source_allowlist = {str(x).strip() for x in getattr(cfg, "global_apply_sources_allowlist", ()) if str(x).strip()}

    applied_renames: list[dict[str, Any]] = []
    blocked_suspicious_renames: list[dict[str, Any]] = []
    for f in collect_files(readable, {".js"}):
        rel_file = rel(f, readable)
        text = read_text(f)
        changed = False
        for s in symbol_items:
            rel_key = (rel_file, str(s.get("symbol", "")).strip(), str(s.get("candidate", "")).strip())
            force_apply = rel_key in batch_force_keys
            if not s.get("apply") and not force_apply:
                continue
            symbol_file = str(s.get("file", "")).strip()
            if symbol_file and symbol_file != rel_file:
                continue
            short = str(s.get("symbol", "")).strip()
            candidate = str(s.get("candidate", "")).strip()
            source = str(s.get("source", "unknown")).strip()
            evidence_refs = [str(x) for x in (s.get("evidence_refs", []) or []) if str(x).strip()]
            # 全局替换只允许低风险来源；pair_semantic 等语义猜测来源只走 scoped pass，防止跨上下文污染。
            # 即使在 batch 中 force_apply，也不允许越过此来源白名单。
            if source not in global_source_allowlist:
                continue
            if source == "chain_call_symbol_consolidated" and (rel_file, short) in skip_global_consolidated and not force_apply:
                continue
            if not short or not candidate or short == candidate:
                continue
            allow_const_short = bool(
                source in {
                    "constant_enum_infer",
                    "constant_class_anchor",
                    "method_logger_class_infer",
                    "method_business_flow_infer",
                    "pinia_store_infer",
                    "vue_sfc_component_infer",
                }
                and re.fullmatch(r"[A-Za-z]{1,2}", short)
            )
            # pair_semantic medium 置信 + 白名单前缀 + 两字符符号（含大写开头）放行
            allow_medium_pair_two_char_restore = bool(
                getattr(cfg, "allow_pair_semantic_medium_prefix_two_char", False)
                and source == "pair_semantic"
                and confidence == "medium"
                and re.fullmatch(r"[A-Za-z]{2}", short)
                and candidate.startswith(cfg.auto_rename_prefixes)
                and len(candidate) >= 6
            )
            # pair_semantic 高置信唯一映射的 PascalCase 服务对象（如 At→Config, Ct→Shell）
            # 在开启 allow_pascal_short_service_rename 时允许通过短符号过滤
            allow_pascal_service = bool(
                getattr(cfg, "allow_pascal_short_service_rename", False)
                and source == "pair_semantic"
                and re.fullmatch(r"[A-Za-z]{1,2}", short)
                and re.fullmatch(r"[A-Z][a-zA-Z]{2,}", candidate)
            )
            if len(short) > 2 or (not re.fullmatch(cfg.short_name_regex, short) and not allow_const_short and not allow_pascal_service and not allow_medium_pair_two_char_restore):
                continue
            if any(token in candidate for token in cfg.forbidden_rename_tokens):
                continue
            if candidate in cfg.generic_candidates:
                continue
            estimated = len(re.findall(rf"\b{re.escape(short)}\b", text))
            # 极值保护：单字符业务流全局替换达到极高次数时直接阻断，
            # 即使存在 flow_cmd 证据，也优先避免大文件中的跨语义污染。
            if (
                source == "method_business_flow_infer"
                and len(short) <= 1
                and estimated >= 50
            ):
                blocked_suspicious_renames.append(
                    {
                        "file": rel_file,
                        "from": short,
                        "to": candidate,
                        "estimated_replace_count": estimated,
                        "reason": "business_flow_single_char_extreme_replacement_blocked",
                    }
                )
                continue
            # 精度保护：method_business_flow_infer 在超高命中场景下，必须带 flow_cmd 证据才允许全局替换。
            # 目的：避免 main-* 这类长文件里 1 字符变量被过度替换；不影响后续 scope pass 的局部替换。
            if (
                source == "method_business_flow_infer"
                and len(short) <= 1
                and any(rel_file.startswith(pref) for pref in single_char_guard_prefixes)
                and estimated >= 15
                and not any(ref.startswith("flow_cmd:") for ref in evidence_refs)
            ):
                blocked_suspicious_renames.append(
                    {
                        "file": rel_file,
                        "from": short,
                        "to": candidate,
                        "estimated_replace_count": estimated,
                        "reason": "business_flow_no_flow_cmd_high_replacement_blocked",
                    }
                )
                continue
            if (
                cfg.block_suspicious_rename
                and len(short) <= max(0, cfg.suspicious_short_len_max)
                and estimated >= max(1, cfg.suspicious_replace_count_threshold)
            ):
                blocked_suspicious_renames.append(
                    {
                        "file": rel_file,
                        "from": short,
                        "to": candidate,
                        "estimated_replace_count": estimated,
                        "reason": "short_symbol_high_replacement_blocked",
                    }
                )
                continue
            new_text, n = safe_symbol_replace(text, short, candidate)
            if n > 0:
                text = new_text
                changed = True
                applied_renames.append(
                    {
                        "file": rel_file,
                        "from": short,
                        "to": candidate,
                        "replace_count": n,
                        "source": source,
                        "evidence_refs": evidence_refs,
                    }
                )
        if changed:
            write_text(f, text)

    preferred_targets_by_file: dict[str, set[str]] = {}
    for ren in applied_renames:
        f = str(ren.get("file", ""))
        t = str(ren.get("to", ""))
        if not f or not t:
            continue
        preferred_targets_by_file.setdefault(f, set()).add(t)
    scope_applied_renames, scope_skipped_groups = run_scope_rename_pass(
        readable, paths, cfg, preferred_targets_by_file=preferred_targets_by_file
    )
    applied_scope_keys = {
        (str(x.get("file", "")), str(x.get("from", "")), str(x.get("to", "")))
        for x in scope_applied_renames
        if str(x.get("file", "")).strip() and str(x.get("from", "")).strip() and str(x.get("to", "")).strip()
    }
    scope_resolution_items: list[dict[str, Any]] = []
    unresolved_scope_only: list[dict[str, Any]] = []
    seen_scope_only_keys: set[tuple[str, str, str]] = set()
    for it in symbol_items:
        if not bool(it.get("dedupe_scope_only", False)):
            continue
        f = str(it.get("file", "")).strip()
        s = str(it.get("symbol", "")).strip()
        c = str(it.get("candidate", "")).strip()
        if not f or not s or not c:
            continue
        fsc = (f, s, c)
        if fsc in seen_scope_only_keys:
            continue
        seen_scope_only_keys.add(fsc)
        scope_group = scope_by_file_symbol.get((f, s), [])
        has_scope_exact = any(str(x.get("candidate", "")).strip() == c for x in scope_group)
        if fsc in applied_scope_keys:
            reason = "scope_candidate_applied"
        elif not has_scope_exact:
            reason = "scope_candidate_not_generated"
        else:
            reason = "scope_candidate_generated_but_not_applied"
        item = {
            "file": f,
            "symbol": s,
            "candidate": c,
            "source": str(it.get("source", "")),
            "confidence": str(it.get("confidence", "low")),
            "reason": reason,
            "evidence_refs": list(it.get("evidence_refs", [])),
        }
        scope_resolution_items.append(item)
        if reason != "scope_candidate_applied":
            unresolved_scope_only.append(item)
    scope_applied_from_dedupe_scope_only = sum(1 for x in scope_resolution_items if str(x.get("reason", "")) == "scope_candidate_applied")
    scope_unapplied_count = len(unresolved_scope_only)

    # readable 末尾再做一次格式化，保证“最终可读产物”而不是仅在 baseline 可读。
    final_format_stats = {
        "targets": 0,
        "changed": 0,
        "by_ext": {".js": 0, ".css": 0, ".html": 0},
        "by_formatter": {"prettier": 0, "js-beautify": 0, "none": 0},
        "none_files": [],
    }
    for f in collect_files(readable, {".js", ".css", ".html"}):
        rel_path = rel(f, readable)
        ext = f.suffix.lower()
        raw_text = read_text(f)
        ext_text, formatter = try_external_format(ext, raw_text, rel_path)
        out_text = normalize_code_text(ext, ext_text)
        final_format_stats["targets"] += 1
        final_format_stats["by_ext"][ext] = int(final_format_stats["by_ext"].get(ext, 0)) + 1
        final_format_stats["by_formatter"][formatter] = int(final_format_stats["by_formatter"].get(formatter, 0)) + 1
        if formatter == "none":
            final_format_stats["none_files"].append(rel_path)
        if out_text != raw_text:
            write_text(f, out_text)
            final_format_stats["changed"] += 1

    mapping_items = []
    for f in collect_files(raw_snapshot):
        rp = rel(f, raw_snapshot)
        if (readable / rp).is_file():
            mapping_items.append({"raw_path": rp, "readable_path": rp})
    mapping_index = {
        "run_id": run_id,
        "path_map_count": len(mapping_items),
        "path_map": mapping_items,
        "applied_renames": applied_renames,
        "scope_applied_renames": scope_applied_renames,
        "scope_skipped_groups": scope_skipped_groups,
        "scope_resolution_dedupe_scope_only": scope_resolution_items,
        "scope_unresolved_dedupe_scope_only": unresolved_scope_only,
        "scope_applied_from_dedupe_scope_only": scope_applied_from_dedupe_scope_only,
        "scope_unapplied_count": scope_unapplied_count,
        "blocked_suspicious_renames": blocked_suspicious_renames,
        "suspicious_policy": {
            "block_in_apply": cfg.block_suspicious_rename,
            "short_len_max": cfg.suspicious_short_len_max,
            "replace_count_threshold": cfg.suspicious_replace_count_threshold,
        },
        "global_apply_sources_allowlist": sorted(global_source_allowlist),
        "final_readable_format": final_format_stats,
        "emit_raw_runtime": emit_raw_runtime,
    }
    write_json(paths.analysis / "mapping_index.json", mapping_index)
    write_json(
        paths.analysis / "scope_unapplied_candidates.json",
        {
            "run_id": run_id,
            "count": len(unresolved_scope_only),
            "items": unresolved_scope_only,
        },
    )
    write_json(
        paths.analysis / "scope_candidate_resolution.json",
        {
            "run_id": run_id,
            "count": len(scope_resolution_items),
            "scope_applied_from_dedupe_scope_only": scope_applied_from_dedupe_scope_only,
            "scope_unapplied_count": scope_unapplied_count,
            "items": scope_resolution_items,
        },
    )

    # 业务模块交付说明：记录目标模块每条改名的证据链，便于后续增量还原。
    symbol_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for it in symbol_items:
        key = (str(it.get("file", "")), str(it.get("symbol", "")), str(it.get("candidate", "")))
        if key[0] and key[1] and key[2]:
            symbol_lookup[key] = it
    all_renames = list(applied_renames) + list(scope_applied_renames)
    note_items: list[dict[str, Any]] = []
    for ren in all_renames:
        file_path = str(ren.get("file", ""))
        if not file_path.startswith(note_target_prefixes):
            continue
        symbol = str(ren.get("from", ""))
        candidate = str(ren.get("to", ""))
        src = str(ren.get("source", "unknown"))
        lk = symbol_lookup.get((file_path, symbol, candidate), {})
        note_items.append(
            {
                "file": file_path,
                "symbol": symbol,
                "candidate": candidate,
                "source": src,
                "confidence": str(lk.get("confidence", "unknown")),
                "evidence_refs": list(ren.get("evidence_refs", [])) or list(lk.get("evidence_refs", [])),
                "replace_count": int(ren.get("replace_count", 0) or 0),
            }
        )
    by_file: dict[str, int] = {}
    for it in note_items:
        f = str(it.get("file", ""))
        by_file[f] = by_file.get(f, 0) + 1
    write_json(
        paths.analysis / "module_restore_notes.json",
        {
            "run_id": run_id,
            "count": len(note_items),
            "items": sorted(note_items, key=lambda x: (x["file"], x["symbol"], x["candidate"])),
            "summary_by_file": [{"file": f, "count": c} for f, c in sorted(by_file.items())],
        },
    )


def cmd_apply_scope_renames(
    workspace: Path,
    run_id: str,
    cfg: Any,
    *,
    run_scope_rename_pass: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]],
) -> None:
    """
    对现有 readable 产物执行一次作用域改名增量应用。
    用于在不重跑全流程时，快速验证/迭代 scope 方案。
    """
    paths = run_paths(workspace, run_id)
    readable = paths.restore_v1 / "readable"
    if not readable.is_dir():
        raise SystemExit("E_RUNTIME: run restore-v1 first")
    mapping_path = paths.analysis / "mapping_index.json"
    mapping_obj = json.loads(read_text(mapping_path)) if mapping_path.is_file() else {"run_id": run_id}
    preferred_targets_by_file: dict[str, set[str]] = {}
    for ren in mapping_obj.get("applied_renames", []):
        f = str(ren.get("file", ""))
        t = str(ren.get("to", ""))
        if not f or not t:
            continue
        preferred_targets_by_file.setdefault(f, set()).add(t)
    scope_applied_renames, scope_skipped_groups = run_scope_rename_pass(
        readable, paths, cfg, preferred_targets_by_file=preferred_targets_by_file
    )
    old_scope = mapping_obj.get("scope_applied_renames", [])
    old_skipped = mapping_obj.get("scope_skipped_groups", [])

    seen_scope: set[tuple[str, str, str, int, int]] = set()
    merged_scope: list[dict[str, Any]] = []
    for item in list(old_scope) + list(scope_applied_renames):
        scope = item.get("scope", {}) if isinstance(item.get("scope"), dict) else {}
        key = (
            str(item.get("file", "")),
            str(item.get("from", "")),
            str(item.get("to", "")),
            int(scope.get("line_start", 0) or 0),
            int(scope.get("line_end", 0) or 0),
        )
        if key in seen_scope:
            continue
        seen_scope.add(key)
        merged_scope.append(item)

    seen_skip: set[tuple[str, str, str, int, int]] = set()
    merged_skipped: list[dict[str, Any]] = []
    for item in list(old_skipped) + list(scope_skipped_groups):
        key = (
            str(item.get("file", "")),
            str(item.get("symbol", "")),
            str(item.get("entity_name", "")),
            int(item.get("line_start", 0) or 0),
            int(item.get("line_end", 0) or 0),
        )
        if key in seen_skip:
            continue
        seen_skip.add(key)
        merged_skipped.append(item)

    mapping_obj["scope_applied_renames"] = merged_scope
    mapping_obj["scope_skipped_groups"] = merged_skipped
    write_json(mapping_path, mapping_obj)
