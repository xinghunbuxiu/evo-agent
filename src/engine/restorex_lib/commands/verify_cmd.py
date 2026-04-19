from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import read_text, sha256_file, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def cmd_verify(workspace: Path, run_id: str, cfg: Any) -> None:
    paths = run_paths(workspace, run_id)
    manifest_snapshot, raw_snapshot = ensure_baseline_exists(paths)
    readable = paths.restore_v1 / "readable"
    raw_runtime = paths.restore_v1 / "raw_runtime"
    run_meta_path = paths.base / "run_meta.json"
    run_meta_obj = json.loads(read_text(run_meta_path)) if run_meta_path.is_file() else {}
    require_raw_runtime = bool(run_meta_obj.get("emit_raw_runtime", False))
    chain_path = paths.analysis / "chain_graph.json"
    origin_path = paths.analysis / "build_origin_report.json"
    mapping_path = paths.analysis / "mapping_index.json"
    ui_flow_path = paths.analysis / "ui_flow_chains.json"
    third_party_path = paths.analysis / "third_party_fingerprint.json"
    js_semantic_path = paths.analysis / "js_semantic_profile.json"
    script_plan_path = paths.analysis / "restore_script_plan.json"
    portrait_core_path = paths.analysis / "portrait_core.json"
    generated_actions_path = paths.analysis / "generated_restore_actions.json"
    action_feedback_path = paths.analysis / "action_feedback.json"
    portrait_calibration_path = paths.analysis / "portrait_calibration.json"

    issues: list[str] = []
    checks: list[dict[str, Any]] = []

    manifest = json.loads(read_text(manifest_snapshot))
    missing = 0
    bad_hash = 0
    for item in manifest.get("files", []):
        p = raw_snapshot / item["path"]
        if not p.is_file():
            missing += 1
            continue
        if sha256_file(p) != item["sha256"]:
            bad_hash += 1
    checks.append({"name": "baseline_hash_consistency", "ok": missing == 0 and bad_hash == 0, "missing": missing, "bad_hash": bad_hash})
    if missing or bad_hash:
        issues.append(f"baseline mismatch: missing={missing}, bad_hash={bad_hash}")

    raw_index = raw_runtime / "pages" / "index.html"
    readable_index = readable / "pages" / "index.html"
    reconstructed_project = paths.base / "reconstructed_project"
    reconstructed_main = reconstructed_project / "src" / "main.ts"
    reconstructed_pkg = reconstructed_project / "package.json"
    reconstructed_vite = reconstructed_project / "vite.config.ts"
    reconstructed_evidence = reconstructed_project / "src" / "meta" / "recovered_evidence.json"
    reconstructed_legacy_dir = reconstructed_project / "public" / "legacy"
    checks.append({"name": "entry_exists_raw_runtime", "ok": (raw_index.is_file() if require_raw_runtime else True), "required": require_raw_runtime})
    checks.append({"name": "entry_exists_readable", "ok": readable_index.is_file()})
    checks.append({"name": "reconstructed_project_exists", "ok": reconstructed_main.is_file()})
    if require_raw_runtime and not raw_index.is_file():
        issues.append("raw_runtime missing pages/index.html")
    if not readable_index.is_file():
        issues.append("readable missing pages/index.html")
    if not reconstructed_main.is_file():
        issues.append("reconstructed_project missing src/main.ts")

    executable_contract_ok = False
    if reconstructed_pkg.is_file():
        try:
            pkg_obj = json.loads(read_text(reconstructed_pkg))
        except Exception:
            pkg_obj = {}
        scripts_obj = pkg_obj.get("scripts", {}) if isinstance(pkg_obj.get("scripts", {}), dict) else {}
        has_dev = isinstance(scripts_obj.get("dev"), str) and bool(str(scripts_obj.get("dev", "")).strip())
        has_build = isinstance(scripts_obj.get("build"), str) and bool(str(scripts_obj.get("build", "")).strip())
        executable_contract_ok = reconstructed_main.is_file() and reconstructed_vite.is_file() and has_dev and has_build
    checks.append(
        {
            "name": "reconstructed_executable_contract",
            "ok": executable_contract_ok,
            "required_files": [
                "reconstructed_project/src/main.ts",
                "reconstructed_project/vite.config.ts",
                "reconstructed_project/package.json(scripts.dev/build)",
            ],
        }
    )
    if not executable_contract_ok:
        issues.append("reconstructed_project executable contract failed (main.ts/vite/package scripts)")
    evidence_contract_ok = reconstructed_evidence.is_file()
    checks.append({"name": "reconstructed_evidence_contract", "ok": evidence_contract_ok})
    if not evidence_contract_ok:
        issues.append("reconstructed_project missing src/meta/recovered_evidence.json")
    no_legacy_copy_ok = not reconstructed_legacy_dir.exists()
    checks.append({"name": "reconstructed_no_public_legacy_copy", "ok": no_legacy_copy_ok})
    if not no_legacy_copy_ok:
        issues.append("reconstructed_project should not contain public/legacy runtime copy")

    placeholder_markers = [
        "来源文件:",
        "运行入口:",
        "默认展示保真运行面 UI",
        "runtime-frame",
        "Reconstructed Project (Vue-like)",
        "还原进度看板",
        "模块运行视图",
    ]
    placeholder_hits = 0
    reconstructed_src = reconstructed_project / "src"
    if reconstructed_src.is_dir():
        for vue_file in reconstructed_src.rglob("*.vue"):
            try:
                text = read_text(vue_file)
            except Exception:
                continue
            hit = any(mark in text for mark in placeholder_markers)
            # 兜底：识别明显“证据展示壳”结构（旧模板 class）
            if not hit and re.search(r"<iframe[^>]+runtime-frame", text):
                hit = True
            if hit:
                placeholder_hits += 1
    placeholder_ok = placeholder_hits == 0
    checks.append({"name": "reconstructed_no_placeholder_shell", "ok": placeholder_ok, "count": placeholder_hits})
    if not placeholder_ok:
        issues.append(f"reconstructed_project contains placeholder shell vue files: {placeholder_hits}")

    chain_obj = json.loads(read_text(chain_path)) if chain_path.is_file() else {"count": 0, "items": []}
    chain_ok = chain_obj.get("count", 0) > 0 and all(
        all(k in i for k in ("trigger", "state_ops", "bridge_calls", "ui_refs", "restore_priority", "entity", "ui_flow_score", "ui_entry_hits"))
        and isinstance(i.get("entity"), dict)
        and all(x in i.get("entity", {}) for x in ("type", "name", "line"))
        for i in chain_obj.get("items", [])
    )
    checks.append({"name": "chain_graph_contract", "ok": chain_ok, "count": chain_obj.get("count", 0)})
    if not chain_ok:
        issues.append("chain_graph contract failed")
    ui_flow_obj = json.loads(read_text(ui_flow_path)) if ui_flow_path.is_file() else {"count": 0, "items": []}
    ui_flow_ok = ui_flow_obj.get("count", 0) > 0 and all(
        all(k in i for k in ("chain_id", "file", "line", "trigger", "bridge_calls", "ui_refs", "ui_flow_score", "ui_entry_hits", "entity"))
        for i in ui_flow_obj.get("items", [])
    )
    checks.append({"name": "ui_flow_chains_contract", "ok": ui_flow_ok, "count": ui_flow_obj.get("count", 0)})
    if not ui_flow_ok:
        issues.append("ui_flow_chains contract failed")

    third_party_obj = json.loads(read_text(third_party_path)) if third_party_path.is_file() else {"count": 0, "items": []}
    third_party_ok = third_party_path.is_file() and int(third_party_obj.get("count", 0)) > 0 and isinstance(
        third_party_obj.get("stats", {}), dict
    )
    checks.append({"name": "third_party_fingerprint_contract", "ok": third_party_ok, "count": int(third_party_obj.get("count", 0))})
    if not third_party_ok:
        issues.append("third_party_fingerprint missing or empty")

    js_semantic_obj = json.loads(read_text(js_semantic_path)) if js_semantic_path.is_file() else {"summary": {}, "count": 0, "items": []}
    js_semantic_summary = js_semantic_obj.get("summary", {}) if isinstance(js_semantic_obj.get("summary", {}), dict) else {}
    js_semantic_ok = (
        js_semantic_path.is_file()
        and int(js_semantic_obj.get("count", 0)) > 0
        and isinstance(js_semantic_obj.get("items", []), list)
        and all(k in js_semantic_summary for k in ("files", "logger_like_classes", "registry_like_objects"))
    )
    checks.append(
        {
            "name": "js_semantic_profile_contract",
            "ok": js_semantic_ok,
            "count": int(js_semantic_obj.get("count", 0)),
            "logger_like_classes": int(js_semantic_summary.get("logger_like_classes", 0)),
            "registry_like_objects": int(js_semantic_summary.get("registry_like_objects", 0)),
        }
    )
    if not js_semantic_ok:
        issues.append("js_semantic_profile missing or invalid")

    script_plan_obj = json.loads(read_text(script_plan_path)) if script_plan_path.is_file() else {"stages": []}
    script_plan_ok = script_plan_path.is_file() and isinstance(script_plan_obj.get("stages", []), list) and len(
        script_plan_obj.get("stages", [])
    ) >= 3
    checks.append(
        {
            "name": "restore_script_plan_contract",
            "ok": script_plan_ok,
            "stage_count": len(script_plan_obj.get("stages", [])) if isinstance(script_plan_obj.get("stages", []), list) else 0,
        }
    )
    if not script_plan_ok:
        issues.append("restore_script_plan missing or invalid")
    portrait_core_obj = json.loads(read_text(portrait_core_path)) if portrait_core_path.is_file() else {}
    generated_actions_obj = json.loads(read_text(generated_actions_path)) if generated_actions_path.is_file() else {}
    split_ok = (
        portrait_core_path.is_file()
        and generated_actions_path.is_file()
        and isinstance(portrait_core_obj.get("capabilities", []), list)
        and isinstance(generated_actions_obj.get("items", []), list)
    )
    checks.append(
        {
            "name": "core_generated_split_contract",
            "ok": split_ok,
            "capability_count": len(portrait_core_obj.get("capabilities", []))
            if isinstance(portrait_core_obj.get("capabilities", []), list)
            else 0,
            "generated_actions": len(generated_actions_obj.get("items", []))
            if isinstance(generated_actions_obj.get("items", []), list)
            else 0,
        }
    )
    if not split_ok:
        issues.append("portrait_core/generated_restore_actions contract failed")
    feedback_obj = json.loads(read_text(action_feedback_path)) if action_feedback_path.is_file() else {}
    calibration_obj = json.loads(read_text(portrait_calibration_path)) if portrait_calibration_path.is_file() else {}
    feedback_required = action_feedback_path.is_file() or portrait_calibration_path.is_file()
    feedback_ok = (
        (not feedback_required)
        or (
            action_feedback_path.is_file()
            and portrait_calibration_path.is_file()
            and isinstance(feedback_obj.get("tag_feedback", []), list)
            and isinstance(calibration_obj.get("tag_weights", {}), dict)
        )
    )
    checks.append(
        {
            "name": "feedback_calibration_contract",
            "ok": feedback_ok,
            "required": feedback_required,
            "tag_feedback_count": len(feedback_obj.get("tag_feedback", []))
            if isinstance(feedback_obj.get("tag_feedback", []), list)
            else 0,
            "tag_weight_count": len(calibration_obj.get("tag_weights", {}))
            if isinstance(calibration_obj.get("tag_weights", {}), dict)
            else 0,
        }
    )
    if not feedback_ok:
        issues.append("action_feedback/portrait_calibration contract failed")

    origin_obj = json.loads(read_text(origin_path)) if origin_path.is_file() else {"count": 0}
    trace_ok = origin_obj.get("count", 0) > 0 and all(
        all(k in i for k in ("file", "origin_label", "confidence", "signals", "counter_evidence", "status"))
        for i in origin_obj.get("items", [])
    )
    checks.append({"name": "origin_traceability", "ok": trace_ok, "count": origin_obj.get("count", 0)})
    if not trace_ok:
        issues.append("build_origin_report missing fields")

    file_portrait_path = paths.portraits / "file_portraits.json"
    file_portrait_obj = json.loads(read_text(file_portrait_path)) if file_portrait_path.is_file() else {"count": 0, "items": []}
    file_portrait_ok = file_portrait_obj.get("count", 0) > 0 and all(
        all(
            k in i
            for k in (
                "file",
                "ext",
                "origin_label",
                "framework_hints",
                "build_hints",
                "ui_hints",
                "domain_hints",
                "restore_priority",
            )
        )
        for i in file_portrait_obj.get("items", [])
    )
    checks.append({"name": "file_portraits_contract", "ok": file_portrait_ok, "count": file_portrait_obj.get("count", 0)})
    if not file_portrait_ok:
        issues.append("file_portraits missing fields or empty")

    class_portrait_path = paths.portraits / "class_portraits.json"
    method_portrait_path = paths.portraits / "method_portraits.json"
    constant_portrait_path = paths.portraits / "constant_portraits.json"
    class_portrait_obj = json.loads(read_text(class_portrait_path)) if class_portrait_path.is_file() else {"count": 0, "items": []}
    class_portrait_ok = class_portrait_obj.get("count", 0) > 0 and all(
        all(k in i for k in ("file", "entity_type", "entity_name", "line", "origin_label", "restore_priority"))
        for i in class_portrait_obj.get("items", [])
    )
    checks.append({"name": "class_portraits_contract", "ok": class_portrait_ok, "count": class_portrait_obj.get("count", 0)})
    if not class_portrait_ok:
        issues.append("class_portraits missing fields or empty")

    method_portrait_obj = (
        json.loads(read_text(method_portrait_path)) if method_portrait_path.is_file() else {"count": 0, "items": []}
    )
    method_portrait_ok = method_portrait_obj.get("count", 0) >= 0 and all(
        all(
            k in i
            for k in (
                "file",
                "entity_type",
                "method_kind",
                "method_name",
                "line",
                "origin_label",
                "restore_priority",
                "params",
                "flow_tags",
                "inferred_param_candidates",
                "confidence",
            )
        )
        for i in method_portrait_obj.get("items", [])
    )
    method_param_rule_ok = all(
        all(
            isinstance(cand, dict) and "source_rule" in cand
            for cand in (i.get("inferred_param_candidates", []) if isinstance(i.get("inferred_param_candidates", []), list) else [])
        )
        for i in method_portrait_obj.get("items", [])
    )
    method_portrait_ok = bool(method_portrait_ok and method_param_rule_ok)
    checks.append({"name": "method_portraits_contract", "ok": method_portrait_ok, "count": method_portrait_obj.get("count", 0)})
    if not method_portrait_ok:
        issues.append("method_portraits missing fields")

    constant_portrait_obj = (
        json.loads(read_text(constant_portrait_path)) if constant_portrait_path.is_file() else {"count": 0, "items": []}
    )
    constant_portrait_ok = constant_portrait_obj.get("count", 0) > 0 and all(
        all(
            k in i
            for k in (
                "file",
                "entity_type",
                "constant_kind",
                "entity_name",
                "line",
                "origin_label",
                "restore_priority",
                "confidence",
                "signal_tags",
                "allow_auto_restore",
                "semantic_bucket",
            )
        )
        for i in constant_portrait_obj.get("items", [])
    )
    checks.append({"name": "constant_portraits_contract", "ok": constant_portrait_ok, "count": constant_portrait_obj.get("count", 0)})
    if not constant_portrait_ok:
        issues.append("constant_portraits missing fields or empty")

    queue_path = paths.analysis / "restore_priority_queue.json"
    queue_obj = json.loads(read_text(queue_path)) if queue_path.is_file() else {"count": 0, "items": []}
    queue_ok = queue_obj.get("count", 0) > 0 and all(
        all(
            k in i
            for k in (
                "file",
                "entity_name",
                "entity_type",
                "restore_priority",
                "chain_count",
                "high_conf_count",
                "bridge_calls",
                "ui_chain_count",
                "ui_flow_score",
                "score",
            )
        )
        for i in queue_obj.get("items", [])
    )
    checks.append({"name": "restore_priority_queue_contract", "ok": queue_ok, "count": queue_obj.get("count", 0)})
    if not queue_ok:
        issues.append("restore_priority_queue missing fields or empty")

    batch_files = [paths.analysis / "entity_restore_batch_1.json", paths.analysis / "entity_restore_batch_2.json", paths.analysis / "entity_restore_batch_3.json"]
    for idx, bp in enumerate(batch_files, start=1):
        bobj = json.loads(read_text(bp)) if bp.is_file() else {"count": 0, "items": []}
        bok = bp.is_file() and all(
            all(k in i for k in ("file", "symbol", "candidate", "confidence", "source", "reason")) for i in bobj.get("items", [])
        )
        checks.append({"name": f"entity_restore_batch_{idx}_contract", "ok": bok, "count": bobj.get("count", 0)})
        if not bok:
            issues.append(f"entity_restore_batch_{idx} missing fields")

    mapping_obj = json.loads(read_text(mapping_path)) if mapping_path.is_file() else {}
    forbidden_violations = 0
    all_applied_renames = list(mapping_obj.get("applied_renames", [])) + list(mapping_obj.get("scope_applied_renames", []))
    for ren in all_applied_renames:
        if any(tok in ren.get("to", "") for tok in cfg.forbidden_rename_tokens):
            forbidden_violations += 1
    checks.append({"name": "forbidden_rename_violation", "ok": forbidden_violations == 0, "count": forbidden_violations})
    if forbidden_violations:
        issues.append(f"forbidden rename violation: {forbidden_violations}")

    suspicious_logger_param_hits = 0
    if readable.is_dir():
        for js_file in readable.rglob("*.js"):
            try:
                text = read_text(js_file)
            except Exception:
                continue
            # 捕获明显语义污染：logger 参数被误命名为 safeDialog/safeMessage。
            suspicious_logger_param_hits += len(
                re.findall(
                    r"\b(?:debug|info|warn|error)\s*\(\s*(?:safeDialog|safeMessage)\b",
                    text,
                )
            )
            suspicious_logger_param_hits += len(
                re.findall(
                    r"\[(?:DEBUG|INFO|WARN|ERROR)\]\[\$\{(?:safeDialog|safeMessage)\}\]",
                    text,
                )
            )
    checks.append(
        {
            "name": "semantic_collision_logger_params",
            "ok": suspicious_logger_param_hits == 0,
            "count": suspicious_logger_param_hits,
        }
    )
    if suspicious_logger_param_hits:
        issues.append(f"semantic collision in logger-like params: {suspicious_logger_param_hits}")

    symbol_path = paths.analysis / "symbol_map_seed.json"
    rename_plan_path = paths.analysis / "rename_plan_focus.json"
    symbol_obj = json.loads(read_text(symbol_path)) if symbol_path.is_file() else {"items": []}
    rename_obj = json.loads(read_text(rename_plan_path)) if rename_plan_path.is_file() else {"items": []}
    by_pair = {
        (str(i.get("file", "")), str(i.get("symbol", "")), str(i.get("candidate", ""))): bool(i.get("apply"))
        for i in symbol_obj.get("items", [])
    }
    inconsistent = 0
    for item in rename_obj.get("items", []):
        key = (str(item.get("file", "")), str(item.get("symbol", "")), str(item.get("candidate", "")))
        if key in by_pair and bool(item.get("apply")) != by_pair[key]:
            inconsistent += 1
    checks.append({"name": "rename_plan_consistency", "ok": inconsistent == 0, "count": inconsistent})
    if inconsistent:
        issues.append(f"rename plan inconsistent with symbol map: {inconsistent}")

    obf_path = paths.analysis / "obfuscation_profile.json"
    if obf_path.is_file():
        obf_obj = json.loads(read_text(obf_path))
    else:
        obf_obj = {"summary": {}, "items": []}
    obf_summary = obf_obj.get("summary", {}) if isinstance(obf_obj.get("summary", {}), dict) else {}
    obf_ok = (
        obf_path.is_file()
        and isinstance(obf_obj.get("items", []), list)
        and len(obf_obj.get("items", [])) > 0
        and isinstance(obf_summary.get("bundle_obfuscation_level", ""), str)
        and bool(obf_summary.get("recommended_strategy", []))
    )
    checks.append(
        {
            "name": "obfuscation_profile_contract",
            "ok": obf_ok,
            "bundle_level": obf_summary.get("bundle_obfuscation_level", "unknown"),
            "js_file_count": obf_summary.get("js_file_count", 0),
        }
    )
    if not obf_ok:
        issues.append("obfuscation_profile missing or invalid")

    ok = not issues
    report = {"run_id": run_id, "ok": ok, "checks": checks, "issues": issues}
    write_json(paths.reports / "verify_report.json", report)
    md = [
        "# Verify Report",
        "",
        f"- run_id: `{run_id}`",
        f"- ok: `{ok}`",
        "",
        "## Checks",
    ]
    for c in checks:
        md.append(f"- `{c['name']}` -> `{c['ok']}`")
    if issues:
        md.append("")
        md.append("## Issues")
        for i in issues:
            md.append(f"- {i}")
    write_text(paths.reports / "verify_report.md", "\n".join(md))
