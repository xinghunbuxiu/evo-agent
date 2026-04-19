from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import read_text, write_json, write_text
from restorex_lib.run_context import run_paths


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return default
    try:
        obj = json.loads(read_text(path))
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default


def cmd_diagnose_pipeline(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    verify_obj = _load_json(paths.reports / "verify_report.json", {"ok": False, "checks": [], "issues": []})
    semantic_obj = _load_json(paths.analysis / "js_semantic_profile.json", {"summary": {}})
    plan_obj = _load_json(paths.analysis / "restore_script_plan.json", {"stages": []})

    failed_checks = [c for c in verify_obj.get("checks", []) if not c.get("ok")]
    failed_names = {str(c.get("name", "")) for c in failed_checks}

    portrait_related = {
        "file_portraits_contract",
        "class_portraits_contract",
        "third_party_fingerprint_contract",
        "js_semantic_profile_contract",
        "origin_traceability",
    }
    script_related = {
        "reconstructed_executable_contract",
        "reconstructed_no_public_legacy_copy",
        "reconstructed_no_placeholder_shell",
        "rename_plan_consistency",
        "forbidden_rename_violation",
    }
    verify_related = {
        "baseline_hash_consistency",
        "entry_exists_readable",
        "chain_graph_contract",
        "ui_flow_chains_contract",
        "obfuscation_profile_contract",
    }

    root_causes: list[dict[str, Any]] = []
    if failed_names & portrait_related:
        root_causes.append(
            {
                "category": "portrait_insufficient",
                "reason": "画像阶段特征覆盖不足或产物缺失",
                "evidence": sorted(failed_names & portrait_related),
                "suggested_fix": "补充 semantic/third-party/file-class 画像规则并重跑画像阶段",
            }
        )
    if failed_names & script_related:
        root_causes.append(
            {
                "category": "script_generation_issue",
                "reason": "脚本生成或重建阶段未满足可执行契约",
                "evidence": sorted(failed_names & script_related),
                "suggested_fix": "修复重建脚本与输出模板，再执行 build-reconstructed-project/restore-v1",
            }
        )
    if failed_names & verify_related:
        root_causes.append(
            {
                "category": "verification_or_data_issue",
                "reason": "验证契约失败或输入数据异常",
                "evidence": sorted(failed_names & verify_related),
                "suggested_fix": "检查输入完整性与 verify 规则，再复跑验证",
            }
        )

    # 即使 verify 通过，也给出“画像充足度”诊断建议
    summary = semantic_obj.get("summary", {}) if isinstance(semantic_obj.get("summary", {}), dict) else {}
    logger_hits = int(summary.get("logger_like_classes", 0))
    registry_hits = int(summary.get("registry_like_objects", 0))
    if verify_obj.get("ok", False) and (logger_hits == 0 or registry_hits == 0):
        root_causes.append(
            {
                "category": "portrait_improvable",
                "reason": "验证通过但语义命中偏弱，后续还原可读性可能受限",
                "evidence": {"logger_like_classes": logger_hits, "registry_like_objects": registry_hits},
                "suggested_fix": "增强语义规则（spec/semantic_rules.json）并重跑 portrait_core + generated_script",
            }
        )

    if not root_causes:
        root_causes.append(
            {
                "category": "no_blocking_issue",
                "reason": "当前未检测到阻断问题",
                "evidence": [],
                "suggested_fix": "继续推进 UI/SFC 真实还原",
            }
        )

    report = {
        "run_id": run_id,
        "verify_ok": bool(verify_obj.get("ok", False)),
        "failed_checks": sorted(failed_names),
        "semantic_summary": summary,
        "plan_stage_count": len(plan_obj.get("stages", [])) if isinstance(plan_obj.get("stages", []), list) else 0,
        "root_causes": root_causes,
    }
    write_json(paths.reports / "pipeline_diagnosis.json", report)

    md = [
        "# Pipeline Diagnosis",
        "",
        f"- run_id: `{run_id}`",
        f"- verify_ok: `{report['verify_ok']}`",
        f"- failed_checks: `{len(report['failed_checks'])}`",
        f"- plan_stage_count: `{report['plan_stage_count']}`",
        "",
        "## Root Causes",
    ]
    for r in root_causes:
        md.append(f"- [{r['category']}] {r['reason']} | evidence={r.get('evidence')} | fix={r['suggested_fix']}")
    write_text(paths.reports / "pipeline_diagnosis.md", "\n".join(md))
