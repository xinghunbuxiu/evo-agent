#!/usr/bin/env python3
from __future__ import annotations

"""RestoreX CLI 入口（薄入口）

职责边界：
1. 参数解析与运行环境准备（workspace、formatter）。
2. 命令分发适配（交给 main_adapter/main_dispatch）。
3. 依赖注入（把各命令实现函数注入编排层）。

不在这里放业务策略，策略统一在 commands/* 与 spec/*。
"""

from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import ensure_formatters_available, read_text
from restorex_lib.run_context import get_run_id
from restorex_lib.commands.main_parser_cmd import build_parser as build_parser_impl
from restorex_lib.commands.main_dispatch_cmd import (
    handle_pre_dispatch as handle_pre_dispatch_impl,
    handle_run_dispatch as handle_run_dispatch_impl,
)
from restorex_lib.commands.main_adapter_cmd import run_main_adapter as run_main_adapter_impl
from restorex_lib.commands.status_cmd import cmd_status as cmd_status_impl
from restorex_lib.commands.compare_cmd import (
    cmd_compare_profiles as cmd_compare_profiles_impl,
    cmd_compare_existing_runs as cmd_compare_existing_runs_impl,
)
from restorex_lib.commands.all_cmd import cmd_all as cmd_all_impl
from restorex_lib.commands.init_cmd import (
    confidence_rank as confidence_rank_impl,
    cmd_init_run as cmd_init_run_impl,
)
from restorex_lib.commands.chains_cmd import cmd_extract_chains as cmd_extract_chains_impl
from restorex_lib.commands.evidence_cmd import cmd_build_evidence as cmd_build_evidence_impl
from restorex_lib.commands.restore_cmd import (
    cmd_restore_v1 as cmd_restore_v1_impl,
    cmd_apply_scope_renames as cmd_apply_scope_renames_impl,
)
from restorex_lib.commands.scope_cmd import run_scope_rename_pass as run_scope_rename_pass_impl
from restorex_lib.commands.finalize_cmd import cmd_finalize as cmd_finalize_impl
from restorex_lib.commands.runtime_evidence_cmd import (
    cmd_ingest_runtime_evidence as cmd_ingest_runtime_evidence_impl,
    cmd_runtime_evidence_stub as cmd_runtime_evidence_stub_impl,
    cmd_collect_runtime_evidence as cmd_collect_runtime_evidence_impl,
)
from restorex_lib.commands.transform_cmd import (
    try_external_format as try_external_format_impl,
    normalize_code_text as normalize_code_text_impl,
    safe_symbol_replace as safe_symbol_replace_impl,
    apply_scoped_symbol_replace as apply_scoped_symbol_replace_impl,
    apply_scoped_call_symbol_replace as apply_scoped_call_symbol_replace_impl,
    bridge_token_to_candidate as bridge_token_to_candidate_impl,
    cmd_normalize as cmd_normalize_impl,
)
from restorex_lib.commands.library_match_cmd import (
    cmd_build_library_match as cmd_build_library_match_impl,
    load_library_exclude_files as load_library_exclude_files_impl,
)
from restorex_lib.commands.structure_cmd import (
    cmd_infer_build_origin as cmd_infer_build_origin_impl,
    cmd_scan_structure as cmd_scan_structure_impl,
    cmd_build_portrait as cmd_build_portrait_impl,
)
from restorex_lib.commands.portraits_cmd import (
    cmd_build_file_portraits as cmd_build_file_portraits_impl,
    cmd_build_class_portraits as cmd_build_class_portraits_impl,
    cmd_build_method_portraits as cmd_build_method_portraits_impl,
    cmd_build_constant_portraits as cmd_build_constant_portraits_impl,
)
from restorex_lib.commands.semantic_profile_cmd import (
    cmd_build_js_semantic_profile as cmd_build_js_semantic_profile_impl,
)
from restorex_lib.commands.script_plan_cmd import (
    cmd_build_restore_script_plan as cmd_build_restore_script_plan_impl,
)
from restorex_lib.commands.feedback_cmd import (
    cmd_build_feedback as cmd_build_feedback_impl,
)
from restorex_lib.commands.diagnose_cmd import (
    cmd_diagnose_pipeline as cmd_diagnose_pipeline_impl,
)
from restorex_lib.commands.source_reconstruction_cmd import (
    cmd_bootstrap_source_rules as cmd_bootstrap_source_rules_impl,
    cmd_decompile_bundle_structure as cmd_decompile_bundle_structure_impl,
    cmd_extract_source_modules as cmd_extract_source_modules_impl,
    cmd_build_source_graph as cmd_build_source_graph_impl,
    cmd_build_source_project as cmd_build_source_project_impl,
)
from restorex_lib.commands.obfuscation_cmd import cmd_analyze_obfuscation as cmd_analyze_obfuscation_impl
from restorex_lib.commands.reconstructed_cmd import cmd_build_reconstructed_project as cmd_build_reconstructed_project_impl
from restorex_lib.commands.verify_cmd import cmd_verify as cmd_verify_impl
from restorex_lib.commands.verify_source_cmd import cmd_verify_source_project as cmd_verify_source_project_impl
from restorex_lib.config_rules import (
    RuleConfig,
    load_json_if_exists as load_json_if_exists_impl,
    load_rule_config as load_rule_config_impl,
)

