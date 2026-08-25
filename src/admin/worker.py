"""
独立任务队列 Worker（可选 scale-out）。

与 evo-admin 共用同一工作区与 `.queue/` 目录时，可分担计算型任务。
默认单节点仅运行 evo-admin 即可（其 create_app 内已启动队列）。
"""

from __future__ import annotations

import os
import signal
import sys
import time


def _resolve_workspace():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    env_workspace = str(os.getenv("EVO_ADMIN_WORKSPACE") or "").strip()
    workspace = repo
    if env_workspace:
        env_path = Path(env_workspace).expanduser()
        env_has_local_executor = (env_path / "executors" / "toutiao" / "scripts" / "cli.py").is_file()
        if env_has_local_executor or env_path.is_dir():
            workspace = env_path
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def main() -> None:
    workspace = _resolve_workspace()

    print("=" * 50)
    print("Evo Task Queue Worker")
    print("=" * 50)
    print(f"Workspace: {workspace}")
    print("Registering handlers via admin.server.create_app ...")
    print()

    # 复用 Admin 装配：注册工种 handler、启动 task_queue（不启动 uvicorn）
    from admin.server import create_app

    create_app()

    stop = False

    def _handle_stop(*_args):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    print("Worker running. Press Ctrl+C to stop.")
    while not stop:
        time.sleep(1)

    print("Shutting down worker.")
    sys.exit(0)


if __name__ == "__main__":
    main()
