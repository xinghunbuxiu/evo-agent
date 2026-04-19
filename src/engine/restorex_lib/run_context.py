from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunPaths:
    base: Path
    baseline: Path
    analysis: Path
    restore_v1: Path
    reports: Path
    # 持久化画像缓存（跨 run 复用，不随 output 清空）
    cache: Path
    portraits: Path
    fingerprints_cache: Path


def now_run_id() -> str:
    return dt.datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")


def run_paths(workspace: Path, run_id: str) -> RunPaths:
    base = workspace / "output" / run_id
    baseline = base / "baseline"
    analysis = base / "analysis"
    restore_v1 = base / "restore_v1"
    reports = base / "reports"
    # cache 目录：持久化，不在 output 下，不随清空丢失
    cache = workspace / "cache"
    portraits = cache / "portraits"
    fingerprints_cache = cache / "fingerprints"
    for p in (baseline, analysis, restore_v1, reports, portraits, fingerprints_cache):
        p.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        base=base,
        baseline=baseline,
        analysis=analysis,
        restore_v1=restore_v1,
        reports=reports,
        cache=cache,
        portraits=portraits,
        fingerprints_cache=fingerprints_cache,
    )


def get_run_id(workspace: Path, run_id: str | None) -> str:
    if run_id:
        return run_id
    return now_run_id()


def input_paths(workspace: Path) -> tuple[Path, Path]:
    input_root = workspace / "input"
    manifest = input_root / "manifest.json"
    raw_bundle = input_root / "raw_bundle"
    if not manifest.is_file():
        raise SystemExit(f"E_RUNTIME: manifest not found: {manifest}")
    if not raw_bundle.is_dir():
        raise SystemExit(f"E_RUNTIME: raw_bundle not found: {raw_bundle}")
    return manifest, raw_bundle


def ensure_baseline_exists(paths: RunPaths) -> tuple[Path, Path]:
    raw_snapshot = paths.baseline / "raw_snapshot"
    manifest_snapshot = paths.baseline / "input_manifest.json"
    if not raw_snapshot.is_dir() or not manifest_snapshot.is_file():
        raise SystemExit("E_RUNTIME: baseline missing, run init-run first")
    return manifest_snapshot, raw_snapshot
