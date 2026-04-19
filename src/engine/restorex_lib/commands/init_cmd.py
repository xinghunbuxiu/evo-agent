from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import collect_files, rel, sha256_file, write_json
from restorex_lib.run_context import input_paths, run_paths


def confidence_rank(label: str) -> int:
    rank = {"low": 1, "medium": 2, "high": 3}
    return rank.get(str(label).lower(), 0)


def cmd_init_run(
    workspace: Path,
    run_id: str,
    cfg: Any,
    supported_exts: set[str],
    emit_raw_runtime: bool = False,
) -> None:
    manifest_path, raw_bundle = input_paths(workspace)
    paths = run_paths(workspace, run_id)
    raw_snapshot = paths.baseline / "raw_snapshot"
    manifest_snapshot = paths.baseline / "input_manifest.json"
    if raw_snapshot.exists():
        shutil.rmtree(raw_snapshot)
    shutil.copytree(raw_bundle, raw_snapshot)
    shutil.copy2(manifest_path, manifest_snapshot)

    file_entries: list[dict[str, Any]] = []
    for f in collect_files(raw_snapshot):
        file_entries.append(
            {
                "path": rel(f, raw_snapshot),
                "ext": f.suffix.lower(),
                "size": f.stat().st_size,
                "sha256": sha256_file(f),
            }
        )

    run_meta = {
        "run_id": run_id,
        "created_at": dt.datetime.now().isoformat(),
        "workspace": str(workspace),
        "input_manifest": str(manifest_path),
        "input_raw_bundle": str(raw_bundle),
        "baseline_raw_snapshot": str(raw_snapshot),
        "rule_profile": getattr(cfg, "profile_name", ""),
        "supported_exts": sorted(supported_exts),
        "file_count": len(file_entries),
        "emit_raw_runtime": emit_raw_runtime,
    }
    write_json(paths.base / "run_meta.json", run_meta)
    write_json(paths.baseline / "raw_file_index.json", {"run_id": run_id, "count": len(file_entries), "files": file_entries})
