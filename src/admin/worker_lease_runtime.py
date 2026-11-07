"""Process-local heartbeat supervision for Mission-owned worker task leases.

Lease tokens stay in this module's thread closure: they are never added to task
payloads, mission actions, or logs. Queue state is authoritative; missing task
records are treated conservatively and keep the lease alive.
"""
from __future__ import annotations

import threading
from typing import Iterable


_TERMINAL_TASK_STATES = {"success", "completed", "failed", "cancelled"}


def start_worker_task_lease_heartbeat(
    *,
    organization_registry,
    task_queue,
    worker_id: str,
    claim_id: str,
    lease_token: str,
    task_ids: Iterable[str],
    lease_seconds: int = 300,
    heartbeat_interval_seconds: float = 60.0,
) -> threading.Thread:
    """Renew a claim while any attached queue task remains non-terminal.

    The daemon exits only after every task is observable and terminal. If a task
    record is temporarily missing, it keeps renewing rather than releasing a
    worker whose execution state is unknown.
    """
    normalized_task_ids = tuple(dict.fromkeys(
        str(task_id or "").strip() for task_id in task_ids if str(task_id or "").strip()
    ))
    if not normalized_task_ids:
        raise ValueError("At least one task_id is required")
    if not str(lease_token or "").strip():
        raise ValueError("lease_token is required")
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be positive")

    def supervise() -> None:
        while True:
            all_terminal = True
            for task_id in normalized_task_ids:
                try:
                    task = task_queue.get_task(task_id) if hasattr(task_queue, "get_task") else None
                except Exception:
                    # A transient queue read/JSON/disk error is an unknown state,
                    # not proof that work has finished. Keep the lease alive and
                    # let the next heartbeat retry the authoritative lookup.
                    all_terminal = False
                    break
                if task is None:
                    all_terminal = False
                    break
                status = getattr(getattr(task, "status", None), "value", getattr(task, "status", ""))
                if str(status or "").strip().lower() not in _TERMINAL_TASK_STATES:
                    all_terminal = False
                    break
            if all_terminal:
                return
            try:
                organization_registry.renew_worker_task_lease(
                    worker_id=worker_id,
                    task_id=claim_id,
                    lease_token=lease_token,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                # Do not release or mint a replacement token here. Mission's
                # durable reconciliation remains responsible for terminal release.
                return
            threading.Event().wait(heartbeat_interval_seconds)

    thread = threading.Thread(
        target=supervise,
        name=f"worker-lease-{worker_id}-{claim_id}",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = ["start_worker_task_lease_heartbeat"]
