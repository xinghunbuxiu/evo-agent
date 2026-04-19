from __future__ import annotations

import json
import glob
import re
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text, write_json
from restorex_lib.run_context import run_paths


def cmd_runtime_evidence_stub(workspace: Path, run_id: str, force: bool = False) -> None:
    paths = run_paths(workspace, run_id)
    runtime_path = paths.analysis / "runtime_evidence.json"
    if runtime_path.is_file() and not force:
        try:
            cur = json.loads(read_text(runtime_path))
        except Exception:
            cur = {}
        mode = str(cur.get("mode", "")).strip()
        # 避免二次执行 all 时覆盖掉已导入的 runtime 证据。
        if mode in {"ingested", "auto_collected"}:
            return
    payload = {
        "run_id": run_id,
        "mode": "pluggable_stub",
        "status": "not_collected",
        "note": "默认静态优先，运行时证据可后续注入并回填 confidence。",
        "items": [],
    }
    write_json(runtime_path, payload)


def cmd_ingest_runtime_evidence(
    workspace: Path,
    run_id: str,
    runtime_evidence_path: str,
    *,
    confidence_rank: Callable[[str], int],
) -> None:
    paths = run_paths(workspace, run_id)
    chain_path = paths.analysis / "chain_graph.json"
    if not chain_path.is_file():
        raise SystemExit("E_RUNTIME: run extract-chains first")
    ext_path = Path(runtime_evidence_path).expanduser().resolve()
    if not ext_path.is_file():
        raise SystemExit(f"E_RUNTIME: runtime evidence file not found: {ext_path}")

    chain_obj = json.loads(read_text(chain_path))
    ext_obj = json.loads(read_text(ext_path))
    ext_items = ext_obj.get("items", []) if isinstance(ext_obj, dict) else []

    by_chain: dict[str, list[dict[str, Any]]] = {}
    unmatched_items: list[dict[str, Any]] = []
    auto_matched = 0

    def _tokenize(text: str) -> list[str]:
        parts = re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", text or "")
        return [p for p in parts if len(p) >= 2]

    # 1) 先吃 direct chain_id 命中
    for item in ext_items:
        cid = str(item.get("chain_id", "")).strip()
        if cid:
            by_chain.setdefault(cid, []).append(item)
        else:
            unmatched_items.append(item)

    # 2) 再对无 chain_id 的证据做自动归链（file/line/关键词/bridge 打分）
    chain_items = chain_obj.get("items", [])
    for item in unmatched_items:
        item_file = str(item.get("file", "")).strip()
        item_file_name = Path(item_file).name if item_file else ""
        item_line_raw = item.get("line", None)
        try:
            item_line = int(item_line_raw) if item_line_raw is not None else None
        except Exception:
            item_line = None
        detail = str(item.get("detail", "")).strip()
        command = str(item.get("command", "")).strip()
        event = str(item.get("event", "")).strip()
        module_kind = str(item.get("module_kind", "")).strip()
        module_name = str(item.get("module_name", "")).strip()
        tokens = _tokenize(" ".join([detail, command, event]))

        best_chain_id = ""
        best_score = 0
        for c in chain_items:
            c_file = str(c.get("file", "")).strip()
            c_line_raw = c.get("line", None)
            try:
                c_line = int(c_line_raw) if c_line_raw is not None else None
            except Exception:
                c_line = None
            c_blob = " ".join(
                [
                    str(c.get("trigger", "")),
                    " ".join([str(x) for x in c.get("state_ops", [])]),
                    " ".join([str(x) for x in c.get("bridge_calls", [])]),
                    " ".join([str(x) for x in c.get("ui_refs", [])]),
                ]
            )

            score = 0
            if item_file:
                if c_file == item_file:
                    score += 6
                elif item_file_name and Path(c_file).name == item_file_name:
                    score += 4
            if item_line is not None and c_line is not None:
                if abs(item_line - c_line) <= 5:
                    score += 3
                elif abs(item_line - c_line) <= 15:
                    score += 1
            if command and command in [str(x) for x in c.get("bridge_calls", [])]:
                # 命令直连是最强信号：允许无 file/line 的 runtime 证据也能稳定归链。
                score += 6
            token_hits = 0
            for t in tokens:
                if t and t in c_blob:
                    token_hits += 1
            score += min(4, token_hits)
            if module_kind == "runtime_segments" and module_name:
                module_tokens = [t for t in _tokenize(module_name.replace("-", "_")) if len(t) >= 3]
                module_hits = 0
                for mt in module_tokens:
                    if mt and mt in c_blob:
                        module_hits += 1
                if module_hits >= 2:
                    score += 5
                elif module_hits == 1:
                    score += 2

            if score > best_score:
                best_score = score
                best_chain_id = str(c.get("chain_id", "")).strip()

        # 阈值策略：至少有一类强信号才自动归链，避免误绑
        if best_chain_id and best_score >= 5:
            bind_item = dict(item)
            bind_item["matched_by"] = "heuristic"
            bind_item["matched_chain_id"] = best_chain_id
            bind_item["matched_score"] = best_score
            by_chain.setdefault(best_chain_id, []).append(bind_item)
            auto_matched += 1

    boosted = 0
    boosted_high = 0
    boosted_medium = 0
    for c in chain_obj.get("items", []):
        hit = by_chain.get(c.get("chain_id", ""), [])
        if hit:
            c["runtime_hits"] = len(hit)
            bridge_set = {str(x) for x in c.get("bridge_calls", [])}
            has_strong_direct_command = any(
                str(hh.get("command", "")).strip() in bridge_set
                and str(hh.get("source", "")) != "auto_module_bridge_hint"
                for hh in hit
            )
            cur_conf = str(c.get("confidence", "low"))
            if has_strong_direct_command:
                if cur_conf != "high":
                    boosted_high += 1
                c["confidence"] = "high"
            else:
                # 仅弱证据（含 module hint direct command / 启发式命中）时，最多提升到 medium。
                if confidence_rank(cur_conf) < confidence_rank("medium"):
                    c["confidence"] = "medium"
                    boosted_medium += 1
            boosted += 1

    write_json(chain_path, chain_obj)
    runtime_mode = "ingested" if (boosted > 0 or auto_matched > 0) else "ingested_empty"
    runtime_payload = {
        "run_id": run_id,
        "mode": runtime_mode,
        "source_file": str(ext_path),
        "ingested_count": len(ext_items),
        "chain_confidence_boosted": boosted,
        "chain_confidence_boosted_high": boosted_high,
        "chain_confidence_boosted_medium": boosted_medium,
        "auto_matched_without_chain_id": auto_matched,
        "unmatched_without_chain_id": max(0, len(unmatched_items) - auto_matched),
        "items": ext_items,
    }
    write_json(paths.analysis / "runtime_evidence.json", runtime_payload)


