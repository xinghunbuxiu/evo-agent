from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from restorex_lib.fingerprint_registry import load_fingerprint_registry
from restorex_lib.fs_utils import collect_files, read_text, rel, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths

ORIGIN_LABELS = {
    "bundler_runtime",
    "framework_compiled",
    "vendor_library",
    "app_business",
    "unknown",
}


def _match_rule(
    rule: dict[str, Any],
    *,
    path_low: str,
    text_low: str,
    compact_low: str,
    ext: str,
) -> bool:
    if not isinstance(rule, dict):
        return False

    checks: list[bool] = []
    path_contains = rule.get("path_contains", [])
    if isinstance(path_contains, list) and path_contains:
        checks.append(any(str(x).lower() in path_low for x in path_contains if str(x).strip()))

    text_contains = rule.get("text_contains", [])
    if isinstance(text_contains, list) and text_contains:
        checks.append(all(str(x).lower() in text_low for x in text_contains if str(x).strip()))

    compact_contains = rule.get("compact_contains", [])
    if isinstance(compact_contains, list) and compact_contains:
        checks.append(all(str(x).lower() in compact_low for x in compact_contains if str(x).strip()))

    text_regex = rule.get("text_regex", [])
    if isinstance(text_regex, list) and text_regex:
        checks.append(any(re.search(str(x), text_low, re.I) for x in text_regex if str(x).strip()))

    compact_regex = rule.get("compact_regex", [])
    if isinstance(compact_regex, list) and compact_regex:
        checks.append(any(re.search(str(x), compact_low, re.I) for x in compact_regex if str(x).strip()))

    ext_in = rule.get("ext_in", [])
    if isinstance(ext_in, list) and ext_in:
        checks.append(ext.lower() in {str(x).lower() for x in ext_in if str(x).strip()})

    all_rules = rule.get("all", [])
    if isinstance(all_rules, list) and all_rules:
        checks.append(all(_match_rule(r, path_low=path_low, text_low=text_low, compact_low=compact_low, ext=ext) for r in all_rules))

    any_rules = rule.get("any", [])
    if isinstance(any_rules, list) and any_rules:
        checks.append(any(_match_rule(r, path_low=path_low, text_low=text_low, compact_low=compact_low, ext=ext) for r in any_rules))

    return all(checks) if checks else False


