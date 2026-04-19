from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import (
    collect_files,
    collect_ui_seed_tokens,
    read_text,
    rel,
    score_ui_flow_signal,
    write_json,
    write_text,
)
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def cmd_extract_chains(
    workspace: Path,
    run_id: str,
    cfg: Any,
    load_library_exclude_files: Callable[[Any], set[str]],
    confidence_rank: Callable[[str], int],
) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    source_root = normalized if normalized.is_dir() else raw_snapshot

    origin_path = paths.analysis / "build_origin_report.json"
    origin_by_file: dict[str, str] = {}
    if origin_path.is_file():
        obj = json.loads(read_text(origin_path))
        origin_by_file = {i["file"]: i.get("origin_label", "unknown") for i in obj.get("items", [])}
    library_excludes = load_library_exclude_files(paths)
    file_portrait_path = paths.portraits / "file_portraits.json"
    class_portrait_path = paths.portraits / "class_portraits.json"
    file_priority: dict[str, str] = {}
    class_entities_by_file: dict[str, list[dict[str, Any]]] = {}
    if file_portrait_path.is_file():
        fp_obj = json.loads(read_text(file_portrait_path))
        for it in fp_obj.get("items", []):
            file_priority[str(it.get("file", ""))] = str(it.get("restore_priority", "low"))
    if class_portrait_path.is_file():
        cp_obj = json.loads(read_text(class_portrait_path))
        for it in cp_obj.get("items", []):
            f = str(it.get("file", ""))
            class_entities_by_file.setdefault(f, []).append(it)
        for f, arr in class_entities_by_file.items():
            arr.sort(key=lambda x: int(x.get("line", 10**9)))

    chain_items: list[dict[str, Any]] = []
    chain_idx = 0
    ui_seed_tokens = collect_ui_seed_tokens(source_root)
    call_pat = re.compile(r'([A-Za-z_$][\w$]*)\(\s*["\']([^"\']+)["\']')
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    js_files = collect_files(source_root, {".js"})
    js_files.sort(key=lambda p: (priority_rank.get(file_priority.get(rel(p, source_root), "low"), 9), rel(p, source_root)))
    for f in js_files:
        p = rel(f, source_root)
        if p in library_excludes:
            continue
        layer = origin_by_file.get(p, "unknown")
        if layer in cfg.chain_skip_origin_labels:
            continue
        lines = read_text(f).splitlines()
        for idx, line in enumerate(lines, start=1):
            calls = call_pat.findall(line)
            if not calls:
                continue
            bridge_calls: list[str] = []
            call_symbols: list[str] = []
            for _fn, k in calls:
                kk = k.strip()
                low = kk.lower()
                if low.startswith("./") or low.startswith("../") or low.startswith("assets/") or "/" in low and not low.startswith(("plugin:", "tauri://")):
                    continue
                if any(low.startswith(s) for s in cfg.runtime_command_schemes):
                    bridge_calls.append(kk)
                    call_symbols.append(str(_fn))
                    continue
                if low.startswith(cfg.chain_key_prefixes) and re.fullmatch(r"[a-z0-9_]+", low):
                    bridge_calls.append(kk)
                    call_symbols.append(str(_fn))
                    continue
                if "_" in low and re.fullmatch(r"[a-z][a-z0-9_]{4,}", low):
                    bridge_calls.append(kk)
                    call_symbols.append(str(_fn))
            ui_refs = re.findall(r"[\u4e00-\u9fff]{2,20}", line)
            state_ops: list[str] = []
            if "localStorage" in line or ".setItem(" in line or ".getItem(" in line:
                state_ops.append("local_storage_io")
            if ".value=" in line or ".value =" in line:
                state_ops.append("reactive_value_change")
            trigger = "direct_call"
            if "onClick" in line or "onChange" in line or "onSubmit" in line or "addEventListener" in line:
                trigger = "ui_event"
            elif "listen(" in line or "once(" in line or "emit(" in line or "emitTo(" in line:
                trigger = "event_subscribe"
            if not bridge_calls and not ui_refs and not state_ops:
                continue
            chain_idx += 1
            confidence = "high" if bridge_calls and (ui_refs or state_ops) else ("medium" if bridge_calls else "low")
            if cfg.chain_require_bridge_calls and not bridge_calls:
                continue
            if len(ui_refs) < max(0, cfg.chain_min_ui_refs):
                continue
            if confidence_rank(confidence) < confidence_rank(cfg.chain_min_confidence):
                continue
            ui_flow_score, ui_entry_hits = score_ui_flow_signal(
                line=line,
                trigger=trigger,
                bridge_calls=bridge_calls,
                ui_refs=ui_refs,
                ui_seed_tokens=ui_seed_tokens,
            )
            entities = class_entities_by_file.get(p, [])
            nearest_entity = None
            if entities:
                best = None
                best_dist = 10**9
                for e in entities:
                    ln = int(e.get("line", 0))
                    ln_end = int(e.get("line_end", ln))
                    if ln <= idx <= max(ln, ln_end):
                        d = 0
                    else:
                        d = min(abs(idx - ln), abs(idx - ln_end))
                    if d < best_dist:
                        best_dist = d
                        best = e
                nearest_entity = best
            chain_items.append(
                {
                    "chain_id": f"CHAIN_{chain_idx:04d}",
                    "file": p,
                    "layer": layer,
                    "restore_priority": file_priority.get(p, "low"),
                    "line": idx,
                    "trigger": trigger,
                    "state_ops": sorted(set(state_ops)),
                    "bridge_calls": sorted(set(bridge_calls)),
                    "call_symbols": sorted(set(call_symbols)),
                    "ui_refs": sorted(set(ui_refs)),
                    "ui_flow_score": int(ui_flow_score),
                    "ui_entry_hits": ui_entry_hits,
                    "confidence": confidence,
                    "entity": {
                        "type": str(nearest_entity.get("entity_type")) if nearest_entity else "unknown",
                        "name": str(nearest_entity.get("entity_name")) if nearest_entity else "__unknown__",
                        "line": int(nearest_entity.get("line", 0)) if nearest_entity else 0,
                        "line_end": int(nearest_entity.get("line_end", nearest_entity.get("line", 0))) if nearest_entity else 0,
                    },
                }
            )
    write_json(paths.analysis / "chain_graph.json", {"run_id": run_id, "count": len(chain_items), "items": chain_items})

    ui_flow_items = []
    for c in chain_items:
        if int(c.get("ui_flow_score", 0)) <= 0 and str(c.get("trigger", "")) != "ui_event":
            continue
        file_low = str(c.get("file", "")).lower()
        is_helper_file = any(x in file_low for x in ("vue_export_helper", "_plugin-", "naive-ui", "vendor", "runtime"))
        if is_helper_file and not c.get("ui_refs") and not c.get("ui_entry_hits") and str(c.get("trigger", "")) != "ui_event":
            continue
        ui_flow_items.append(
            {
                "chain_id": c.get("chain_id", ""),
                "file": c.get("file", ""),
                "line": c.get("line", 0),
                "trigger": c.get("trigger", ""),
                "bridge_calls": c.get("bridge_calls", []),
                "ui_refs": c.get("ui_refs", []),
                "state_ops": c.get("state_ops", []),
                "ui_flow_score": int(c.get("ui_flow_score", 0)),
                "ui_entry_hits": c.get("ui_entry_hits", []),
                "confidence": c.get("confidence", "low"),
                "entity": c.get("entity", {}),
            }
        )
    ui_flow_items.sort(
        key=lambda x: (
            -int(x.get("ui_flow_score", 0)),
            0 if str(x.get("confidence", "low")) == "high" else 1,
            x.get("file", ""),
            int(x.get("line", 0)),
        )
    )
    write_json(
        paths.analysis / "ui_flow_chains.json",
        {
            "run_id": run_id,
            "count": len(ui_flow_items),
            "items": ui_flow_items,
            "ui_seed_token_count": len(ui_seed_tokens),
        },
    )
    md = [
        "# UI Flow Chains",
        "",
        f"- run_id: `{run_id}`",
        f"- ui_seed_token_count: `{len(ui_seed_tokens)}`",
        f"- items: `{len(ui_flow_items)}`",
        "",
        "| UI Score | Confidence | File | Entity | Trigger | BridgeCalls |",
        "|---:|---|---|---|---|---|",
    ]
    for it in ui_flow_items[:300]:
        ent = it.get("entity", {}) if isinstance(it.get("entity", {}), dict) else {}
        md.append(
            f"| {it['ui_flow_score']} | {it['confidence']} | {it['file']} | {ent.get('name', '__unknown__')} | {it['trigger']} | {','.join((it.get('bridge_calls', []) or [])[:3])} |"
        )
    write_text(paths.analysis / "ui_flow_chains.md", "\n".join(md))

