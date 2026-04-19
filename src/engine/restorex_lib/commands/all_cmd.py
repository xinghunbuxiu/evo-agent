from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text, write_json
from restorex_lib.run_context import run_paths


def cmd_all(
    workspace: Path,
    run_id: str,
    cfg: Any,
    emit_raw_runtime: bool = False,
    auto_runtime_evidence: bool = False,
    runtime_log_glob: str = "",
    runtime_collect_limit: int = 3000,
    runtime_prefer_direct: bool = True,
    *,
    cmd_init_run: Callable[..., None],
    cmd_normalize: Callable[..., None],
    cmd_infer_build_origin: Callable[..., None],
    cmd_scan_structure: Callable[..., None],
    cmd_build_portrait: Callable[..., None],
    cmd_build_file_portraits: Callable[..., None],
    cmd_build_class_portraits: Callable[..., None],
    cmd_build_method_portraits: Callable[..., None],
    cmd_build_constant_portraits: Callable[..., None],
    cmd_build_js_semantic_profile: Callable[..., None],
    cmd_build_restore_script_plan: Callable[..., None],
    cmd_build_feedback: Callable[..., None],
    cmd_analyze_obfuscation: Callable[..., None],
    cmd_build_library_match: Callable[..., None],
    cmd_extract_chains: Callable[..., None],
    cmd_build_evidence: Callable[..., None],
    cmd_bootstrap_source_rules: Callable[..., None],
    cmd_decompile_bundle_structure: Callable[..., None],
    cmd_extract_source_modules: Callable[..., None],
    cmd_build_source_graph: Callable[..., None],
    cmd_collect_runtime_evidence: Callable[..., Path],
    cmd_ingest_runtime_evidence: Callable[..., None],
    cmd_runtime_evidence_stub: Callable[..., None],
    cmd_restore_v1: Callable[..., None],
    cmd_build_reconstructed_project: Callable[..., None],
    cmd_build_source_project: Callable[..., None],
    cmd_verify: Callable[..., None],
    cmd_verify_source_project: Callable[..., None],
    cmd_diagnose_pipeline: Callable[..., None],
    cmd_finalize: Callable[..., None],
) -> None:
    """全流程编排（单 run 内闭环）。

    设计原则：
    - 先“画像/证据”，再“还原/重建”，最后“验证/反馈/诊断/收尾”。
    - runtime 证据是增强项，不应破坏主线可重复性。
    """
    # 1) 基线与静态画像阶段
    cmd_init_run(workspace, run_id, cfg, emit_raw_runtime=emit_raw_runtime)
    cmd_normalize(workspace, run_id)
    cmd_infer_build_origin(workspace, run_id)
    cmd_scan_structure(workspace, run_id)
    cmd_build_portrait(workspace, run_id)
    cmd_build_file_portraits(workspace, run_id)
    cmd_build_class_portraits(workspace, run_id)
    cmd_build_method_portraits(workspace, run_id)
    cmd_build_constant_portraits(workspace, run_id)
    cmd_build_js_semantic_profile(workspace, run_id)
    cmd_analyze_obfuscation(workspace, run_id)
    cmd_build_library_match(workspace, run_id)
    cmd_extract_chains(workspace, run_id, cfg)
    cmd_build_evidence(workspace, run_id, cfg)
    cmd_build_restore_script_plan(workspace, run_id)
    # 2) 可选 runtime 证据回灌（用于提升链路置信度）
    if auto_runtime_evidence:
        collected = cmd_collect_runtime_evidence(
            workspace,
            run_id,
            log_glob=runtime_log_glob,
            limit=runtime_collect_limit,
            prefer_direct=runtime_prefer_direct,
        )
        try:
            collected_obj = json.loads(read_text(collected))
        except Exception:
            collected_obj = {}
        collected_items = collected_obj.get("items", []) if isinstance(collected_obj, dict) else []
        if collected_items:
            cmd_ingest_runtime_evidence(workspace, run_id, str(collected))
            # ingest 会提升 chain_graph 置信度，重新构建 evidence_matrix 以保持一致。
            cmd_build_evidence(workspace, run_id, cfg)
        else:
            paths = run_paths(workspace, run_id)
            runtime_payload = {
                "run_id": run_id,
                "mode": "auto_collected_empty",
                "status": "no_runtime_hits",
                "source_file": str(collected),
                "bridge_catalog_size": int(collected_obj.get("bridge_catalog_size", 0)) if isinstance(collected_obj, dict) else 0,
                "log_files_scanned": int(collected_obj.get("log_files_scanned", 0)) if isinstance(collected_obj, dict) else 0,
                "ingested_count": 0,
                "chain_confidence_boosted": 0,
                "items": [],
            }
            write_json(paths.analysis / "runtime_evidence.json", runtime_payload)
    else:
        cmd_runtime_evidence_stub(workspace, run_id)
    # 3) 还原与重建
    cmd_restore_v1(workspace, run_id, cfg, emit_raw_runtime=emit_raw_runtime)
    cmd_bootstrap_source_rules(workspace, run_id)
    cmd_decompile_bundle_structure(workspace, run_id)
    cmd_extract_source_modules(workspace, run_id)
    cmd_build_source_graph(workspace, run_id)
    cmd_build_reconstructed_project(workspace, run_id)
    cmd_build_source_project(workspace, run_id)
    # 4) 验证与反馈闭环
    # 第一轮 verify 产出基础验证报告，供 feedback 阶段使用。
    cmd_verify(workspace, run_id, cfg)
    cmd_verify_source_project(workspace, run_id)
    cmd_build_feedback(workspace, run_id)
    # feedback/calibration 生成后再跑一次 verify，确保最终报告包含该契约状态。
    cmd_verify(workspace, run_id, cfg)
    cmd_verify_source_project(workspace, run_id)
    # 5) 诊断与收尾交付
    cmd_diagnose_pipeline(workspace, run_id)
    cmd_finalize(workspace, run_id, cfg)