def cmd_collect_runtime_evidence(
    workspace: Path,
    run_id: str,
    log_glob: str = "",
    limit: int = 3000,
    prefer_direct: bool = True,
) -> Path:
    paths = run_paths(workspace, run_id)
    chain_path = paths.analysis / "chain_graph.json"
    if not chain_path.is_file():
        raise SystemExit("E_RUNTIME: run extract-chains first")

    chain_obj = json.loads(read_text(chain_path))
    bridge_calls: set[str] = set()
    for c in chain_obj.get("items", []):
        for b in c.get("bridge_calls", []):
            s = str(b).strip()
            if s:
                bridge_calls.add(s)
    if not bridge_calls:
        raise SystemExit("E_RUNTIME: no bridge_calls in chain_graph")

    candidates: list[Path] = []
    ignored_roots = {
        str((workspace / "output").resolve()),
        str((workspace / "docs").resolve()),
        str((workspace / "cache" / "remote").resolve()),
        str((workspace / "plugin").resolve()),
        str((workspace / "workflow").resolve()),
    }

    def should_include_file(p: Path) -> bool:
        try:
            rp = p.resolve()
        except Exception:
            return False
        if not rp.is_file():
            return False
        s = str(rp)
        for ir in ignored_roots:
            if s.startswith(ir + "/") or s == ir:
                return False
        if rp.suffix.lower() in {".md", ".markdown"}:
            return False
        if rp.name in {
            "chain_graph.json",
            "rename_plan_focus.json",
            "symbol_map_seed.json",
            "build_origin_report.json",
            "framework_inventory.md",
            "evidence_matrix.md",
            "evidence_matrix.json",
        }:
            return False
        return rp.suffix.lower() in {".log", ".txt", ".jsonl", ".json"}

    if log_glob.strip():
        for p in glob.glob(log_glob.strip()):
            pp = Path(p)
            if should_include_file(pp):
                candidates.append(pp)
    else:
        default_roots = [
            workspace / "input" / "runtime_logs",
            workspace / "input" / "logs",
            workspace.parent / "runtime_logs",
            workspace.parent / "build_info" / "runtime_logs",
            workspace.parent / "build_info" / "app_clone" / "runtime_logs",
        ]
        for root in default_roots:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if should_include_file(p):
                    candidates.append(p)

    # 去重 + 稳定排序
    uniq_files = sorted({str(p.resolve()) for p in candidates})
    cmd_regex = re.compile(
        r"\bplugin:[a-zA-Z0-9_-]+\|[a-zA-Z0-9_]+\b|\b(?:get_|set_|open_|start_|stop_|create_|login_|fetch_|check_|clear_|copy_|select_|restore_|download_|toggle_|one_click_)[A-Za-z0-9_]+\b"
    )
    broad_snake_regex = re.compile(r"\b[a-z][a-z0-9_]{3,}\b")
    json_cmd_regex = re.compile(r'"(?:command|cmd|bridge_call)"\s*:\s*"([A-Za-z0-9_:\-|]+)"')
    json_chain_regex = re.compile(r'"chain_id"\s*:\s*"(CHAIN_[A-Za-z0-9_]+)"')
    json_event_regex = re.compile(r'"event"\s*:\s*"([A-Za-z0-9_:\-|]+)"')
    module_load_regex = re.compile(r"/recovered/(runtime_segments)/([A-Za-z0-9_.-]+)\.segment\.js")
    bridge_tokens = sorted(bridge_calls, key=len, reverse=True)
    invoke_cmd_regex = re.compile(r'invoke\(\s*["\']([A-Za-z0-9_:\-|]+)["\']')

    segment_dirs = [
        workspace.parent / "source" / "restored_source_tauri" / "src" / "recovered" / "runtime_segments",
        workspace.parent / "source" / "restored_source_tauri" / "dist" / "recovered" / "runtime_segments",
    ]
    module_cmd_cache: dict[str, list[str]] = {}

    def get_module_bridge_commands(module_name: str) -> list[str]:
        if module_name in module_cmd_cache:
            return module_cmd_cache[module_name]
        commands: set[str] = set()
        for seg_dir in segment_dirs:
            seg_file = seg_dir / f"{module_name}.segment.js"
            if not seg_file.is_file():
                continue
            try:
                seg_text = read_text(seg_file)
            except Exception:
                continue
            for m in invoke_cmd_regex.findall(seg_text):
                cmd = str(m).strip()
                if cmd and cmd in bridge_calls:
                    commands.add(cmd)
            # 兜底：按 bridge token 直接扫描段文件。
            if not commands:
                for bt in bridge_tokens:
                    if bt and bt in seg_text:
                        commands.add(bt)
        out = sorted(commands)
        module_cmd_cache[module_name] = out
        return out

    items: list[dict[str, Any]] = []
    module_hint_seen: set[tuple[str, str]] = set()
    for fp in uniq_files:
        path = Path(fp)
        try:
            text = read_text(path)
        except Exception:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            line_chain_id = ""
            line_event = ""
            m_cid = json_chain_regex.search(line)
            if m_cid:
                line_chain_id = m_cid.group(1).strip()
            m_evt = json_event_regex.search(line)
            if m_evt:
                line_event = m_evt.group(1).strip()
            found: list[str] = []
            # 优先使用 chain_graph 中真实 bridge token 直接匹配，减少正则漏检。
            for bt in bridge_tokens:
                if bt and bt in line:
                    found.append(bt)
            if not found:
                for m in json_cmd_regex.findall(line):
                    token = str(m).strip()
                    if token and token in bridge_calls:
                        found.append(token)
            if not found:
                found = cmd_regex.findall(line)
            if not found:
                # 兜底：宽松抽取 snake_case token，再与 bridge catalog 求交集。
                broad = broad_snake_regex.findall(line)
                found = [tk for tk in broad if tk in bridge_calls]
            if not found:
                # 模块加载线索（非 direct command）：可用于启发式归链。
                mm = module_load_regex.search(line)
                if mm:
                    module_kind = mm.group(1)
                    module_name = mm.group(2)
                    module_cmds = get_module_bridge_commands(module_name)
                    for cmd in module_cmds:
                        dedup_key = (module_name, cmd)
                        if dedup_key in module_hint_seen:
                            continue
                        module_hint_seen.add(dedup_key)
                        items.append(
                            {
                                "source": "auto_module_bridge_hint",
                                "file": path.name,
                                "line": idx,
                                "module_kind": module_kind,
                                "module_name": module_name,
                                "command": cmd,
                                "detail": line.strip()[:500],
                            }
                        )
                        if len(items) >= max(1, limit):
                            break
                    if len(items) >= max(1, limit):
                        break
                continue
            found = list(dict.fromkeys(found))
            for token in found:
                if token not in bridge_calls:
                    continue
                items.append(
                    {
                        "source": "auto_log_scan",
                        "file": path.name,
                        "line": idx,
                        "command": token,
                        "chain_id": line_chain_id,
                        "event": line_event,
                        "detail": line.strip()[:500],
                    }
                )
                if len(items) >= max(1, limit):
                    break
            if len(items) >= max(1, limit):
                break
        if len(items) >= max(1, limit):
            break

    out = paths.analysis / "runtime_evidence.auto_collected.json"
    direct_items = [it for it in items if str(it.get("source", "")) == "auto_log_scan"]
    hint_items = [it for it in items if str(it.get("source", "")) == "auto_module_bridge_hint"]
    if prefer_direct and direct_items:
        # 一旦存在 direct 执行证据，优先仅输出 direct，避免弱 module hint 稀释置信提升。
        items = direct_items
    write_json(
        out,
        {
            "run_id": run_id,
            "mode": "auto_collected",
            "bridge_catalog_size": len(bridge_calls),
            "log_files_scanned": len(uniq_files),
            "log_files_sample": uniq_files[:20],
            "prefer_direct": bool(prefer_direct),
            "direct_items_count": len(direct_items),
            "module_hint_items_count": len(hint_items),
            "items": items,
        },
    )
    return out
