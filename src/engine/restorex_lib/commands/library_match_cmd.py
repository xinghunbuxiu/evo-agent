from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from restorex_lib.config_rules import deep_merge_dict, load_json_if_exists
from restorex_lib.fingerprint_registry import load_fingerprint_registry
from restorex_lib.fs_utils import collect_files, read_text, rel, write_json
from restorex_lib.run_context import ensure_baseline_exists, run_paths
from restorex_lib.commands.structure_cmd import refine_origin_with_library_match


def infer_library_from_filename(file_path: str) -> str:
    low = file_path.lower()
    m = re.search(r"/?([a-z][a-z0-9_-]{2,})-[a-z0-9_-]{6,}\.(js|css)$", low)
    if not m:
        return ""
    name = m.group(1)
    if name in {"main", "index", "vendor", "chunk", "styles", "style", "app"}:
        return ""
    return name


def _default_library_match_rules() -> dict[str, Any]:
    return {
        "structural_evidence_types": [
            "module_signature",
            "export_shape",
            "runtime_helper_pattern",
            "chunk_naming",
            "css_marker",
        ],
        "evidence_type_weights": {
            "module_signature": 2.6,
            "export_shape": 2.2,
            "runtime_helper_pattern": 2.2,
            "chunk_naming": 2.0,
            "css_marker": 1.8,
            "text_markers": 1.0,
        },
        "high_min_structural_types": 2,
        "medium_min_structural_types": 1,
        "block_text_only_libraries": ["naive-ui", "pinia", "react", "vue-i18n", "vuex", "zustand"],
        "library_rules": {},
    }


def _load_library_match_rules(workspace: Path) -> dict[str, Any]:
    defaults = _default_library_match_rules()
    registry = load_fingerprint_registry(workspace)
    defaults["library_rules"] = registry.get("library_match_rules", {}) if isinstance(registry.get("library_match_rules", {}), dict) else {}
    override = load_json_if_exists(workspace / "cache" / "remote" / "library_match_rules.json")
    if not override:
        return defaults
    merged = deep_merge_dict(defaults, override)
    # 基础防御：阈值最低为 1，避免配置误写导致全部降级。
    merged["high_min_structural_types"] = max(1, int(merged.get("high_min_structural_types", 2) or 2))
    merged["medium_min_structural_types"] = max(1, int(merged.get("medium_min_structural_types", 1) or 1))
    return merged


def _match_markers(text_low: str, markers: list[str]) -> list[str]:
    hits: list[str] = []
    for marker in markers:
        mk = str(marker).strip()
        if not mk:
            continue
        if mk.lower() in text_low:
            hits.append(mk)
    return sorted(set(hits))


