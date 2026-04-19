from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text, write_text


def _scope_fallback_invoke_candidate(rel_file: str) -> str:
    name = str(rel_file).strip().split("/")[-1]
    stem = name.rsplit(".", 1)[0]
    raw = stem.split("-", 1)[0]
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", raw) if p]
    if len(parts) == 1:
        parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", parts[0]) or parts
    if not parts:
        return "handleInvokeCommand"
    module = "".join(p[:1].upper() + p[1:] for p in parts)
    for suffix in ("Dialog", "Page", "View", "Panel", "Module", "Screen"):
        if module.endswith(suffix) and len(module) > len(suffix):
            module = module[: -len(suffix)]
            break
    if not module:
        return "handleInvokeCommand"
    return f"handle{module}InvokeCommand"


def run_scope_rename_pass(
    readable: Path,
    paths: Any,
    cfg: Any,
    preferred_targets_by_file: dict[str, set[str]] | None = None,
    *,
    apply_scoped_call_symbol_replace: Callable[[str, str, str, int, int], tuple[str, int]],
    apply_scoped_symbol_replace: Callable[[str, str, str, int, int], tuple[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scope_path = paths.analysis / "scope_rename_candidates.json"
    if not scope_path.is_file():
        return ([], [])
    try:
        scope_items = json.loads(read_text(scope_path)).get("items", [])
    except Exception:
        return ([], [])

    scope_applied_renames: list[dict[str, Any]] = []
    scope_skipped_groups: list[dict[str, Any]] = []

    grouped_scope: dict[tuple[str, str, str, int, int], list[dict[str, Any]]] = {}
    for it in scope_items:
        rel_file = str(it.get("file", "")).strip()
        short = str(it.get("symbol", "")).strip()
        cand = str(it.get("candidate", "")).strip()
        src = str(it.get("source", "")).strip()
        ent_name = str(it.get("entity_name", "")).strip()
        line_start = int(it.get("line_start", 0) or 0)
        line_end = int(it.get("line_end", line_start) or line_start)
        conf = str(it.get("confidence", "low")).lower()
        evidence_refs = [str(r) for r in it.get("evidence_refs", [])]
        if not rel_file or not short or not cand or not ent_name:
            continue
        allow_business_short = bool(src == "scope_method_business_flow_infer" and re.fullmatch(r"[A-Za-z]{1,2}", short))
        allow_registry_short = bool(src == "scope_service_registry_infer" and re.fullmatch(r"[A-Za-z]{1,2}", short))
        if len(short) > 2 or (not re.fullmatch(cfg.short_name_regex, short) and not allow_business_short and not allow_registry_short):
            continue
        if conf not in {"high", "medium"}:
            continue
        allow_medium_flow_scope = bool(
            src == "scope_method_business_flow_infer"
            and re.fullmatch(r"[A-Za-z]{1,2}", short)
            and any(str(r).startswith("flow_tag:") for r in evidence_refs)
        )
        if conf == "medium" and not cfg.allow_scope_medium_confidence and not allow_medium_flow_scope:
            continue
        if conf == "medium" and len(evidence_refs) < 2:
            continue
        if any(token in cand for token in cfg.forbidden_rename_tokens):
            continue
        allow_registry_generic_candidate = bool(
            src == "scope_service_registry_infer"
            and conf == "high"
            and re.fullmatch(r"^[a-z][A-Za-z0-9]{3,40}$", cand)
        )
        allow_registry_pascal_candidate = bool(
            src == "scope_service_registry_infer"
            and conf == "high"
            and re.fullmatch(r"^[A-Z][A-Za-z0-9]{3,48}$", cand)
        )
        if cand in cfg.generic_candidates and not (allow_registry_generic_candidate or allow_registry_pascal_candidate):
            continue
        allow_registry_candidate = bool(
            src == "scope_service_registry_infer"
            and (
                re.fullmatch(r"^[a-z][A-Za-z0-9]{3,40}$", cand)
                or allow_registry_pascal_candidate
            )
        )
        if not cand.startswith(cfg.auto_rename_prefixes) and not allow_registry_candidate:
            continue
        key = (rel_file, short, ent_name, max(1, line_start), max(max(1, line_start), line_end))
        grouped_scope.setdefault(key, []).append(it)

    selected_scope_ops: dict[str, list[dict[str, Any]]] = {}
    for key, items in grouped_scope.items():
        rel_file, short, ent_name, line_start, line_end = key
        score_map: dict[str, float] = {}
        refs_map: dict[str, set[str]] = {}
        for it in items:
            cand = str(it.get("candidate", "")).strip()
            conf = str(it.get("confidence", "low")).lower()
            conf_weight = {"high": 3.0, "medium": 2.0, "low": 1.0}.get(conf, 1.0)
            ev = [str(r) for r in it.get("evidence_refs", [])]
            score_map[cand] = score_map.get(cand, 0.0) + conf_weight + min(1.0, 0.25 * max(1, len(ev)))
            refs_map.setdefault(cand, set()).update(ev)
        ranked = sorted(score_map.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked:
            continue
        top_cand, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else -1.0
        if len(ranked) > 1 and top_score <= second_score:
            if preferred_targets_by_file:
                preferred = preferred_targets_by_file.get(rel_file, set())
                preferred_hits = [c for c, _ in ranked if c in preferred]
                if len(preferred_hits) == 1:
                    top_cand = preferred_hits[0]
                    top_score = score_map.get(top_cand, top_score)
                    second_score = -1.0
            if len(ranked) > 1 and top_score <= second_score:
                # 次级兜底：并列时优先选择“语义更通用”的候选（词段更少）。
                seg_rank = []
                for c, _ in ranked:
                    segs = re.findall(r"[A-Z]?[a-z0-9]+", c)
                    seg_rank.append((len(segs), len(c), c))
                seg_rank.sort()
                if seg_rank and (len(seg_rank) == 1 or seg_rank[0][0] < seg_rank[1][0]):
                    top_cand = seg_rank[0][2]
                    top_score = score_map.get(top_cand, top_score)
                    second_score = -1.0
            if len(ranked) > 1 and top_score <= second_score:
                # 末级兜底：多命令并列时统一收敛为 invoke 包装器语义，避免长期悬空。
                if len(ranked) >= 3:
                    top_cand = _scope_fallback_invoke_candidate(rel_file)
                    top_score = 0.0
                    second_score = -1.0
            if len(ranked) > 1 and top_score <= second_score:
                scope_skipped_groups.append(
                    {
                        "file": rel_file,
                        "symbol": short,
                        "entity_name": ent_name,
                        "line_start": line_start,
                        "line_end": line_end,
                        "reason": "scope_multi_candidates_tie",
                        "candidates": [{"candidate": c, "score": round(s, 3)} for c, s in ranked],
                    }
                )
            continue
        selected_scope_ops.setdefault(rel_file, []).append(
            {
                "symbol": short,
                "candidate": top_cand,
                "entity_name": ent_name,
                "line_start": line_start,
                "line_end": line_end,
                "score": round(top_score, 3),
                "evidence_refs": sorted(refs_map.get(top_cand, set())),
                "source": str(items[0].get("source", "scope_chain_infer")) if items else "scope_chain_infer",
            }
        )

    for rel_file, ops in selected_scope_ops.items():
        target = readable / rel_file
        if not target.is_file():
            continue
        text = read_text(target)
        changed = False
        # 按起始行倒序应用，避免前段替换影响后段行号定位。
        for op in sorted(ops, key=lambda x: (int(x["line_start"]), int(x["line_end"])), reverse=True):
            new_text, n = apply_scoped_call_symbol_replace(
                text,
                str(op["symbol"]),
                str(op["candidate"]),
                int(op["line_start"]),
                int(op["line_end"]),
            )
            # 对方法业务流候选做定义位兜底：若调用位替换未命中，则在同一方法作用域内做符号替换。
            if n <= 0 and str(op.get("source", "")) in {"scope_method_business_flow_infer", "scope_service_registry_infer"}:
                new_text, n = apply_scoped_symbol_replace(
                    text,
                    str(op["symbol"]),
                    str(op["candidate"]),
                    int(op["line_start"]),
                    int(op["line_end"]),
                )
            if n > 0:
                text = new_text
                changed = True
                scope_applied_renames.append(
                    {
                        "file": rel_file,
                        "from": op["symbol"],
                        "to": op["candidate"],
                        "replace_count": n,
                        "scope": {
                            "entity_name": op["entity_name"],
                            "line_start": op["line_start"],
                            "line_end": op["line_end"],
                            "score": op["score"],
                        },
                        "source": str(op.get("source", "scope_chain_infer")),
                        "evidence_refs": op.get("evidence_refs", []),
                    }
                )
        if changed:
            write_text(target, text)

    # 方法参数作用域改名：仅采纳方法画像中的高置信 logger 参数候选，避免全局污染。
    method_path = paths.portraits / "method_portraits.json"
    if method_path.is_file():
        try:
            method_items = json.loads(read_text(method_path)).get("items", [])
        except Exception:
            method_items = []
        method_ops_by_file: dict[str, list[dict[str, Any]]] = {}
        for it in method_items:
            method_kind = str(it.get("method_kind", ""))
            if method_kind not in {"logger_method", "logger_setter_method"}:
                continue
            if str(it.get("confidence", "low")) != "high":
                continue
            rel_file = str(it.get("file", "")).strip()
            if not rel_file:
                continue
            line_start = int(it.get("line", 0) or 0)
            line_end = int(it.get("line_end", line_start) or line_start)
            if line_start <= 0:
                continue
            inferred = it.get("inferred_param_candidates", [])
            for prm in inferred if isinstance(inferred, list) else []:
                conf = str(prm.get("confidence", "low")).lower()
                if conf != "high":
                    continue
                raw_param = str(prm.get("param", "")).strip()
                short = raw_param.lstrip(".")
                candidate = str(prm.get("candidate", "")).strip()
                if not short or not candidate:
                    continue
                if not re.fullmatch(cfg.short_name_regex, short):
                    continue
                if candidate in cfg.generic_candidates:
                    continue
                if any(token in candidate for token in cfg.forbidden_rename_tokens):
                    continue
                method_ops_by_file.setdefault(rel_file, []).append(
                    {
                        "symbol": short,
                        "candidate": candidate,
                        "line_start": line_start,
                        "line_end": max(line_start, line_end),
                        "method_name": str(it.get("method_name", "")),
                    }
                )

        for rel_file, ops in method_ops_by_file.items():
            target = readable / rel_file
            if not target.is_file():
                continue
            text = read_text(target)
            changed = False
            for op in sorted(ops, key=lambda x: (int(x["line_start"]), int(x["line_end"])), reverse=True):
                new_text, n = apply_scoped_symbol_replace(
                    text,
                    str(op["symbol"]),
                    str(op["candidate"]),
                    int(op["line_start"]),
                    int(op["line_end"]),
                )
                if n > 0:
                    text = new_text
                    changed = True
                    scope_applied_renames.append(
                        {
                            "file": rel_file,
                            "from": op["symbol"],
                            "to": op["candidate"],
                            "replace_count": n,
                            "scope": {
                                "entity_name": op["method_name"],
                                "line_start": op["line_start"],
                                "line_end": op["line_end"],
                            },
                            "source": "scope_method_param_infer",
                            "evidence_refs": [f"{rel_file}#method:{op['method_name']}:{op['line_start']}-{op['line_end']}"],
                        }
                    )
            if changed:
                write_text(target, text)
    return (scope_applied_renames, scope_skipped_groups)
