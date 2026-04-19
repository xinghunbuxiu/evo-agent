from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text, write_json, write_text


def load_compare_row_by_run(run_base: Path, profile: str = "", run_id: str = "") -> dict[str, Any]:
    analysis = run_base / "analysis"
    reports = run_base / "reports"
    run_meta = run_base / "run_meta.json"
    verify = json.loads(read_text(reports / "verify_report.json"))
    symbol = json.loads(read_text(analysis / "symbol_map_seed.json"))
    rename_plan = json.loads(read_text(analysis / "rename_plan_focus.json"))
    mapping = json.loads(read_text(analysis / "mapping_index.json"))
    chain = json.loads(read_text(analysis / "chain_graph.json"))
    meta = json.loads(read_text(run_meta)) if run_meta.is_file() else {}
    actual_run_id = run_id or str(meta.get("run_id", "")) or run_base.name
    inferred_profile = profile or str(meta.get("rule_profile", "")) or "unknown"
    scope_applied = len(mapping.get("scope_applied_renames", []))
    return {
        "profile": inferred_profile,
        "run_id": actual_run_id,
        "run_meta_profile": meta.get("rule_profile", ""),
        "profile_consistent": inferred_profile == str(meta.get("rule_profile", inferred_profile)),
        "verify_ok": verify.get("ok", False),
        "symbol_total": symbol.get("count", 0),
        "rename_auto_apply": sum(1 for i in rename_plan.get("items", []) if i.get("apply")),
        "applied_renames": len(mapping.get("applied_renames", [])),
        "scope_applied_renames": scope_applied,
        "applied_renames_total": len(mapping.get("applied_renames", [])) + scope_applied,
        "suspicious_applied_renames": sum(
            1
            for i in (list(mapping.get("applied_renames", [])) + list(mapping.get("scope_applied_renames", [])))
            if len(str(i.get("from", ""))) <= 2 and int(i.get("replace_count", 0)) >= 200
        ),
        "blocked_suspicious_renames": len(mapping.get("blocked_suspicious_renames", [])),
        "chain_count": chain.get("count", 0),
        "chain_high": sum(1 for i in chain.get("items", []) if i.get("confidence") == "high"),
        "run_output": str(run_base),
    }


def cmd_compare_profiles(
    workspace: Path,
    profiles: list[str],
    *,
    load_rule_config: Callable[[Path, str], Any],
    now_run_id: Callable[[], str],
    cmd_all: Callable[..., None],
) -> Path:
    compare_id = f"compare_{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    compare_dir = workspace / "output" / "compare" / compare_id
    compare_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for profile in profiles:
        cfg = load_rule_config(workspace, profile)
        run_id = now_run_id()
        cmd_all(workspace, run_id, cfg, emit_raw_runtime=False, auto_runtime_evidence=False)
        run_base = workspace / "output" / run_id
        results.append(load_compare_row_by_run(run_base, profile, run_id))

    scored: list[dict[str, Any]] = []
    for r in results:
        score = 0
        if r.get("verify_ok"):
            score += 1000
        score += int(r.get("applied_renames", 0)) * 10
        score += int(r.get("chain_high", 0)) * 3
        score -= int(r.get("suspicious_applied_renames", 0)) * 200
        score -= int(r.get("blocked_suspicious_renames", 0)) * 10
        rr = dict(r)
        rr["score"] = score
        scored.append(rr)
    scored_sorted = sorted(scored, key=lambda x: x.get("score", -10**9), reverse=True)
    recommended = scored_sorted[0] if scored_sorted else {}

    out_json = compare_dir / "profile_compare.json"
    out_md = compare_dir / "profile_compare.md"
    payload = {
        "compare_id": compare_id,
        "created_at": dt.datetime.now().isoformat(),
        "profiles": profiles,
        "results": scored,
        "recommended_profile": recommended.get("profile", ""),
        "recommended_run_id": recommended.get("run_id", ""),
        "recommended_score": recommended.get("score", 0),
    }
    write_json(out_json, payload)

    md = [
        "# Profile Compare",
        "",
        f"- compare_id: `{compare_id}`",
        f"- profiles: `{', '.join(profiles)}`",
        "",
        "| Profile | Run ID | Profile OK | Verify | Symbol Total | Auto Apply | Applied Renames | Suspicious Applied | Blocked Suspicious | Chain Count | Chain High | Score |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in scored_sorted:
        md.append(
            f"| {r['profile']} | {r['run_id']} | {r['profile_consistent']} | {r['verify_ok']} | {r['symbol_total']} | {r['rename_auto_apply']} | {r['applied_renames']} | {r['suspicious_applied_renames']} | {r['blocked_suspicious_renames']} | {r['chain_count']} | {r['chain_high']} | {r['score']} |"
        )
    if recommended:
        md.extend(
            [
                "",
                "## Recommended",
                f"- profile: `{recommended.get('profile', '')}`",
                f"- run_id: `{recommended.get('run_id', '')}`",
                f"- score: `{recommended.get('score', 0)}`",
            ]
        )
    write_text(out_md, "\n".join(md))
    return compare_dir


def cmd_compare_existing_runs(workspace: Path, run_ids: list[str]) -> Path:
    compare_id = f"compare_existing_{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    compare_dir = workspace / "output" / "compare" / compare_id
    compare_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for run_id in run_ids:
        rid = run_id.strip()
        if not rid:
            continue
        run_base = workspace / "output" / rid
        analysis = run_base / "analysis"
        reports = run_base / "reports"
        required = [
            analysis / "symbol_map_seed.json",
            analysis / "rename_plan_focus.json",
            analysis / "mapping_index.json",
            analysis / "chain_graph.json",
            reports / "verify_report.json",
        ]
        missing = [str(p) for p in required if not p.is_file()]
        if missing:
            errors.append({"run_id": rid, "error": "missing_required_artifacts", "missing": ", ".join(missing)})
            continue
        results.append(load_compare_row_by_run(run_base, run_id=rid))

    out_json = compare_dir / "profile_compare.json"
    out_md = compare_dir / "profile_compare.md"
    payload = {
        "compare_id": compare_id,
        "created_at": dt.datetime.now().isoformat(),
        "mode": "existing_runs",
        "run_ids": run_ids,
        "result_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    write_json(out_json, payload)

    md = [
        "# Existing Runs Compare",
        "",
        f"- compare_id: `{compare_id}`",
        f"- result_count: `{len(results)}`",
        f"- error_count: `{len(errors)}`",
        "",
        "| Profile | Run ID | Profile OK | Verify | Symbol Total | Auto Apply | Applied Renames | Suspicious Applied | Blocked Suspicious | Chain Count | Chain High |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        md.append(
            f"| {r['profile']} | {r['run_id']} | {r['profile_consistent']} | {r['verify_ok']} | {r['symbol_total']} | {r['rename_auto_apply']} | {r['applied_renames']} | {r['suspicious_applied_renames']} | {r['blocked_suspicious_renames']} | {r['chain_count']} | {r['chain_high']} |"
        )
    if errors:
        md.extend(
            [
                "",
                "## Errors",
            ]
        )
        for e in errors:
            md.append(f"- run_id `{e['run_id']}`: {e['error']} ({e['missing']})")
    write_text(out_md, "\n".join(md))
    return compare_dir
