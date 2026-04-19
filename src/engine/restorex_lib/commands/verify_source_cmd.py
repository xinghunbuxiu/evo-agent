from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from restorex_lib.config_rules import load_json_if_exists
from restorex_lib.fs_utils import read_text, write_json, write_text
from restorex_lib.run_context import run_paths


def _count_forbidden_tokens(root: Path, patterns: list[str]) -> int:
    hits = 0
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in {".ts", ".vue", ".js"}:
            continue
        if "restored/bundle" in str(file_path).replace("\\", "/"):
            continue
        try:
            text = read_text(file_path)
        except Exception:
            continue
        for token in patterns:
            hits += text.count(token)
    return hits


def _run_build(project_root: Path) -> tuple[bool, str]:
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return False, "npm_not_found"
    install_proc = subprocess.run(
        [npm_bin, "install", "--silent"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if install_proc.returncode != 0:
        return False, f"npm_install_failed: {install_proc.stderr[-500:]}"
    build_proc = subprocess.run(
        [npm_bin, "run", "build"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if build_proc.returncode != 0:
        return False, f"npm_build_failed: {build_proc.stderr[-500:] or build_proc.stdout[-500:]}"
    return True, build_proc.stdout[-500:]


def _load_source_contracts(workspace: Path, run_id: str) -> dict[str, Any]:
    rules = load_json_if_exists(workspace / "cache" / "project" / "source_reconstruction_rules.json")
    if not rules and run_id:
        rules = load_json_if_exists(
            workspace / "output" / run_id / "analysis" / "source_reconstruction" / "source_reconstruction_rules.generated.json"
        )
    return dict(rules.get("source_project_contracts", {}))


def cmd_verify_source_project(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    contracts = _load_source_contracts(workspace, run_id)
    project_root = paths.base / "reconstructed_project_source"
    report_path = paths.reports / "verify_source_report.json"
    checks: list[dict[str, Any]] = []
    issues: list[str] = []

    if not project_root.is_dir():
        issues.append("reconstructed_project_source missing")
        write_json(report_path, {"run_id": run_id, "ok": False, "checks": [], "issues": issues})
        write_text(paths.reports / "verify_source_report.md", "# Verify Source Project\n\n- ok: `False`\n\n- reconstructed_project_source missing\n")
        return

    main_ts = project_root / "src" / "main.ts"
    app_vue = project_root / "src" / "App.vue"
    views_dir = project_root / "src" / "views"
    components_dir = project_root / "src" / "components"
    services_dir = project_root / "src" / "services"
    meta_report = project_root / "src" / "meta" / "reconstruction_report.json"

    main_text = read_text(main_ts) if main_ts.is_file() else ""
    source_entry_ok = "restored/bundle/assets/main-" not in main_text and "createApp" in main_text
    checks.append({"name": "source_entry_not_bundle_driven", "ok": source_entry_ok})
    if not source_entry_ok:
        issues.append("src/main.ts still appears bundle-driven")

    project_exists_ok = all(path.exists() for path in (main_ts, app_vue, views_dir, components_dir, services_dir, meta_report))
    checks.append({"name": "source_project_exists", "ok": project_exists_ok})
    if not project_exists_ok:
        issues.append("source project core files/dirs missing")

    service_files = sorted(p.name for p in services_dir.glob("*.ts")) if services_dir.is_dir() else []
    required_service_keys = [str(x).strip() for x in contracts.get("required_service_keys", []) if str(x).strip()]
    required_services = {f"{key.lower()}.ts" for key in required_service_keys}
    service_contract_ok = required_services.issubset(set(service_files))
    checks.append(
        {
            "name": "source_service_extraction_contract",
            "ok": service_contract_ok,
            "count": len(service_files),
            "services": service_files,
        }
    )
    if not service_contract_ok:
        issues.append("required generated service facade files missing")

    component_files = sorted(p.name for p in components_dir.glob("*.vue")) if components_dir.is_dir() else []
    required_component_ids = [str(x).strip() for x in contracts.get("required_component_ids", []) if str(x).strip()]
    required_components = {f"{component_id}.vue" for component_id in required_component_ids}
    component_contract_ok = required_components.issubset(set(component_files))
    checks.append(
        {
            "name": "source_component_adoption_contract",
            "ok": component_contract_ok,
            "count": len(component_files),
            "components": component_files,
        }
    )
    if not component_contract_ok:
        issues.append("required dialog source components missing")

    forbidden_hits = _count_forbidden_tokens(project_root / "src", ["__vite__mapDeps", "_plugin-vue_export-helper"])
    shell_reduction_ok = forbidden_hits == 0
    checks.append({"name": "bundle_runtime_shell_reduction_contract", "ok": shell_reduction_ok, "count": forbidden_hits})
    if not shell_reduction_ok:
        issues.append(f"forbidden bundle shell tokens remain: {forbidden_hits}")

    main_partitions = 0
    for path in [services_dir, components_dir, views_dir, project_root / "src" / "composables", project_root / "src" / "stores"]:
        if path.is_dir():
            main_partitions += len(list(path.glob("*")))
    partition_ok = main_partitions >= int(contracts.get("min_partition_count", 1))
    checks.append({"name": "main_partition_contract", "ok": partition_ok, "count": main_partitions})
    if not partition_ok:
        issues.append("source project partition count too low")

    build_ok, build_detail = _run_build(project_root)
    checks.append({"name": "source_build_contract", "ok": build_ok, "detail": build_detail})
    if not build_ok:
        issues.append(build_detail)

    runtime_ok = build_ok and source_entry_ok and component_contract_ok and service_contract_ok
    checks.append({"name": "source_runtime_contract", "ok": runtime_ok})
    if not runtime_ok:
        issues.append("source runtime contract failed")

    graph = {}
    if meta_report.is_file():
        try:
            graph = json.loads(read_text(meta_report))
        except Exception:
            graph = {}
    module_graph = graph.get("module_graph", {}) if isinstance(graph, dict) else {}
    module_count = len(module_graph.get("nodes", [])) if isinstance(module_graph.get("nodes", []), list) else 0
    adoption_rate = 1.0 if module_count == 0 else round((len(component_files) + len(service_files) + 3) / module_count, 4)

    ok = not issues
    report = {
        "run_id": run_id,
        "ok": ok,
        "checks": checks,
        "issues": issues,
        "source_project_ok": ok,
        "source_build_ok": build_ok,
        "source_runtime_ok": runtime_ok,
        "source_bundle_shell_remaining": forbidden_hits,
        "source_module_adoption_rate": adoption_rate,
        "source_entry_mode": "source_modules" if source_entry_ok else "bundle_like",
    }
    write_json(report_path, report)

    md = [
        "# Verify Source Project",
        "",
        f"- run_id: `{run_id}`",
        f"- ok: `{ok}`",
        f"- source_build_ok: `{build_ok}`",
        f"- source_runtime_ok: `{runtime_ok}`",
        "",
        "## Checks",
    ]
    for check in checks:
        md.append(f"- `{check['name']}` -> `{check['ok']}`")
    if issues:
        md.extend(["", "## Issues"])
        for issue in issues:
            md.append(f"- {issue}")
    write_text(paths.reports / "verify_source_report.md", "\n".join(md))
