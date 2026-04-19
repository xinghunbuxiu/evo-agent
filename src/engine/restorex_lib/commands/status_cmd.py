from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def cmd_status(workspace: Path, run_id: str, read_text: Callable[[Path], str]) -> dict[str, Any]:
    output_dir = workspace / "output"
    if not output_dir.is_dir():
        raise SystemExit("E_RUNTIME: output dir not found")

    target_run_id = run_id.strip()
    if not target_run_id:
        run_dirs = sorted([p for p in output_dir.glob("run_*") if p.is_dir()], key=lambda p: p.name)
        if not run_dirs:
            raise SystemExit("E_RUNTIME: no runs found in output")
        target_run_id = run_dirs[-1].name

    final_summary = output_dir / target_run_id / "reports" / "final_summary.json"
    if not final_summary.is_file():
        raise SystemExit(f"E_RUNTIME: final_summary missing for run_id={target_run_id}")

    obj = json.loads(read_text(final_summary))
    overview = obj.get("overview", {}) if isinstance(obj, dict) else {}
    metrics = obj.get("metrics", {}) if isinstance(obj, dict) else {}
    risk_items = obj.get("risk_items", []) if isinstance(obj, dict) else []

    return {
        "run_id": target_run_id,
        "generated_at": obj.get("generated_at", ""),
        "verify_ok": bool(overview.get("verify_ok", False)),
        "checks_failed": int(overview.get("checks_failed", 0) or 0),
        "issues_total": int(overview.get("issues_total", 0) or 0),
        "applied_renames_total": int(metrics.get("applied_renames_total", 0) or 0),
        "chains_high": int(metrics.get("chains_high", 0) or 0),
        "chains_medium": int(metrics.get("chains_medium", 0) or 0),
        "chains_low": int(metrics.get("chains_low", 0) or 0),
        "ui_flow_chains": int(metrics.get("ui_flow_chains", 0) or 0),
        "ui_flow_high": int(metrics.get("ui_flow_high", 0) or 0),
        "runtime_evidence_mode": str(metrics.get("runtime_evidence_mode", "")),
        "runtime_boosted_chains": int(metrics.get("runtime_boosted_chains", 0) or 0),
        "bundle_obfuscation_level": str(metrics.get("bundle_obfuscation_level", "unknown")),
        "obfuscation_high_files": int(metrics.get("obfuscation_high_files", 0) or 0),
        "suspicious_renames": int(metrics.get("suspicious_renames", 0) or 0),
        "business_flow_dedupe_conflict_groups": int(metrics.get("business_flow_dedupe_conflict_groups", 0) or 0),
        "business_flow_dedupe_kept": int(metrics.get("business_flow_dedupe_kept", 0) or 0),
        "business_flow_dedupe_dropped": int(metrics.get("business_flow_dedupe_dropped", 0) or 0),
        "business_flow_dedupe_scope_bridged": int(metrics.get("business_flow_dedupe_scope_bridged", 0) or 0),
        "scope_unapplied_count": int(metrics.get("scope_unapplied_count", 0) or 0),
        "scope_applied_from_dedupe_scope_only": int(metrics.get("scope_applied_from_dedupe_scope_only", 0) or 0),
        "source_project_ok": bool(metrics.get("source_project_ok", False)),
        "source_build_ok": bool(metrics.get("source_build_ok", False)),
        "source_runtime_ok": bool(metrics.get("source_runtime_ok", False)),
        "source_bundle_shell_remaining": int(metrics.get("source_bundle_shell_remaining", 0) or 0),
        "source_module_adoption_rate": float(metrics.get("source_module_adoption_rate", 0) or 0),
        "source_entry_mode": str(metrics.get("source_entry_mode", "unknown")),
        "risk_items": [str(x) for x in risk_items[:10]],
        "final_summary": str(final_summary),
    }