SUPPORTED_EXTS = {".html", ".js", ".css", ".svg"}


def cmd_init_run(workspace: Path, run_id: str, cfg: RuleConfig, emit_raw_runtime: bool = False) -> None:
    cmd_init_run_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        supported_exts=SUPPORTED_EXTS,
        emit_raw_runtime=emit_raw_runtime,
    )


def cmd_extract_chains(workspace: Path, run_id: str, cfg: RuleConfig) -> None:
    cmd_extract_chains_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        load_library_exclude_files=load_library_exclude_files_impl,
        confidence_rank=confidence_rank_impl,
    )


def cmd_build_evidence(workspace: Path, run_id: str, cfg: RuleConfig) -> None:
    cmd_build_evidence_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        bridge_token_to_candidate=bridge_token_to_candidate_impl,
        load_library_exclude_files=load_library_exclude_files_impl,
        confidence_rank=confidence_rank_impl,
    )


def _run_scope_rename_pass(
    readable: Path,
    paths: Any,
    cfg: RuleConfig,
    preferred_targets_by_file: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return run_scope_rename_pass_impl(
        readable=readable,
        paths=paths,
        cfg=cfg,
        preferred_targets_by_file=preferred_targets_by_file,
        apply_scoped_call_symbol_replace=apply_scoped_call_symbol_replace_impl,
        apply_scoped_symbol_replace=apply_scoped_symbol_replace_impl,
    )


def cmd_restore_v1(workspace: Path, run_id: str, cfg: RuleConfig, emit_raw_runtime: bool = False) -> None:
    cmd_restore_v1_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        emit_raw_runtime=emit_raw_runtime,
        safe_symbol_replace=safe_symbol_replace_impl,
        try_external_format=try_external_format_impl,
        normalize_code_text=normalize_code_text_impl,
        run_scope_rename_pass=_run_scope_rename_pass,
    )


def cmd_finalize(workspace: Path, run_id: str, cfg: RuleConfig) -> None:
    cmd_finalize_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        load_json_if_exists=load_json_if_exists_impl,
    )


def cmd_ingest_runtime_evidence(workspace: Path, run_id: str, runtime_evidence_path: str) -> None:
    cmd_ingest_runtime_evidence_impl(
        workspace=workspace,
        run_id=run_id,
        runtime_evidence_path=runtime_evidence_path,
        confidence_rank=confidence_rank_impl,
    )


def cmd_all(
    workspace: Path,
    run_id: str,
    cfg: RuleConfig,
    emit_raw_runtime: bool = False,
    auto_runtime_evidence: bool = False,
    runtime_log_glob: str = "",
    runtime_collect_limit: int = 3000,
    runtime_prefer_direct: bool = True,
) -> None:
    # all 是唯一“端到端”编排入口：从输入扫描到最终收尾报告。
    cmd_all_impl(
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        emit_raw_runtime=emit_raw_runtime,
        auto_runtime_evidence=auto_runtime_evidence,
        runtime_log_glob=runtime_log_glob,
        runtime_collect_limit=runtime_collect_limit,
        runtime_prefer_direct=runtime_prefer_direct,
        cmd_init_run=cmd_init_run,
        cmd_normalize=cmd_normalize_impl,
        cmd_infer_build_origin=cmd_infer_build_origin_impl,
        cmd_scan_structure=cmd_scan_structure_impl,
        cmd_build_portrait=cmd_build_portrait_impl,
        cmd_build_file_portraits=cmd_build_file_portraits_impl,
        cmd_build_class_portraits=cmd_build_class_portraits_impl,
        cmd_build_method_portraits=cmd_build_method_portraits_impl,
        cmd_build_constant_portraits=cmd_build_constant_portraits_impl,
        cmd_build_js_semantic_profile=cmd_build_js_semantic_profile_impl,
        cmd_build_restore_script_plan=cmd_build_restore_script_plan_impl,
        cmd_build_feedback=cmd_build_feedback_impl,
        cmd_analyze_obfuscation=cmd_analyze_obfuscation_impl,
        cmd_build_library_match=cmd_build_library_match_impl,
        cmd_extract_chains=cmd_extract_chains,
        cmd_build_evidence=cmd_build_evidence,
        cmd_bootstrap_source_rules=cmd_bootstrap_source_rules_impl,
        cmd_decompile_bundle_structure=cmd_decompile_bundle_structure_impl,
        cmd_extract_source_modules=cmd_extract_source_modules_impl,
        cmd_build_source_graph=cmd_build_source_graph_impl,
        cmd_collect_runtime_evidence=cmd_collect_runtime_evidence_impl,
        cmd_ingest_runtime_evidence=cmd_ingest_runtime_evidence,
        cmd_runtime_evidence_stub=cmd_runtime_evidence_stub_impl,
        cmd_restore_v1=cmd_restore_v1,
        cmd_build_reconstructed_project=cmd_build_reconstructed_project_impl,
        cmd_build_source_project=cmd_build_source_project_impl,
        cmd_verify=cmd_verify_impl,
        cmd_verify_source_project=cmd_verify_source_project_impl,
        cmd_diagnose_pipeline=cmd_diagnose_pipeline_impl,
        cmd_finalize=cmd_finalize,
    )


