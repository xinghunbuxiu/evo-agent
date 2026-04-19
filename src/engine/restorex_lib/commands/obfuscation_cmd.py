from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import collect_files, read_text, rel, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def cmd_analyze_obfuscation(workspace: Path, run_id: str) -> None:
    """混淆/压缩画像：评估输入复杂度，并给出自动还原策略。"""
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    file_portrait_path = paths.portraits / "file_portraits.json"
    file_portrait_obj = json.loads(read_text(file_portrait_path)) if file_portrait_path.is_file() else {"items": []}
    origin_by_file = {str(i.get("file", "")): str(i.get("origin_label", "unknown")) for i in file_portrait_obj.get("items", [])}

    js_keywords = {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "break",
        "continue",
        "try",
        "catch",
        "finally",
        "function",
        "return",
        "const",
        "let",
        "var",
        "class",
        "new",
        "this",
        "null",
        "true",
        "false",
        "import",
        "export",
        "default",
        "from",
        "await",
        "async",
        "typeof",
        "instanceof",
        "void",
        "delete",
    }

    def classify_score(score: int) -> str:
        if score >= 11:
            return "high"
        if score >= 6:
            return "medium"
        return "low"

    file_items: list[dict[str, Any]] = []
    level_count = {"low": 0, "medium": 0, "high": 0}
    source_type_count: dict[str, int] = {"app_business": 0, "framework_compiled": 0, "vendor_library": 0, "bundler_runtime": 0, "unknown": 0}

    for f in collect_files(source_root, {".js"}):
        rel_path = rel(f, source_root)
        text = read_text(f)
        lines = text.splitlines()
        line_count = max(1, len(lines))
        origin_label = origin_by_file.get(rel_path, "unknown")
        source_type_count[origin_label] = source_type_count.get(origin_label, 0) + 1

        long_line_count = sum(1 for ln in lines if len(ln) >= 220)
        long_line_ratio = long_line_count / line_count

        symbols = re.findall(r"\b[A-Za-z_$][A-Za-z0-9_$]*\b", text)
        identifiers = [s for s in symbols if s not in js_keywords and not s.startswith("__VUE")]
        ident_count = max(1, len(identifiers))
        short_ident_count = sum(1 for s in identifiers if len(s) <= 2)
        short_ident_ratio = short_ident_count / ident_count
        avg_ident_len = sum(len(s) for s in identifiers) / ident_count if identifiers else 0.0

        punct_count = text.count(";") + text.count(",") + text.count("{") + text.count("}")
        punct_density = punct_count / max(1, len(text))

        has_eval = bool(re.search(r"\b(?:eval|Function)\s*\(", text))
        has_obf_hex = bool(re.search(r"\b0x[a-fA-F0-9]{4,}\b", text))
        has_obf_symbol = bool(re.search(r"\b_0x[a-fA-F0-9]{4,}\b", text))
        has_flatten = bool(re.search(r"while\s*\(\s*!!\[\]\s*\)|switch\s*\(\s*[A-Za-z_$][\w$]*\s*(?:\+\+|--)\s*\)", text))
        has_large_string_table = bool(re.search(r"\[[^\]]{120,}\]", text))

        score = 0
        if short_ident_ratio >= 0.50:
            score += 3
        elif short_ident_ratio >= 0.35:
            score += 2
        if long_line_ratio >= 0.35:
            score += 3
        elif long_line_ratio >= 0.18:
            score += 2
        if punct_density >= 0.09:
            score += 2
        elif punct_density >= 0.06:
            score += 1
        if has_obf_symbol:
            score += 3
        if has_flatten:
            score += 3
        if has_eval:
            score += 2
        if has_obf_hex:
            score += 1
        if has_large_string_table:
            score += 2

        level = classify_score(score)
        level_count[level] = level_count.get(level, 0) + 1
        readability_score = max(0, min(100, 100 - score * 7))

        file_items.append(
            {
                "file": rel_path,
                "origin_label": origin_label,
                "line_count": line_count,
                "identifier_count": len(identifiers),
                "short_identifier_ratio": round(short_ident_ratio, 4),
                "avg_identifier_len": round(avg_ident_len, 4),
                "long_line_ratio": round(long_line_ratio, 4),
                "punctuation_density": round(punct_density, 6),
                "flags": {
                    "has_eval_or_function_ctor": has_eval,
                    "has_hex_obfuscation": has_obf_hex,
                    "has_obfuscation_symbol": has_obf_symbol,
                    "has_control_flow_flattening": has_flatten,
                    "has_large_string_table": has_large_string_table,
                },
                "obfuscation_score": score,
                "obfuscation_level": level,
                "estimated_readability_score": readability_score,
            }
        )

    total = max(1, len(file_items))
    high_ratio = level_count.get("high", 0) / total
    medium_ratio = level_count.get("medium", 0) / total
    if high_ratio >= 0.30:
        bundle_level = "high"
    elif high_ratio + medium_ratio >= 0.55:
        bundle_level = "medium"
    else:
        bundle_level = "low"

    strategy: list[str] = [
        "先保留 raw_runtime 或原始入口可执行基线，再进行可读层替换。",
        "优先还原 app_business 文件；vendor/bundler 仅保留映射与证据，不做激进重写。",
        "改名仅采纳 high 置信候选；medium/low 保持候选状态，避免过拟合污染。",
    ]
    if bundle_level == "high":
        strategy.append("建议启用分层恢复：先链路可运行，再做局部 AST 改写，不直接全量改写。")
    elif bundle_level == "medium":
        strategy.append("建议双轨输出：readable 用于理解，raw_runtime 用于回归验真。")
    else:
        strategy.append("可采用 balanced 档位批量推进，并持续回归 verify 门禁。")

    out_obj = {
        "run_id": run_id,
        "generated_at": dt.datetime.now().isoformat(),
        "summary": {
            "js_file_count": len(file_items),
            "bundle_obfuscation_level": bundle_level,
            "obfuscation_level_distribution": level_count,
            "source_type_distribution": source_type_count,
            "recommended_strategy": strategy,
        },
        "items": sorted(file_items, key=lambda x: (int(x.get("obfuscation_score", 0)), str(x.get("file", ""))), reverse=True),
    }
    write_json(paths.analysis / "obfuscation_profile.json", out_obj)

    md = [
        "# Obfuscation Profile",
        "",
        f"- run_id: `{run_id}`",
        f"- js_file_count: `{out_obj['summary']['js_file_count']}`",
        f"- bundle_obfuscation_level: `{bundle_level}`",
        "",
        "## Level Distribution",
        f"- high: `{level_count.get('high', 0)}`",
        f"- medium: `{level_count.get('medium', 0)}`",
        f"- low: `{level_count.get('low', 0)}`",
        "",
        "## Recommended Strategy",
    ]
    for s in strategy:
        md.append(f"- {s}")
    md.extend(["", "## Top Complex Files"])
    for it in out_obj["items"][:20]:
        md.append(
            f"- {it['file']} | level={it['obfuscation_level']} score={it['obfuscation_score']} short={it['short_identifier_ratio']} longLine={it['long_line_ratio']} origin={it['origin_label']}"
        )
    write_text(paths.analysis / "obfuscation_profile.md", "\n".join(md))