def _detect_third_party_from_registry(path: str, text: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    rel_low = path.lower()
    txt_low = text.lower()
    compact_low = re.sub(r"\s+", "", txt_low)
    ext = Path(path).suffix.lower()
    out: list[dict[str, Any]] = []
    rules = registry.get("third_party_fingerprints", [])
    if not isinstance(rules, list):
        return out
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match", {})
        if not _match_rule(match, path_low=rel_low, text_low=txt_low, compact_low=compact_low, ext=ext):
            continue
        library = str(rule.get("library", "")).strip()
        if not library or any(x.get("library") == library for x in out):
            continue
        out.append(
            {
                "library": library,
                "kind": str(rule.get("kind", "unknown")),
                "confidence": str(rule.get("confidence", "medium")),
                "evidence": [str(x) for x in (rule.get("evidence", []) if isinstance(rule.get("evidence", []), list) else []) if str(x).strip()],
                "guessed_from": str(rule.get("guessed_from", "fingerprint pack rule")),
            }
        )
    return out


def _detect_signal_from_registry(path: str, text: str, registry: dict[str, Any]) -> list[str]:
    rel_low = path.lower()
    txt_low = text.lower()
    compact_low = re.sub(r"\s+", "", txt_low)
    ext = Path(path).suffix.lower()
    out: list[str] = []
    rules = registry.get("signal_rules", [])
    if not isinstance(rules, list):
        return out
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        signal = str(rule.get("signal", "")).strip()
        if not signal:
            continue
        if _match_rule(rule.get("match", {}), path_low=rel_low, text_low=txt_low, compact_low=compact_low, ext=ext):
            out.append(signal)
    return out


def detect_third_party_fingerprint(path: str, text: str, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rel_low = path.lower()
    txt_low = text.lower()
    compact_low = re.sub(r"\s+", "", txt_low)
    ext = Path(path).suffix.lower()
    hits: list[dict[str, Any]] = []

    def add_hit(library: str, kind: str, confidence: str, evidence: list[str], guessed_from: str) -> None:
        if any(h["library"] == library for h in hits):
            return
        hits.append(
            {
                "library": library,
                "kind": kind,
                "confidence": confidence,
                "evidence": evidence,
                "guessed_from": guessed_from,
            }
        )

    reg = registry or {}
    for item in _detect_third_party_from_registry(path, text, reg):
        add_hit(
            library=str(item.get("library", "")),
            kind=str(item.get("kind", "unknown")),
            confidence=str(item.get("confidence", "medium")),
            evidence=[str(x) for x in item.get("evidence", []) if str(x).strip()],
            guessed_from=str(item.get("guessed_from", "fingerprint pack rule")),
        )
    return hits


def detect_signals(path: str, text: str, registry: dict[str, Any] | None = None) -> tuple[list[str], list[str]]:
    signals: list[str] = []
    counter: list[str] = []
    low_path = path.lower()
    low_text = text.lower()
    compact_low = re.sub(r"\s+", "", low_text)

    reg = registry or {}
    signals.extend(_detect_signal_from_registry(path, text, reg))
    if len(text) > 180_000:
        signals.append("large-export-density")
    if re.search(r"[.-][A-Za-z0-9_-]{6,}\.(js|css)$", path):
        signals.append("hash chunk")

    if re.search(r"[\u4e00-\u9fff]", text):
        signals.append("contains-cn-text")
    else:
        counter.append("no-cn-text")
    if low_path.endswith(".svg"):
        counter.append("asset-like")
    uniq_signals = sorted(set(signals))
    return uniq_signals, counter


def classify_origin(path: str, signals: list[str]) -> tuple[str, str, str]:
    s = set(signals)
    low_path = path.lower()
    # 大型 vendor 包：文件名命中 + 大量导出密度
    if "vendor-name-naive-ui" in s or (len(s) >= 3 and "large-export-density" in s and "framework-component-compiled" in s):
        return "vendor_library", "high", "verified"
    # Vite/Vue 构建辅助 chunk（_plugin-vue_export-helper 等）
    if "helper-runtime" in s:
        return "bundler_runtime", "high", "verified"
    # CSS：带 hash 的 chunk 文件视为框架编译产物
    if low_path.endswith(".css") and ("scoped-css-marker" in s or "hash chunk" in s):
        return "framework_compiled", "medium", "guessed"
    # Vue SFC 编译产物（有 __name 特征 + 引用了 _plugin-vue_export-helper）
    # 但如果同时有业务信号（中文文案 + pinia/bridge），优先判断为 app_business
    if "vue-sfc-compiled" in s:
        has_business_signals = (
            "contains-cn-text" in s
            and (
                "pinia-store-signature" in s
                or "host-bridge-runtime" in s
                or "__vite__mapDeps" in s
                or "framework-component-compiled" in s
            )
        )
        if not has_business_signals:
            return "framework_compiled", "medium", "guessed"
    # 业务文件：有中文文案 + Tauri bridge 调用
    if "host-bridge-runtime" in s and "contains-cn-text" in s:
        return "app_business", "high", "verified"
    # 业务文件：有中文文案 + Vue 组件特征
    if "framework-component-compiled" in s and "contains-cn-text" in s:
        return "app_business", "medium", "guessed"
    # 纯 bundler 运行时（HTML 入口、preload 图等）
    if "modulepreload" in s or "__vite__mapDeps" in s:
        return "bundler_runtime", "medium", "guessed"
    if low_path.endswith(".svg"):
        return "unknown", "low", "guessed"
    return "unknown", "low", "guessed"


def refine_origin_with_library_match(
    origin_items: list[dict[str, Any]],
    library_match_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """用 library_match 的高置信结果修正 origin_label。

    规则（按优先级）：
    - kind=vendor_library  + high + primary  → vendor_library  (verified)
    - kind=bundler_helper  + high + primary  → bundler_runtime (verified)
    - kind=host_bridge     + high + primary  → bundler_runtime (verified)
    - kind=framework_compiled + medium + primary → framework_compiled (若当前为 unknown/guessed)
    - kind=state_management + high + primary → 不改 origin_label，但提升 confidence
    """
    # 按文件建立 library_match 的 primary 命中索引
    primary_by_file: dict[str, dict[str, Any]] = {}
    for it in library_match_items:
        if not bool(it.get("is_primary_match", False)):
            continue
        f = str(it.get("file", "")).strip()
        if not f:
            continue
        # 同一文件可能有多个 primary（不同库），取 confidence 最高的
        existing = primary_by_file.get(f)
        rank = {"high": 3, "medium": 2, "low": 1}
        if existing is None or rank.get(str(it.get("confidence", "low")), 0) > rank.get(str(existing.get("confidence", "low")), 0):
            primary_by_file[f] = it

    KIND_TO_ORIGIN: dict[str, str] = {
        "vendor_library": "vendor_library",
        "bundler_helper": "bundler_runtime",
        "bundler_runtime": "bundler_runtime",
        "host_bridge": "bundler_runtime",
    }
    FRAMEWORK_COMPILED_KINDS = {"framework_compiled"}

    out: list[dict[str, Any]] = []
    for item in origin_items:
        obj = dict(item)
        f = str(obj.get("file", "")).strip()
        match = primary_by_file.get(f)
        if match:
            kind = str(match.get("kind", "")).strip()
            conf = str(match.get("confidence", "low")).strip()
            if kind in KIND_TO_ORIGIN and conf == "high":
                new_label = KIND_TO_ORIGIN[kind]
                if obj.get("origin_label") != new_label:
                    obj["origin_label"] = new_label
                    obj["confidence"] = "high"
                    obj["status"] = "verified"
                    obj.setdefault("refinement_notes", []).append(
                        f"library_match:{match.get('library')}(kind={kind},conf={conf})"
                    )
            elif kind in FRAMEWORK_COMPILED_KINDS and conf in {"medium", "high"}:
                if obj.get("origin_label") in {"unknown", "framework_compiled"}:
                    obj["origin_label"] = "framework_compiled"
                    obj["confidence"] = conf
                    obj["status"] = "guessed"
                    obj.setdefault("refinement_notes", []).append(
                        f"library_match:{match.get('library')}(kind={kind},conf={conf})"
                    )
        out.append(obj)
    return out


def cmd_infer_build_origin(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    registry = load_fingerprint_registry(workspace)
    items: list[dict[str, Any]] = []
    for f in collect_files(source_root):
        p = rel(f, source_root)
        text = read_text(f)
        signals, counter = detect_signals(p, text, registry=registry)
        origin_label, confidence, status = classify_origin(p, signals)
        if origin_label not in ORIGIN_LABELS:
            origin_label = "unknown"
        items.append(
            {
                "file": p,
                "origin_label": origin_label,
                "confidence": confidence,
                "signals": sorted(signals),
                "counter_evidence": sorted(counter),
                "status": status,
            }
        )
    items.sort(key=lambda x: (x["origin_label"], x["file"]))
    write_json(paths.analysis / "build_origin_report.json", {"run_id": run_id, "count": len(items), "items": items})


def cmd_scan_structure(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    html_entries: list[dict[str, Any]] = []
    js_entries: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for f in collect_files(source_root):
        p = rel(f, source_root)
        text = read_text(f)
        if f.suffix.lower() == ".html":
            scripts = re.findall(r'<script[^>]+src="([^"]+)"', text)
            styles = re.findall(r'<link[^>]+href="([^"]+)"', text)
            html_entries.append({"file": p, "scripts": scripts, "styles": styles})
        if f.suffix.lower() == ".js":
            imports = re.findall(r'import[^"\']*["\']([^"\']+)["\']', text)
            js_entries.append({"file": p, "imports": imports})
            for imp in imports:
                edges.append({"from": p, "to": imp})

    write_json(
        paths.analysis / "structure_scan.json",
        {
            "run_id": run_id,
            "html_files": html_entries,
            "js_files": js_entries,
            "module_edges": edges,
        },
    )


def cmd_build_portrait(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot
    registry = load_fingerprint_registry(workspace)

    origin_path = paths.analysis / "build_origin_report.json"
    structure_path = paths.analysis / "structure_scan.json"
    if not origin_path.is_file() or not structure_path.is_file():
        raise SystemExit("E_RUNTIME: run infer-build-origin and scan-structure first")

    origin_obj = json.loads(read_text(origin_path))
    structure_obj = json.loads(read_text(structure_path))

    ext_stats: dict[str, int] = {}
    for f in collect_files(source_root):
        ext = f.suffix.lower()
        ext_stats[ext] = ext_stats.get(ext, 0) + 1

    origin_stats: dict[str, int] = {}
    for item in origin_obj.get("items", []):
        label = str(item.get("origin_label", "unknown"))
        origin_stats[label] = origin_stats.get(label, 0) + 1

    signals_counter: dict[str, int] = {}
    for item in origin_obj.get("items", []):
        for s in item.get("signals", []):
            key = str(s)
            signals_counter[key] = signals_counter.get(key, 0) + 1

    top_signals = sorted(signals_counter.items(), key=lambda x: x[1], reverse=True)[:20]
    js_files = structure_obj.get("js_files", [])
    html_files = structure_obj.get("html_files", [])
    module_edges = structure_obj.get("module_edges", [])
    file_names = [str(i.get("file", "")).lower() for i in origin_obj.get("items", [])]

    frameworks: list[dict[str, Any]] = []
    top_signal_names = {str(s) for s, _ in top_signals}
    framework_rules = registry.get("framework_rules", []) if isinstance(registry.get("framework_rules", []), list) else []
    for rule in framework_rules:
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name", "")).strip()
        if not name:
            continue
        sig_all = [str(x) for x in (rule.get("signals_all", []) if isinstance(rule.get("signals_all", []), list) else []) if str(x).strip()]
        sig_any = [str(x) for x in (rule.get("signals_any", []) if isinstance(rule.get("signals_any", []), list) else []) if str(x).strip()]
        file_any = [str(x).lower() for x in (rule.get("file_name_contains_any", []) if isinstance(rule.get("file_name_contains_any", []), list) else []) if str(x).strip()]
        ok_sig_all = (not sig_all) or all(x in top_signal_names for x in sig_all)
        ok_sig_any = (not sig_any) or any(x in top_signal_names for x in sig_any)
        ok_file = (not file_any) or any(any(tok in fn for tok in file_any) for fn in file_names)
        if ok_sig_all and ok_sig_any and ok_file:
            frameworks.append(
                {
                    "name": name,
                    "confidence": str(rule.get("confidence", "medium")),
                    "evidence": [str(x) for x in (rule.get("evidence", []) if isinstance(rule.get("evidence", []), list) else []) if str(x).strip()],
                }
            )
    # 兼容兜底：当 pack 配置缺失时仍保持旧行为。
    if not frameworks:
        if any("framework-entry-create-mount" == s for s, _ in top_signals):
            frameworks.append({"name": "vue-like", "confidence": "high", "evidence": ["framework-entry-create-mount"]})
        if any("naive-ui" in n for n in file_names):
            frameworks.append({"name": "naive-ui-like", "confidence": "high", "evidence": ["vendor-name-naive-ui"]})
        if any("__vite__mapdeps" == s.lower() for s, _ in top_signals) or any("vite" in str(e.get("to", "")).lower() for e in module_edges):
            frameworks.append({"name": "vite-like-bundler", "confidence": "high", "evidence": ["__vite__mapDeps", "modulepreload"]})

    third_party_items: list[dict[str, Any]] = []
    third_party_stats: dict[str, int] = {}
    for f in collect_files(source_root):
        rel_path = rel(f, source_root)
        text = read_text(f)
        for hit in detect_third_party_fingerprint(rel_path, text, registry=registry):
            item = {"file": rel_path, **hit}
            third_party_items.append(item)
            lib = str(hit.get("library", "unknown"))
            third_party_stats[lib] = third_party_stats.get(lib, 0) + 1

    portrait = {
        "run_id": run_id,
        "generated_at": dt.datetime.now().isoformat(),
        "input_profile": {
            "total_files": sum(ext_stats.values()),
            "ext_stats": ext_stats,
            "origin_stats": origin_stats,
            "top_signals": [{"signal": k, "count": v} for k, v in top_signals],
        },
        "build_profile": {
            "frameworks": frameworks,
            "entry_html_count": len(html_files),
            "js_module_count": len(js_files),
            "module_edge_count": len(module_edges),
            "third_party_stats": third_party_stats,
        },
        "restoration_focus": {
            "first_target": "app_business",
            "second_target": "framework_compiled",
            "skip_default": ["vendor_library", "bundler_runtime"],
        },
    }
    write_json(paths.analysis / "code_portrait.json", portrait)

    md = [
        "# Code Portrait",
        "",
        f"- run_id: `{run_id}`",
        f"- total_files: `{portrait['input_profile']['total_files']}`",
        f"- js_modules: `{portrait['build_profile']['js_module_count']}`",
        f"- module_edges: `{portrait['build_profile']['module_edge_count']}`",
        "",
        "## Framework Guess",
    ]
    if frameworks:
        for fw in frameworks:
            ev = ",".join(fw.get("evidence", []))
            md.append(f"- {fw['name']} (confidence={fw['confidence']}, evidence={ev})")
    else:
        md.append("- unknown")
    md.extend(["", "## Origin Stats"])
    for k, v in sorted(origin_stats.items(), key=lambda x: x[0]):
        md.append(f"- {k}: {v}")
    md.extend(["", "## Top Signals"])
    for item in portrait["input_profile"]["top_signals"][:12]:
        md.append(f"- {item['signal']}: {item['count']}")
    write_text(paths.analysis / "code_portrait.md", "\n".join(md))

    third_party_items.sort(key=lambda x: (x["library"], x["file"]))
    write_json(
        paths.analysis / "third_party_fingerprint.json",
        {
            "run_id": run_id,
            "count": len(third_party_items),
            "stats": third_party_stats,
            "items": third_party_items,
        },
    )
    tp_md = [
        "# Third-party Fingerprint",
        "",
        f"- run_id: `{run_id}`",
        f"- items: `{len(third_party_items)}`",
        "",
        "## Stats",
    ]
    if third_party_stats:
        for k, v in sorted(third_party_stats.items(), key=lambda x: (-x[1], x[0])):
            tp_md.append(f"- {k}: {v}")
    else:
        tp_md.append("- none")
    tp_md.extend(["", "## Samples"])
    if third_party_items:
        for it in third_party_items[:60]:
            ev = ", ".join(it.get("evidence", []))
            tp_md.append(
                f"- {it['file']} -> {it['library']} ({it['kind']}, confidence={it['confidence']}, evidence={ev})"
            )
    else:
        tp_md.append("- none")
    write_text(paths.analysis / "third_party_fingerprint.md", "\n".join(tp_md))