def cmd_compare_profiles(workspace: Path, profiles: list[str]) -> Path:
    return cmd_compare_profiles_impl(
        workspace=workspace,
        profiles=profiles,
        load_rule_config=load_rule_config_impl,
        now_run_id=lambda: get_run_id(workspace, None),
        cmd_all=cmd_all,
    )


def cmd_status(workspace: Path, run_id: str = "") -> dict[str, Any]:
    return cmd_status_impl(workspace=workspace, run_id=run_id, read_text=read_text)


def main() -> int:
    parser = build_parser_impl()
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    # 统一在入口保证格式化工具可用，避免后续步骤因环境差异中断。
    ensure_formatters_available(workspace)

    def _cmd_apply_scope_renames(workspace: Path, run_id: str, cfg: RuleConfig) -> None:
        cmd_apply_scope_renames_impl(
            workspace=workspace,
            run_id=run_id,
            cfg=cfg,
            run_scope_rename_pass=_run_scope_rename_pass,
        )

    # 通过 adapter 做统一 pre-dispatch/run-dispatch，保证 CLI 输出格式稳定。
    exit_code, lines = run_main_adapter_impl(
        args=args,
        workspace=workspace,
        get_run_id=get_run_id,
        load_rule_config=load_rule_config_impl,
        handle_pre_dispatch=handle_pre_dispatch_impl,
        handle_run_dispatch=handle_run_dispatch_impl,
        cmd_compare_profiles=cmd_compare_profiles,
        cmd_compare_existing_runs=cmd_compare_existing_runs_impl,
        cmd_status=cmd_status,
        cmd_init_run=cmd_init_run,
        cmd_normalize=cmd_normalize_impl,
        cmd_infer_build_origin=cmd_infer_build_origin_impl,
        cmd_scan_structure=cmd_scan_structure_impl,
        cmd_build_portrait=cmd_build_portrait_impl,
        cmd_build_file_portraits=cmd_build_file_portraits_impl,
        cmd_build_class_portraits=cmd_build_class_portraits_impl,
        cmd_build_method_portraits=cmd_build_method_portraits_impl,
        cmd_build_constant_portraits=cmd_build_constant_portraits_impl,
        cmd_build_js_semantic_profile=cmd_build_js_semantic_profile_impl,
        cmd_build_restore_script_plan=cmd_build_restore_script_plan_impl,
        cmd_build_feedback=cmd_build_feedback_impl,
        cmd_analyze_obfuscation=cmd_analyze_obfuscation_impl,
        cmd_build_library_match=cmd_build_library_match_impl,
        cmd_extract_chains=cmd_extract_chains,
        cmd_build_evidence=cmd_build_evidence,
        cmd_bootstrap_source_rules=cmd_bootstrap_source_rules_impl,
        cmd_decompile_bundle_structure=cmd_decompile_bundle_structure_impl,
        cmd_extract_source_modules=cmd_extract_source_modules_impl,
        cmd_build_source_graph=cmd_build_source_graph_impl,
        cmd_build_reconstructed_project=cmd_build_reconstructed_project_impl,
        cmd_build_source_project=cmd_build_source_project_impl,
        cmd_restore_v1=cmd_restore_v1,
        cmd_apply_scope_renames=_cmd_apply_scope_renames,
        cmd_verify=cmd_verify_impl,
        cmd_verify_source_project=cmd_verify_source_project_impl,
        cmd_diagnose_pipeline=cmd_diagnose_pipeline_impl,
        cmd_finalize=cmd_finalize,
        cmd_runtime_evidence_stub=cmd_runtime_evidence_stub_impl,
        cmd_collect_runtime_evidence=cmd_collect_runtime_evidence_impl,
        cmd_ingest_runtime_evidence=cmd_ingest_runtime_evidence,
        cmd_all=cmd_all,
    )
    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
