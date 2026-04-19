from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def run_main_adapter(
    args: Any,
    workspace: Path,
    *,
    get_run_id: Callable[[Path, str | None], str],
    load_rule_config: Callable[[Path, str], Any],
    handle_pre_dispatch: Callable[..., tuple[bool, int, list[str]]],
    handle_run_dispatch: Callable[..., list[str]],
    cmd_compare_profiles: Callable[[Path, list[str]], Path],
    cmd_compare_existing_runs: Callable[[Path, list[str]], Path],
    cmd_status: Callable[[Path, str], dict[str, Any]],
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
    cmd_build_reconstructed_project: Callable[..., None],
    cmd_build_source_project: Callable[..., None],
    cmd_restore_v1: Callable[..., None],
    cmd_apply_scope_renames: Callable[..., None],
    cmd_verify: Callable[..., None],
    cmd_verify_source_project: Callable[..., None],
    cmd_diagnose_pipeline: Callable[..., None],
    cmd_finalize: Callable[..., None],
    cmd_runtime_evidence_stub: Callable[..., None],
    cmd_collect_runtime_evidence: Callable[..., Path],
    cmd_ingest_runtime_evidence: Callable[..., None],
    cmd_all: Callable[..., None],
) -> tuple[int, list[str]]:
    handled, exit_code, pre_lines = handle_pre_dispatch(
        args=args,
        workspace=workspace,
        cmd_compare_profiles=cmd_compare_profiles,
        cmd_compare_existing_runs=cmd_compare_existing_runs,
        cmd_status=cmd_status,
    )
    if handled:
        return exit_code, pre_lines

    run_id = get_run_id(workspace, args.run_id or None)
    cfg = load_rule_config(workspace, args.rule_profile)
    extra_lines = handle_run_dispatch(
        args=args,
        workspace=workspace,
        run_id=run_id,
        cfg=cfg,
        cmd_init_run=cmd_init_run,
        cmd_normalize=cmd_normalize,
        cmd_infer_build_origin=cmd_infer_build_origin,
        cmd_scan_structure=cmd_scan_structure,
        cmd_build_portrait=cmd_build_portrait,
        cmd_build_file_portraits=cmd_build_file_portraits,
        cmd_build_class_portraits=cmd_build_class_portraits,
        cmd_build_method_portraits=cmd_build_method_portraits,
        cmd_build_constant_portraits=cmd_build_constant_portraits,
        cmd_build_js_semantic_profile=cmd_build_js_semantic_profile,
        cmd_build_restore_script_plan=cmd_build_restore_script_plan,
        cmd_build_feedback=cmd_build_feedback,
        cmd_analyze_obfuscation=cmd_analyze_obfuscation,
        cmd_build_library_match=cmd_build_library_match,
        cmd_extract_chains=cmd_extract_chains,
        cmd_build_evidence=cmd_build_evidence,
        cmd_bootstrap_source_rules=cmd_bootstrap_source_rules,
        cmd_decompile_bundle_structure=cmd_decompile_bundle_structure,
        cmd_extract_source_modules=cmd_extract_source_modules,
        cmd_build_source_graph=cmd_build_source_graph,
        cmd_build_reconstructed_project=cmd_build_reconstructed_project,
        cmd_build_source_project=cmd_build_source_project,
        cmd_restore_v1=cmd_restore_v1,
        cmd_apply_scope_renames=cmd_apply_scope_renames,
        cmd_verify=cmd_verify,
        cmd_verify_source_project=cmd_verify_source_project,
        cmd_diagnose_pipeline=cmd_diagnose_pipeline,
        cmd_finalize=cmd_finalize,
        cmd_runtime_evidence_stub=cmd_runtime_evidence_stub,
        cmd_collect_runtime_evidence=cmd_collect_runtime_evidence,
        cmd_ingest_runtime_evidence=cmd_ingest_runtime_evidence,
        cmd_all=cmd_all,
    )

    lines = list(extra_lines)
    lines.append(f"ok: command={args.command}")
    lines.append(f"run_id={run_id}")
    lines.append(f"output={workspace / 'output' / run_id}")
    return 0, lines
