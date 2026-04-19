from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def handle_pre_dispatch(
    args: Any,
    workspace: Path,
    *,
    cmd_compare_profiles: Callable[[Path, list[str]], Path],
    cmd_compare_existing_runs: Callable[[Path, list[str]], Path],
    cmd_status: Callable[[Path, str], dict[str, Any]],
) -> tuple[bool, int, list[str]]:
    if args.command == "compare-profiles":
        profiles = [x.strip() for x in args.profiles.split(",") if x.strip()]
        compare_dir = cmd_compare_profiles(workspace, profiles)
        return (True, 0, [f"ok: command={args.command}", f"compare_output={compare_dir}"])

    if args.command == "compare-runs":
        run_ids = [x.strip() for x in args.compare_run_ids.split(",") if x.strip()]
        if not run_ids:
            raise SystemExit("E_RUNTIME: --compare-run-ids is required for compare-runs")
        compare_dir = cmd_compare_existing_runs(workspace, run_ids)
        return (True, 0, [f"ok: command={args.command}", f"compare_output={compare_dir}"])

    if args.command == "status":
        payload = cmd_status(workspace, args.run_id or "")
        return (True, 0, ["ok: command=status", "status=" + json.dumps(payload, ensure_ascii=False)])

    return (False, 0, [])


def handle_run_dispatch(
    args: Any,
    workspace: Path,
    run_id: str,
    cfg: Any,
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
) -> list[str]:
    """命令执行分发层。

    约束：
    - 只做命令路由，不做策略判断。
    - 统一返回 extra_lines，保持 CLI 输出协议稳定。
    """
    extra_lines: list[str] = []
    if args.command == "init-run":
        cmd_init_run(workspace, run_id, cfg, emit_raw_runtime=args.emit_raw_runtime)
    elif args.command == "normalize":
        cmd_normalize(workspace, run_id)
    elif args.command == "infer-build-origin":
        cmd_infer_build_origin(workspace, run_id)
    elif args.command == "scan-structure":
        cmd_scan_structure(workspace, run_id)
    elif args.command == "build-portrait":
        cmd_build_portrait(workspace, run_id)
    elif args.command == "build-file-portraits":
        cmd_build_file_portraits(workspace, run_id)
    elif args.command == "build-class-portraits":
        cmd_build_class_portraits(workspace, run_id)
    elif args.command == "build-method-portraits":
        cmd_build_method_portraits(workspace, run_id)
    elif args.command == "build-constant-portraits":
        cmd_build_constant_portraits(workspace, run_id)
    elif args.command == "build-js-semantic-profile":
        cmd_build_js_semantic_profile(workspace, run_id)
    elif args.command == "build-script-plan":
        cmd_build_restore_script_plan(workspace, run_id)
    elif args.command == "build-feedback":
        cmd_build_feedback(workspace, run_id)
    elif args.command == "analyze-obfuscation":
        cmd_analyze_obfuscation(workspace, run_id)
    elif args.command == "build-library-match":
        cmd_build_library_match(workspace, run_id)
    elif args.command == "extract-chains":
        cmd_extract_chains(workspace, run_id, cfg)
    elif args.command == "build-evidence":
        cmd_build_evidence(workspace, run_id, cfg)
    elif args.command == "bootstrap-source-rules":
        cmd_bootstrap_source_rules(workspace, run_id)
    elif args.command == "decompile-bundle-structure":
        cmd_decompile_bundle_structure(workspace, run_id)
    elif args.command == "extract-source-modules":
        cmd_extract_source_modules(workspace, run_id)
    elif args.command == "build-source-graph":
        cmd_build_source_graph(workspace, run_id)
    elif args.command == "build-reconstructed-project":
        cmd_build_reconstructed_project(workspace, run_id)
    elif args.command == "build-source-project":
        cmd_build_source_project(workspace, run_id)
    elif args.command == "restore-v1":
        cmd_restore_v1(workspace, run_id, cfg, emit_raw_runtime=args.emit_raw_runtime)
    elif args.command == "apply-scope-renames":
        cmd_apply_scope_renames(workspace, run_id, cfg)
    elif args.command == "verify":
        cmd_verify(workspace, run_id, cfg)
    elif args.command == "verify-source-project":
        cmd_verify_source_project(workspace, run_id)
    elif args.command == "diagnose-pipeline":
        cmd_diagnose_pipeline(workspace, run_id)
    elif args.command == "finalize":
        cmd_finalize(workspace, run_id, cfg)
    elif args.command == "runtime-evidence-stub":
        cmd_runtime_evidence_stub(workspace, run_id, force=True)
    elif args.command == "collect-runtime-evidence":
        out = cmd_collect_runtime_evidence(
            workspace,
            run_id,
            log_glob=args.log_glob,
            limit=args.collect_limit,
            prefer_direct=bool(args.runtime_prefer_direct),
        )
        extra_lines.append(f"runtime_evidence={out}")
    elif args.command == "ingest-runtime-evidence":
        if not args.runtime_evidence:
            raise SystemExit("E_RUNTIME: --runtime-evidence is required for ingest-runtime-evidence")
        cmd_ingest_runtime_evidence(workspace, run_id, args.runtime_evidence)
    elif args.command == "all":
        cmd_all(
            workspace,
            run_id,
            cfg,
            emit_raw_runtime=args.emit_raw_runtime,
            auto_runtime_evidence=args.auto_runtime_evidence,
            runtime_log_glob=args.log_glob,
            runtime_collect_limit=args.collect_limit,
            runtime_prefer_direct=bool(args.runtime_prefer_direct),
        )
    return extra_lines