def _collect_candidate(file_path: str, text: str, lib: str, rule: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    text_low = text.lower()
    inferred_name = infer_library_from_filename(file_path)
    compact_low = re.sub(r"\s+", "", text_low)

    evidence_by_type: dict[str, list[str]] = {}

    hints = [str(x).lower() for x in (rule.get("filename_hints", []) if isinstance(rule.get("filename_hints", []), list) else [])]
    if inferred_name and (inferred_name == lib or inferred_name in hints):
        evidence_by_type.setdefault("chunk_naming", []).append(inferred_name)

    for etype in ("module_signature", "export_shape", "runtime_helper_pattern", "css_marker", "text_markers"):
        markers = rule.get(etype, [])
        if not isinstance(markers, list):
            continue
        hits = _match_markers(text_low, [str(x) for x in markers])
        if hits:
            evidence_by_type.setdefault(etype, []).extend(hits)

    # Pinia 特征补强：即使 defineStore 被压缩成短函数名，也能通过结构签名识别。
    pinia_strong_signal = False
    if lib == "pinia":
        has_store_shape = bool(
            re.search(r"[a-z_$][\w$]*\([\"'][^\"']+[\"'],\{state:\(\)=>\(\{", compact_low)
            and "getters:{" in compact_low
            and "actions:{" in compact_low
        )
        if has_store_shape:
            pinia_strong_signal = True
            evidence_by_type.setdefault("module_signature", []).append("store_signature:state_getters_actions")
        if "createpinia(" in compact_low or "definestore(" in compact_low:
            pinia_strong_signal = True
            evidence_by_type.setdefault("runtime_helper_pattern", []).append("pinia_runtime_helper")

    if not evidence_by_type:
        return None

    evidence_types = sorted(evidence_by_type.keys())
    block_text_only = {
        str(x).strip().lower()
        for x in (cfg.get("block_text_only_libraries", []) if isinstance(cfg.get("block_text_only_libraries", []), list) else [])
        if str(x).strip()
    }
    # 对易误判库，纯 text_markers 命中不进入候选。
    if lib.lower() in block_text_only and evidence_types == ["text_markers"]:
        return None

    # 仅靠 $patch 等弱信号容易误判，Pinia 必须有强结构信号才进入候选。
    if lib == "pinia" and not pinia_strong_signal:
        return None

    weights = cfg.get("evidence_type_weights", {})
    structural_types = set(str(x) for x in cfg.get("structural_evidence_types", []))
    structural_hits = sorted([x for x in evidence_types if x in structural_types])
    structural_count = len(structural_hits)

    score = 0.0
    evidence_lines: list[str] = []
    for etype in evidence_types:
        detail_hits = sorted(set(str(x) for x in evidence_by_type.get(etype, []) if str(x).strip()))
        # 每种证据类型最多计入 2 个细节，避免单类 marker 过多导致偏斜。
        hit_factor = min(2, len(detail_hits))
        weight = float(weights.get(etype, 1.0))
        score += weight * hit_factor
        evidence_lines.append(f"{etype}:{','.join(detail_hits[:4])}")

    medium_min_struct = int(cfg.get("medium_min_structural_types", 1) or 1)
    base_conf = "low"
    if structural_count >= medium_min_struct:
        # 结构证据优先：只要结构信号达标，至少中置信；文本证据用于补强。
        base_conf = "medium"
    elif evidence_types == ["text_markers"]:
        base_conf = "low"

    consistency_score = 0
    if "chunk_naming" in evidence_by_type:
        consistency_score += 1
    if "module_signature" in evidence_by_type:
        consistency_score += 1
    if "runtime_helper_pattern" in evidence_by_type:
        consistency_score += 1

    kind = "framework_runtime" if lib in {"vue", "react", "svelte", "pinia"} else "vendor_library"
    return {
        "file": file_path,
        "library": lib,
        "kind": kind,
        "base_confidence": base_conf,
        "evidence": sorted(evidence_lines),
        "evidence_types": evidence_types,
        "evidence_score": round(score, 3),
        "structural_evidence_count": structural_count,
        "consistency_score": consistency_score,
    }


def _confidence_rank(conf: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(conf), 0)


def _resolve_file_conflicts(candidates: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    structural_types = set(str(x) for x in cfg.get("structural_evidence_types", []))
    high_min_struct = int(cfg.get("high_min_structural_types", 2) or 2)

    for item in candidates:
        item["structural_types"] = [x for x in item.get("evidence_types", []) if x in structural_types]

    ranked = sorted(
        candidates,
        key=lambda x: (
            int(x.get("structural_evidence_count", 0)),
            float(x.get("evidence_score", 0.0)),
            _confidence_rank(str(x.get("base_confidence", "low"))),
            int(x.get("consistency_score", 0)),
            str(x.get("library", "")),
        ),
        reverse=True,
    )
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    top_key = (
        int(top.get("structural_evidence_count", 0)),
        float(top.get("evidence_score", 0.0)),
        _confidence_rank(str(top.get("base_confidence", "low"))),
        int(top.get("consistency_score", 0)),
    )
    second_key = (
        int(second.get("structural_evidence_count", 0)),
        float(second.get("evidence_score", 0.0)),
        _confidence_rank(str(second.get("base_confidence", "low"))),
        int(second.get("consistency_score", 0)),
    ) if second else None

    top_is_unique = second is None or top_key > second_key
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(ranked):
        obj = dict(item)
        obj["is_primary_match"] = idx == 0
        if idx == 0:
            if int(obj.get("structural_evidence_count", 0)) >= high_min_struct and top_is_unique:
                obj["confidence"] = "high"
                obj["decision_reason"] = "primary_by_structural_evidence_unique"
            elif int(obj.get("structural_evidence_count", 0)) >= 1:
                obj["confidence"] = "medium"
                obj["decision_reason"] = "primary_by_conflict_resolution"
            else:
                obj["confidence"] = str(obj.get("base_confidence", "low"))
                obj["decision_reason"] = "primary_with_text_evidence_only"
        else:
            obj["confidence"] = "medium" if str(obj.get("base_confidence", "low")) == "high" else str(obj.get("base_confidence", "low"))
            obj["decision_reason"] = "non_primary_conflict_candidate"
        obj["status"] = "verified" if str(obj["confidence"]) == "high" else "guessed"
        out.append(obj)
    return out


def _calc_quality(match_items: list[dict[str, Any]], origin_by_file: dict[str, str], files_scanned: int) -> dict[str, Any]:
    confidence_dist_all = Counter(str(x.get("confidence", "low")) for x in match_items)
    primary_items = [x for x in match_items if bool(x.get("is_primary_match", False))]
    metric_items = primary_items if primary_items else match_items
    confidence_dist = Counter(str(x.get("confidence", "low")) for x in metric_items)
    text_only_count = sum(1 for x in metric_items if sorted(x.get("evidence_types", [])) == ["text_markers"])
    high_conf_count = int(confidence_dist.get("high", 0))

    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in match_items:
        by_file[str(it.get("file", ""))].append(it)

    conflict_files = [f for f, items in by_file.items() if len(items) > 1]
    resolved = 0
    unresolved = 0
    for f in conflict_files:
        prim_count = sum(1 for x in by_file[f] if bool(x.get("is_primary_match", False)))
        if prim_count == 1:
            resolved += 1
        else:
            unresolved += 1

    by_library: dict[str, dict[str, int]] = {}
    for it in match_items:
        lib = str(it.get("library", "unknown"))
        by_library.setdefault(lib, {"high": 0, "medium": 0, "low": 0, "total": 0})
        conf = str(it.get("confidence", "low"))
        by_library[lib][conf if conf in {"high", "medium", "low"} else "low"] += 1
        by_library[lib]["total"] += 1

    unknown_files_count = sum(1 for _, v in origin_by_file.items() if str(v) == "unknown")
    total = max(1, len(metric_items))
    return {
        "count": len(match_items),
        "primary_count": len(primary_items),
        "files_scanned": files_scanned,
        "confidence_distribution": {
            "high": int(confidence_dist.get("high", 0)),
            "medium": int(confidence_dist.get("medium", 0)),
            "low": int(confidence_dist.get("low", 0)),
        },
        "confidence_distribution_all": {
            "high": int(confidence_dist_all.get("high", 0)),
            "medium": int(confidence_dist_all.get("medium", 0)),
            "low": int(confidence_dist_all.get("low", 0)),
        },
        "high_confidence_library_matches": high_conf_count,
        "text_only_count": text_only_count,
        "text_only_ratio": round(text_only_count / total, 4),
        "primary_conflicts_total": len(conflict_files),
        "primary_conflicts_resolved": resolved,
        "primary_conflicts_unresolved": unresolved,
        "unknown_files_count": unknown_files_count,
        "by_library": dict(sorted(by_library.items())),
    }


def cmd_build_library_match(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    cfg = _load_library_match_rules(workspace)

    origin_path = paths.analysis / "build_origin_report.json"
    if not origin_path.is_file():
        raise SystemExit("E_RUNTIME: run infer-build-origin first")
    origin_obj = json.loads(read_text(origin_path))
    origin_by_file = {str(i.get("file", "")): str(i.get("origin_label", "unknown")) for i in origin_obj.get("items", [])}

    all_candidates: list[dict[str, Any]] = []
    rules = cfg.get("library_rules", {})
    files_scanned = 0
    for f in collect_files(source_root, {".js", ".css"}):
        p = rel(f, source_root)
        txt = read_text(f)
        files_scanned += 1
        for lib, rule in rules.items():
            if not isinstance(rule, dict):
                continue
            cand = _collect_candidate(p, txt, str(lib), rule, cfg)
            if cand:
                all_candidates.append(cand)

    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in all_candidates:
        by_file[str(it.get("file", ""))].append(it)

    match_items: list[dict[str, Any]] = []
    for file_key, items in by_file.items():
        resolved = _resolve_file_conflicts(items, cfg)
        for it in resolved:
            it["file"] = file_key
            match_items.append(it)

    match_items.sort(key=lambda x: (str(x.get("file", "")), int(not bool(x.get("is_primary_match", False))), str(x.get("library", ""))))
    quality = _calc_quality(match_items, origin_by_file, files_scanned)

    write_json(
        paths.analysis / "library_matches.json",
        {
            "run_id": run_id,
            "count": len(match_items),
            "items": match_items,
        },
    )
    write_json(
        paths.analysis / "library_match_quality.json",
        {
            "run_id": run_id,
            **quality,
        },
    )

    # 排除规则：
    # - kind=vendor_library / bundler_runtime / host_bridge + high 置信 → 排除
    # - kind=framework_compiled（Vue SFC 编译产物）→ 不排除，这类文件含业务逻辑
    # - origin_label=app_business → 永不排除（业务文件优先，即使命中 framework_runtime）
    # - medium + text + chunk 组合 → 排除（历史行为保留）
    # 注意：framework_runtime 仅当 high 且 primary 时排除（如 naive-ui 主包）
    NON_EXCLUDE_KINDS = {"framework_compiled"}
    ALWAYS_EXCLUDE_KINDS = {"vendor_library", "bundler_runtime", "bundler_helper", "host_bridge"}
    exclude_files: set[str] = set()
    symbol_map_items = []
    for it in match_items:
        evidence_types = set(str(x) for x in (it.get("evidence_types", []) or []))
        conf = str(it.get("confidence", "low"))
        kind = str(it.get("kind", ""))
        is_primary = bool(it.get("is_primary_match", False))
        has_text = "text_markers" in evidence_types
        has_chunk = "chunk_naming" in evidence_types
        file_origin = str(origin_by_file.get(str(it.get("file", "")), "unknown"))
        # app_business 文件永不排除，无论库匹配结果如何
        if file_origin == "app_business":
            exclude_flag = False
        # framework_compiled 永不排除（Vue SFC 业务组件）
        elif kind in NON_EXCLUDE_KINDS:
            exclude_flag = False
        elif kind in ALWAYS_EXCLUDE_KINDS and conf == "high" and is_primary:
            exclude_flag = True
        elif conf == "high" and is_primary:
            # framework_runtime 等：high + primary 才排除
            exclude_flag = True
        elif conf == "medium" and has_text and has_chunk:
            # 历史行为：medium + text + chunk 组合排除
            exclude_flag = True
        else:
            exclude_flag = False
        if exclude_flag:
            exclude_files.add(str(it.get("file", "")))
        symbol_map_items.append(
            {
                "file": it["file"],
                "library": it["library"],
                "kind": kind,
                "confidence": conf,
                "exclude_from_business_rename": exclude_flag,
            }
        )
    write_json(
        paths.analysis / "library_symbol_map.json",
        {
            "run_id": run_id,
            "count": len(symbol_map_items),
            "items": symbol_map_items,
            "exclude_files": sorted(exclude_files),
        },
    )

    business_pool: list[str] = []
    for f in collect_files(source_root, {".js"}):
        p = rel(f, source_root)
        if p not in exclude_files:
            business_pool.append(p)
    write_json(
        paths.analysis / "business_symbol_pool.json",
        {
            "run_id": run_id,
            "count": len(business_pool),
            "files": sorted(business_pool),
        },
    )

    # 反馈回路：用 library_match 高置信结果修正 build_origin_report
    origin_path = paths.analysis / "build_origin_report.json"
    if origin_path.is_file():
        try:
            origin_obj = json.loads(read_text(origin_path))
            origin_items = origin_obj.get("items", [])
            refined = refine_origin_with_library_match(origin_items, match_items)
            refined_count = sum(
                1 for a, b in zip(origin_items, refined)
                if a.get("origin_label") != b.get("origin_label")
            )
            origin_obj["items"] = refined
            origin_obj["library_match_refined"] = True
            origin_obj["library_match_refined_count"] = refined_count
            write_json(origin_path, origin_obj)
        except Exception:
            pass  # 回写失败不中断主流程


def load_library_exclude_files(paths: Any) -> set[str]:
    p = paths.analysis / "library_symbol_map.json"
    if not p.is_file():
        return set()
    try:
        obj = json.loads(read_text(p))
        items = obj.get("exclude_files", [])
        if isinstance(items, list):
            return {str(x) for x in items}
    except Exception:
        return set()
    return set()
