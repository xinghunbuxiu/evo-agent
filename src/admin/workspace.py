"""Shared Admin workspace resolution.

The repository root contains application code; EVO_ADMIN_WORKSPACE selects the
existing business-data workspace. An explicitly configured but invalid path is
an error rather than a silent fallback that could write data into the repository.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def resolve_admin_workspace(repo_root: Optional[Path] = None) -> Path:
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    configured = str(os.getenv("EVO_ADMIN_WORKSPACE") or "").strip()
    if not configured:
        return repository.expanduser().resolve()

    workspace = Path(configured).expanduser()
    if not workspace.exists() or not workspace.is_dir():
        raise ValueError(
            "EVO_ADMIN_WORKSPACE must point to an existing directory: "
            f"{workspace}"
        )
    return workspace.resolve()
