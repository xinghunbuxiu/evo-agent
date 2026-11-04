"""
Evo Core - AI 学习引擎

通用学习能力，跨领域复用：
- 经验记录与检索
- 策略进化
- 技能生成与执行
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from .capability_types import infer_capability_type, legacy_domains_for_capability_type
from .verification import verify_verification_evidence


TASK_TYPE_ALIASES = {
    "analysis": "analyze",
    "analyze": "analyze",
    "reconstruction": "reconstruct",
    "reconstruct": "reconstruct",
}


def normalize_task_type(task_type: str) -> str:
    """统一任务类型命名，避免 experience 与 runtime 调度不一致。"""
    return TASK_TYPE_ALIASES.get(task_type, task_type)


@dataclass
class Experience:
    """经验记录"""
    id: str
    domain: str  # 领域：js/android/pc/dev
    task_type: str
    input_summary: str
    output_summary: str
    quality_score: float
    capability_type: str = "general_dev"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "capability_type": infer_capability_type(
                capability_type=self.capability_type,
                domain=self.domain,
            ),
            "task_type": normalize_task_type(self.task_type),
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "quality_score": self.quality_score,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class ExperienceStore:
    """Tenant-scoped experience store with a durable remote-sync outbox."""

    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = Path(workspace)
        self.tenant_id = str(tenant_id or "default")
        if self.tenant_id in {".", ".."} or "/" in self.tenant_id or chr(92) in self.tenant_id:
            raise ValueError("invalid tenant_id")
        self.tenant_root = self.workspace / ".tenants" / self.tenant_id
        self.exp_dir = self.tenant_root / "experiences"
        self.outbox_pending_dir = self.tenant_root / "experience_outbox" / "pending"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_pending_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def save(self, exp: Experience) -> None:
        """Persist locally and enqueue an immutable, retryable remote-sync event.

        The synchronous save path never performs network I/O. The outbox entry
        is fsynced before the local projection is updated, so a process restart
        can resume remote archival without depending on an in-memory task.
        """
        exp.task_type = normalize_task_type(exp.task_type)
        exp.capability_type = infer_capability_type(
            capability_type=getattr(exp, "capability_type", None),
            domain=exp.domain,
        )
        domain = str(exp.domain or "").strip()
        experience_id = str(exp.id or "").strip()
        if (
            not domain or domain in {".", ".."} or "/" in domain or chr(92) in domain
            or not experience_id or experience_id in {".", ".."}
            or "/" in experience_id or chr(92) in experience_id
        ):
            raise ValueError("experience domain and id must be safe path segments")

        payload = json.dumps(exp.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
        payload_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        artifact_id = f"{self.tenant_id}:{domain}/{experience_id}:{payload_digest}"
        outbox_record = {
            "schema_version": 1,
            "tenant_id": self.tenant_id,
            "domain": domain,
            "experience_id": experience_id,
            "artifact_id": artifact_id,
            "sha256": payload_digest,
            "relative_path": f"{domain}/{experience_id}-{payload_digest[:16]}.json",
            "content": payload,
        }
        outbox_name = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest() + ".json"
        self._atomic_write_text(
            self.outbox_pending_dir / outbox_name,
            json.dumps(outbox_record, indent=2, ensure_ascii=False, sort_keys=True),
        )

        domain_dir = self.exp_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        exp_file = domain_dir / f"{experience_id}.json"
        self._atomic_write_text(exp_file, payload)
    
    def load_by_domain(self, domain: str, limit: int = 100) -> List[Experience]:
        """按领域加载经验"""
        domain_dir = self.exp_dir / domain
        if not domain_dir.is_dir():
            return []
        
        experiences = []
        for f in sorted(domain_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    data["task_type"] = normalize_task_type(data.get("task_type", ""))
                    data["capability_type"] = infer_capability_type(
                        capability_type=data.get("capability_type"),
                        domain=data.get("domain"),
                    )
                    experiences.append(Experience(**data))
                    if len(experiences) >= limit:
                        break
            except:
                pass
        return experiences

    def load_by_task(self, domain: str, task_type: str, limit: int = 100) -> List[Experience]:
        """按领域和任务类型加载经验。"""
        normalized_task_type = normalize_task_type(task_type)
        return [
            exp for exp in self.load_by_domain(domain, limit=limit * 2)
            if normalize_task_type(exp.task_type) == normalized_task_type
        ][:limit]

    def load_by_capability_type(self, capability_type: str, limit: int = 100) -> List[Experience]:
        """按能力类型加载经验，兼容历史 domain 存储目录。"""
        experiences: List[Experience] = []
        seen_ids: set[str] = set()
        for domain in legacy_domains_for_capability_type(capability_type):
            for exp in self.load_by_domain(domain, limit=limit):
                if exp.id in seen_ids:
                    continue
                seen_ids.add(exp.id)
                experiences.append(exp)
                if len(experiences) >= limit:
                    return experiences
        return experiences[:limit]


@dataclass
class Strategy:
    """经过验证、可复用的执行策略。"""
    id: str
    name: str
    domain: str
    description: str
    applicable_when: List[str]
    steps: List[Dict[str, Any]]
    success_rate: float = 0.0
    usage_count: int = 0
    feedback_task_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "applicable_when": self.applicable_when,
            "steps": self.steps,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "feedback_task_ids": list(self.feedback_task_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Strategy":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            domain=str(data["domain"]),
            description=str(data.get("description", "")),
            applicable_when=[str(item) for item in data.get("applicable_when", [])],
            steps=[item for item in data.get("steps", []) if isinstance(item, dict)],
            success_rate=float(data.get("success_rate", 0.0)),
            usage_count=int(data.get("usage_count", 0)),
            feedback_task_ids=[str(item) for item in data.get("feedback_task_ids", []) if str(item).strip()],
        )


class StrategyEngine:
    """持久化策略库；仅将带有验证证据的候选策略提升为可复用策略。"""

    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = Path(workspace)
        self.tenant_id = str(tenant_id or "default")
        self.strategy_file = self.workspace / ".tenants" / self.tenant_id / "strategies.json"
        self.strategies: List[Strategy] = []
        self._load_strategies()

    def _load_strategies(self) -> None:
        self.strategies = []
        if not self.strategy_file.is_file():
            return
        with self.strategy_file.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError("Strategy store must contain a JSON list")
        self.strategies = [
            Strategy.from_dict(item)
            for item in payload
            if isinstance(item, dict) and item.get("id")
        ]

    def _save_strategies(self) -> None:
        self.strategy_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.strategy_file.with_suffix(".json.tmp")
        temp_file.write_text(
            json.dumps([item.to_dict() for item in self.strategies], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_file.replace(self.strategy_file)

    def find_strategy(self, domain: str, context: Dict[str, Any]) -> Optional[Strategy]:
        context_text = json.dumps(context, ensure_ascii=False, sort_keys=True, default=str)
        for strategy in self.strategies:
            if strategy.domain == domain and all(
                condition in context_text for condition in strategy.applicable_when
            ):
                return strategy
        return None

    @contextmanager
    def _strategy_store_lock(self):
        """Serialize strategy read-modify-write across threads and processes."""
        self.strategy_file.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.strategy_file.with_suffix(self.strategy_file.suffix + ".lock")
        with lock_path.open("a+b") as lock_handle:
            if lock_handle.tell() == 0:
                lock_handle.write(b"0")
                lock_handle.flush()
            lock_handle.seek(0)
            try:
                import fcntl
            except ImportError:  # pragma: no cover - exercised on Windows
                import msvcrt
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def evolve_strategy(self, exp: Experience) -> Optional[Strategy]:
        """Apply feedback under a process-wide lock to prevent lost updates."""
        with self._strategy_store_lock():
            # Reload under the lock: this instance may hold a stale snapshot.
            self._load_strategies()
            return self._evolve_strategy_locked(exp)

    def _evolve_strategy_locked(self, exp: Experience) -> Optional[Strategy]:
        """Update usage evidence or promote an explicitly validated strategy proposal.

        Experience metadata contract:
        - strategy_id + execution_success + independent verification evidence:
          update an existing strategy's observed outcome.
        - strategy_proposal + validation_passed=True + independent verification
          evidence: register a new verified strategy.
        Merely storing an experience or assigning a high quality_score never promotes a strategy.
        """
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        changed = False
        strategy_id = str(metadata.get("strategy_id") or "").strip()
        verification = metadata.get("verification_evidence")
        task_id = str(metadata.get("task_id") or "").strip()
        checks = verification.get("checks") if isinstance(verification, dict) else None
        verification_status = (
            str(verification.get("status") or "").strip()
            if isinstance(verification, dict) else ""
        )
        verification_is_independent = (
            isinstance(verification, dict)
            and verification.get("source") == "mission_independent_verifier"
            and str(verification.get("task_id") or "").strip() == task_id
            and bool(str(verification.get("execution_event_id") or "").strip())
            and bool(str(verification.get("verifier_id") or "").strip())
            and bool(str(verification.get("verifier_version") or "").strip())
            and verification_status in {"passed", "failed"}
            and isinstance(checks, list)
            and bool(checks)
            and all(
                isinstance(check, dict)
                and bool(str(check.get("check_id") or "").strip())
                and isinstance(check.get("passed"), bool)
                for check in checks
            )
            and (
                (verification_status == "passed" and all(check["passed"] for check in checks))
                or (verification_status == "failed" and any(not check["passed"] for check in checks))
            )
        )
        if (
            strategy_id
            and isinstance(metadata.get("execution_success"), bool)
            and metadata.get("execution_success") is (verification_status == "passed")
            and verification_is_independent
            and verify_verification_evidence(self.workspace, self.tenant_id, verification)
        ):
            strategy = next((item for item in self.strategies if item.id == strategy_id), None)
            # Mission feedback must be tied to independently verified evidence and
            # deduplicated in the persisted strategy record, not only an action flag.
            if strategy is not None and task_id and task_id not in strategy.feedback_task_ids:
                previous_successes = strategy.success_rate * strategy.usage_count
                strategy.usage_count += 1
                strategy.success_rate = (
                    previous_successes + (1.0 if metadata["execution_success"] else 0.0)
                ) / strategy.usage_count
                strategy.feedback_task_ids.append(task_id)
                changed = True

        proposal = metadata.get("strategy_proposal")
        validation_evidence = metadata.get("validation_evidence")
        task_id = str(metadata.get("task_id") or "").strip()
        evidence_task_id = (
            str(validation_evidence.get("task_id") or "").strip()
            if isinstance(validation_evidence, dict) else ""
        )
        checks = validation_evidence.get("checks") if isinstance(validation_evidence, dict) else None
        evidence_is_task_bound = (
            bool(task_id)
            and evidence_task_id == task_id
            and isinstance(validation_evidence, dict)
            and validation_evidence.get("source") == "mission_independent_verifier"
            and bool(str(validation_evidence.get("execution_event_id") or "").strip())
            and bool(str(validation_evidence.get("verifier_id") or "").strip())
            and bool(str(validation_evidence.get("verifier_version") or "").strip())
            and validation_evidence.get("status") == "passed"
            and isinstance(checks, list)
            and bool(checks)
            and all(
                isinstance(check, dict)
                and bool(str(check.get("check_id") or "").strip())
                and check.get("passed") is True
                for check in checks
            )
        )
        # A boolean or worker-authored check list is not enough to promote a
        # reusable strategy. Require verifier identity/version and execution-event
        # linkage as well as non-empty passing checks bound to the same task ID.
        if (
            metadata.get("validation_passed") is True
            and evidence_is_task_bound
            and verify_verification_evidence(self.workspace, self.tenant_id, validation_evidence)
            and isinstance(proposal, dict)
        ):
            proposal_id = str(proposal.get("id") or "").strip()
            name = str(proposal.get("name") or "").strip()
            steps = proposal.get("steps")
            if proposal_id and name and isinstance(steps, list) and steps and all(
                isinstance(step, dict) for step in steps
            ):
                strategy = next((item for item in self.strategies if item.id == proposal_id), None)
                candidate = Strategy(
                    id=proposal_id,
                    name=name,
                    domain=str(proposal.get("domain") or exp.domain),
                    description=str(proposal.get("description") or exp.output_summary),
                    applicable_when=[
                        str(item) for item in proposal.get("applicable_when", [])
                        if str(item).strip()
                    ],
                    steps=steps,
                    success_rate=1.0,
                    usage_count=1,
                )
                if strategy is None:
                    self.strategies.append(candidate)
                    strategy = candidate
                else:
                    strategy.name = candidate.name
                    strategy.domain = candidate.domain
                    strategy.description = candidate.description
                    strategy.applicable_when = candidate.applicable_when
                    strategy.steps = candidate.steps
                    strategy.success_rate = candidate.success_rate
                    strategy.usage_count = max(strategy.usage_count, 1)
                changed = True

        if not changed:
            # A rejected, unsigned, tampered, or duplicate feedback event must not
            # look like a successful update to the caller.
            return None
        self._save_strategies()
        return next(
            (item for item in self.strategies if item.id == strategy_id),
            next(
                (
                    item for item in self.strategies
                    if isinstance(proposal, dict) and item.id == str(proposal.get("id") or "")
                ),
                None,
            ),
        )


__all__ = [
    "Experience",
    "ExperienceStore",
    "Strategy",
    "StrategyEngine",
    "normalize_task_type",
]
