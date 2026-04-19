from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text, write_json, write_text
from restorex_lib.run_context import run_paths
from restorex_lib.commands.run_index_cmd import refresh_run_index


def cmd_finalize(
    workspace: Path,
    run_id: str,
    cfg: Any,
    load_json_if_exists: Callable[[Path], dict[str, Any]],
) -> None:
    paths = run_paths(workspace, run_id)
    verify_path = paths.reports / "verify_report.json"
    chain_path = paths.analysis / "chain_graph.json"
    symbol_path = paths.analysis / "symbol_map_seed.json"
    origin_path = paths.analysis / "build_origin_report.json"
    ui_flow_path = paths.analysis / "ui_flow_chains.json"
    if not verify_path.is_file():
        raise SystemExit("E_RUNTIME: run verify first")

    verify_obj = json.loads(read_text(verify_path))
    chain_obj = json.loads(read_text(chain_path)) if chain_path.is_file() else {"count": 0, "items": []}
    symbol_obj = json.loads(read_text(symbol_path)) if symbol_path.is_file() else {"count": 0, "items": []}
    origin_obj = json.loads(read_text(origin_path)) if origin_path.is_file() else {"count": 0}
    ui_flow_obj = json.loads(read_text(ui_flow_path)) if ui_flow_path.is_file() else {"count": 0, "items": []}
    mapping_path = paths.analysis / "mapping_index.json"
    mapping_obj = json.loads(read_text(mapping_path)) if mapping_path.is_file() else {"applied_renames": []}
    verify_source_path = paths.reports / "verify_source_report.json"
    verify_source_obj = json.loads(read_text(verify_source_path)) if verify_source_path.is_file() else {}
    obf_path = paths.analysis / "obfuscation_profile.json"
    obf_obj = json.loads(read_text(obf_path)) if obf_path.is_file() else {"summary": {}}
    obf_summary = obf_obj.get("summary", {}) if isinstance(obf_obj.get("summary", {}), dict) else {}
    runtime_evidence_path = paths.analysis / "runtime_evidence.json"
    runtime_obj = (
        json.loads(read_text(runtime_evidence_path))
        if runtime_evidence_path.is_file()
        else {"mode": "unknown", "ingested_count": 0, "chain_confidence_boosted": 0}
    )
    rename_plan_path = paths.analysis / "rename_plan_focus.json"
    rename_plan_obj = json.loads(read_text(rename_plan_path)) if rename_plan_path.is_file() else {"items": []}
    dedupe_path = paths.analysis / "business_flow_dedupe_report.json"
    dedupe_obj = json.loads(read_text(dedupe_path)) if dedupe_path.is_file() else {"summary": {}}
    dedupe_summary = dedupe_obj.get("summary", {}) if isinstance(dedupe_obj.get("summary", {}), dict) else {}

    chain_items = chain_obj.get("items", []) if isinstance(chain_obj.get("items", []), list) else []
    chain_high = sum(1 for i in chain_items if i.get("confidence") == "high")
    chain_medium = sum(1 for i in chain_items if i.get("confidence") == "medium")
    chain_low = sum(1 for i in chain_items if i.get("confidence") == "low")
    ui_flow_count = int(ui_flow_obj.get("count", 0) or 0)
    ui_flow_high = sum(1 for i in ui_flow_obj.get("items", []) if str(i.get("confidence", "low")) == "high")
    rename_auto_apply = sum(1 for i in rename_plan_obj.get("items", []) if i.get("apply"))
    applied_renames = len(mapping_obj.get("applied_renames", []))
    scope_applied_renames = len(mapping_obj.get("scope_applied_renames", []))
    all_renames = list(mapping_obj.get("applied_renames", [])) + list(mapping_obj.get("scope_applied_renames", []))
    top_renames = sorted(all_renames, key=lambda x: int(x.get("replace_count", 0)), reverse=True)[:10]
    suspicious_renames = [
        r
        for r in all_renames
        if len(str(r.get("from", ""))) <= max(0, cfg.suspicious_short_len_max)
        and int(r.get("replace_count", 0)) >= max(1, cfg.suspicious_replace_count_threshold)
    ]
    blocked_suspicious = mapping_obj.get("blocked_suspicious_renames", [])
    scope_unapplied_count = int(mapping_obj.get("scope_unapplied_count", 0) or 0)
    scope_applied_from_dedupe_scope_only = int(mapping_obj.get("scope_applied_from_dedupe_scope_only", 0) or 0)
    verify_checks = verify_obj.get("checks", []) if isinstance(verify_obj.get("checks", []), list) else []
    failed_checks = [c for c in verify_checks if not c.get("ok")]
    runtime_mode = str(runtime_obj.get("mode", "unknown"))

    risk_items: list[str] = []
    if not verify_obj.get("ok", False):
        risk_items.append("verify 未通过，需先处理 checks/issues。")
    if chain_low > 0:
        runtime_boosted = int(runtime_obj.get("chain_confidence_boosted", 0))
        if runtime_mode == "ingested" and runtime_boosted > 0:
            risk_items.append(
                f"仍有 low 置信链路 {chain_low} 条（已命中 runtime 证据 {runtime_boosted} 条，多为弱证据）。"
            )
        else:
            risk_items.append(f"存在 low 置信链路 {chain_low} 条，建议补 runtime evidence。")
    if rename_auto_apply == 0:
        risk_items.append("自动改名为 0，当前规则较保守，readable 可读性提升有限。")
    if runtime_mode in ("pluggable_stub", "unknown"):
        risk_items.append("运行时证据未注入，仅静态证据驱动。")
    elif runtime_mode == "auto_collected_empty":
        scanned = int(runtime_obj.get("log_files_scanned", 0))
        risk_items.append(f"已自动扫描运行日志（{scanned} 个文件）但未命中 bridge 证据。")
    elif runtime_mode == "ingested_empty":
        risk_items.append("已注入运行时证据，但未成功归链到任何链路。")
    if suspicious_renames:
        risk_items.append(f"检测到疑似过拟合改名 {len(suspicious_renames)} 条（短符号高替换次数）。")
    if blocked_suspicious:
        risk_items.append(f"已拦截可疑改名 {len(blocked_suspicious)} 条（策略生效）。")

    next_steps: list[str] = []
    if chain_low > 0 or chain_medium > 0:
        if runtime_mode == "auto_collected_empty":
            next_steps.append("补充含 bridge/command 关键字的真实运行日志后复跑（或手工提供 runtime_evidence.json）。")
        elif runtime_mode in ("pluggable_stub", "unknown"):
            next_steps.append("收集并导入 runtime_evidence.json，提升链路置信度。")
        elif runtime_mode == "ingested_empty":
            next_steps.append("补充包含 command/chain_id 的运行证据（或提高日志颗粒度）后复跑。")
    if len(failed_checks) > 0:
        next_steps.append("逐项修复 verify failed checks 后再 finalize。")
    if rename_auto_apply < 3:
        next_steps.append("可用 balanced 档位复跑，评估可读性提升与风险平衡。")
    if not next_steps:
        next_steps.append("基线已稳定，可作为下一输入包的增量对比起点。")

    source_project_ok = bool(verify_source_obj.get("source_project_ok", False))
    source_build_ok = bool(verify_source_obj.get("source_build_ok", False))
    source_runtime_ok = bool(verify_source_obj.get("source_runtime_ok", False))
    source_bundle_shell_remaining = int(verify_source_obj.get("source_bundle_shell_remaining", 0) or 0)
    source_module_adoption_rate = float(verify_source_obj.get("source_module_adoption_rate", 0) or 0)
    source_entry_mode = str(verify_source_obj.get("source_entry_mode", "unknown"))
    if not source_project_ok:
        risk_items.append("源码工程未通过 verify-source-project。")
    elif source_bundle_shell_remaining > 0:
        risk_items.append(f"源码工程仍残留 bundle 壳特征 {source_bundle_shell_remaining} 处。")

    handoff = {
        "run_id": run_id,
        "finalized_at": dt.datetime.now().isoformat(),
        "verify_ok": verify_obj.get("ok", False),
        "summary": {
            "origin_items": origin_obj.get("count", 0),
            "symbol_candidates": symbol_obj.get("count", 0),
            "chains": chain_obj.get("count", 0),
            "chains_high": chain_high,
            "chains_medium": chain_medium,
            "chains_low": chain_low,
            "ui_flow_chains": ui_flow_count,
            "ui_flow_high": ui_flow_high,
            "rename_auto_apply": rename_auto_apply,
            "applied_renames": applied_renames,
            "scope_applied_renames": scope_applied_renames,
            "applied_renames_total": len(all_renames),
            "runtime_evidence_mode": runtime_obj.get("mode", "unknown"),
            "runtime_boosted_chains": runtime_obj.get("chain_confidence_boosted", 0),
            "suspicious_renames": len(suspicious_renames),
            "blocked_suspicious_renames": len(blocked_suspicious),
            "bundle_obfuscation_level": obf_summary.get("bundle_obfuscation_level", "unknown"),
            "obfuscation_high_files": (obf_summary.get("obfuscation_level_distribution", {}) or {}).get("high", 0),
            "business_flow_dedupe_conflict_groups": int(dedupe_summary.get("conflict_groups", 0) or 0),
            "business_flow_dedupe_kept": int(dedupe_summary.get("kept", 0) or 0),
            "business_flow_dedupe_dropped": int(dedupe_summary.get("dropped", 0) or 0),
            "business_flow_dedupe_scope_bridged": int(dedupe_summary.get("scope_bridged", 0) or 0),
            "scope_unapplied_count": scope_unapplied_count,
            "scope_applied_from_dedupe_scope_only": scope_applied_from_dedupe_scope_only,
            "source_project_ok": source_project_ok,
            "source_build_ok": source_build_ok,
            "source_runtime_ok": source_runtime_ok,
            "source_bundle_shell_remaining": source_bundle_shell_remaining,
            "source_module_adoption_rate": source_module_adoption_rate,
            "source_entry_mode": source_entry_mode,
        },
        "artifacts": {
            "baseline": str(paths.baseline),
            "analysis": str(paths.analysis),
            "restore_v1": str(paths.restore_v1),
            "reports": str(paths.reports),
            "reconstructed_project_raw": str((paths.base / "reconstructed_project_raw")),
            "reconstructed_project_source": str((paths.base / "reconstructed_project_source")),
        },
        "defaults": {
            "static_first": True,
            "runtime_evidence_pluggable": True,
            "auto_rename_scope": "app_business + high_confidence",
        },
    }
    write_json(paths.reports / "handoff_package.json", handoff)

    # 产物边界索引：明确“核心引擎/规则配置/输入/本轮生成”四层，便于交接与复盘。
    spec_dir = workspace / "cache" / "remote"
    spec_files = sorted(str(p.relative_to(workspace)) for p in spec_dir.glob("*.json") if p.is_file())
    profile_files = sorted(str(p.relative_to(workspace)) for p in (spec_dir / "profiles").glob("*.json") if p.is_file())
    core_engine_paths = [
        "plugin/restorex_cli.py",
        "plugin/restorex_lib/",
        "script/run_restorex_all.sh",
        "script/run_release_gate_4_4_11.sh",
        "script/run_h5_quality_batch_strict.sh",
    ]
    input_paths = [
        "input/manifest.json",
        "input/raw_bundle/",
    ]
    reconstructed_project = paths.base / "reconstructed_project"
    run_generated_paths = {
        "run_root": str(paths.base.relative_to(workspace)),
        "baseline": str(paths.baseline.relative_to(workspace)),
        "analysis": str(paths.analysis.relative_to(workspace)),
        "restore_v1": str(paths.restore_v1.relative_to(workspace)),
        "reports": str(paths.reports.relative_to(workspace)),
        "reconstructed_project": str(reconstructed_project.relative_to(workspace)),
    }
    boundary_index = {
        "run_id": run_id,
        "generated_at": dt.datetime.now().isoformat(),
        "layers": {
            "core_engine": {
                "description": "通用可复用引擎代码（跨输入包不变）。",
                "paths": core_engine_paths,
            },
            "rule_spec": {
                "description": "规则配置层（可调、可版本化）。",
                "paths": spec_files + profile_files,
            },
            "input_source": {
                "description": "唯一输入源（原始包与清单）。",
                "paths": input_paths,
            },
            "run_generated": {
                "description": "本轮自动生成产物（可清空重建）。",
                "paths": run_generated_paths,
            },
        },
    }
    write_json(paths.reports / "artifact_boundary_index.json", boundary_index)
    md_boundary = [
        "# Artifact Boundary Index",
        "",
        f"- run_id: `{run_id}`",
        f"- generated_at: `{boundary_index['generated_at']}`",
        "",
        "## Core Engine",
    ]
    for p in core_engine_paths:
        md_boundary.append(f"- `{p}`")
    md_boundary.extend(["", "## Rule Spec"])
    for p in spec_files + profile_files:
        md_boundary.append(f"- `{p}`")
    md_boundary.extend(["", "## Input Source"])
    for p in input_paths:
        md_boundary.append(f"- `{p}`")
    md_boundary.extend(["", "## Run Generated"])
    for k, v in run_generated_paths.items():
        md_boundary.append(f"- {k}: `{v}`")
    write_text(paths.reports / "artifact_boundary_index.md", "\n".join(md_boundary))

    final_summary = {
        "run_id": run_id,
        "generated_at": dt.datetime.now().isoformat(),
        "overview": {
            "verify_ok": verify_obj.get("ok", False),
            "checks_total": len(verify_checks),
            "checks_failed": len(failed_checks),
            "issues_total": len(verify_obj.get("issues", [])),
        },
        "metrics": handoff["summary"],
        "top_applied_renames": top_renames,
        "suspicious_renames": suspicious_renames[:30],
        "blocked_suspicious_renames": blocked_suspicious[:30],
        "failed_checks": failed_checks,
        "risk_items": risk_items,
        "next_steps": next_steps,
    }
    write_json(paths.reports / "final_summary.json", final_summary)

    md = [
        "# Final Handoff",
        "",
        f"- run_id: `{run_id}`",
        f"- verify_ok: `{handoff['verify_ok']}`",
        f"- origin_items: `{handoff['summary']['origin_items']}`",
        f"- symbol_candidates: `{handoff['summary']['symbol_candidates']}`",
        f"- chains: `{handoff['summary']['chains']}`",
        f"- ui_flow_chains: `{handoff['summary']['ui_flow_chains']}`",
        "",
        "## Artifact Paths",
        f"- baseline: `{handoff['artifacts']['baseline']}`",
        f"- analysis: `{handoff['artifacts']['analysis']}`",
        f"- restore_v1: `{handoff['artifacts']['restore_v1']}`",
        f"- reports: `{handoff['artifacts']['reports']}`",
        "",
        "## Final Summary",
        f"- checks_failed: `{len(failed_checks)}`",
        f"- chains(high/medium/low): `{chain_high}/{chain_medium}/{chain_low}`",
        f"- ui_flow(high/total): `{ui_flow_high}/{ui_flow_count}`",
        f"- rename_auto_apply: `{rename_auto_apply}`",
        f"- applied_renames: `{applied_renames}`",
        f"- scope_applied_renames: `{scope_applied_renames}`",
        f"- applied_renames_total: `{len(all_renames)}`",
        f"- business_flow_dedupe(conflict/kept/dropped/scope): `{int(dedupe_summary.get('conflict_groups', 0) or 0)}/{int(dedupe_summary.get('kept', 0) or 0)}/{int(dedupe_summary.get('dropped', 0) or 0)}/{int(dedupe_summary.get('scope_bridged', 0) or 0)}`",
        f"- scope_resolution(applied/unapplied): `{scope_applied_from_dedupe_scope_only}/{scope_unapplied_count}`",
        f"- runtime_evidence_mode: `{runtime_obj.get('mode', 'unknown')}`",
        "",
        "## Risks",
    ]
    if risk_items:
        for item in risk_items:
            md.append(f"- {item}")
    else:
        md.append("- 当前未发现新增风险。")
    md.extend(["", "## Next Steps"])
    for step in next_steps:
        md.append(f"- {step}")
    write_text(paths.reports / "handoff_package.md", "\n".join(md))
    write_text(paths.reports / "final_summary.md", "\n".join(md))
    refresh_run_index(workspace, load_json_if_exists=load_json_if_exists)
