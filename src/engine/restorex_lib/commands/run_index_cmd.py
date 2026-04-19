from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import write_json, write_text


def refresh_run_index(workspace: Path, load_json_if_exists: Callable[[Path], dict[str, Any]]) -> None:
    output_dir = workspace / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dirs = sorted([p for p in output_dir.glob("run_*") if p.is_dir()], key=lambda p: p.name, reverse=True)

    rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        run_id = run_dir.name
        run_meta = load_json_if_exists(run_dir / "run_meta.json")
        verify = load_json_if_exists(run_dir / "reports" / "verify_report.json")
        final_summary = load_json_if_exists(run_dir / "reports" / "final_summary.json")
        metrics = final_summary.get("metrics", {}) if isinstance(final_summary, dict) else {}
        overview = final_summary.get("overview", {}) if isinstance(final_summary, dict) else {}

        rows.append(
            {
                "run_id": run_id,
                "rule_profile": str(run_meta.get("rule_profile", "")),
                "verify_ok": bool(verify.get("ok", False)) if verify else bool(overview.get("verify_ok", False)),
                "checks_failed": int(overview.get("checks_failed", 0)),
                "chains": int(metrics.get("chains", 0)),
                "chains_high": int(metrics.get("chains_high", 0)),
                "applied_renames": int(metrics.get("applied_renames_total", metrics.get("applied_renames", 0))),
                "runtime_mode": str(metrics.get("runtime_evidence_mode", "")),
                "source_project_ok": bool(metrics.get("source_project_ok", False)),
                "generated_at": str(final_summary.get("generated_at", "")),
                "path": str(run_dir),
            }
        )

    index_json = {
        "updated_at": dt.datetime.now().isoformat(),
        "run_count": len(rows),
        "latest_run_id": rows[0]["run_id"] if rows else "",
        "items": rows,
    }
    write_json(output_dir / "RUN_INDEX.json", index_json)

    md = [
        "# Run Index",
        "",
        f"- updated_at: `{index_json['updated_at']}`",
        f"- run_count: `{index_json['run_count']}`",
        f"- latest_run_id: `{index_json['latest_run_id']}`",
        "",
        "| Run ID | Profile | Verify | Source | Failed Checks | Chains | High | Applied Renames | Runtime Mode | Generated At |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['run_id']} | {r['rule_profile']} | {r['verify_ok']} | {r['source_project_ok']} | {r['checks_failed']} | {r['chains']} | {r['chains_high']} | {r['applied_renames']} | {r['runtime_mode']} | {r['generated_at']} |"
        )
    write_text(output_dir / "RUN_INDEX.md", "\n".join(md))
