"""
Evo Core - AI 学习引擎

通用学习能力，跨领域复用：
- 经验记录与检索
- 策略进化
- 技能生成与执行
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from .capability_types import infer_capability_type, legacy_domains_for_capability_type


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
    """经验存储"""
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        self.exp_dir = workspace / ".tenants" / tenant_id / "experiences"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, exp: Experience) -> None:
        """保存经验"""
        exp.task_type = normalize_task_type(exp.task_type)
        exp.capability_type = infer_capability_type(
            capability_type=getattr(exp, "capability_type", None),
            domain=exp.domain,
        )
        domain_dir = self.exp_dir / exp.domain
        domain_dir.mkdir(exist_ok=True)
        
        exp_file = domain_dir / f"{exp.id}.json"
        with open(exp_file, "w") as f:
            json.dump(exp.to_dict(), f, indent=2, ensure_ascii=False)
    
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
    """策略定义"""
    id: str
    name: str
    domain: str
    description: str
    applicable_when: List[str]
    steps: List[Dict[str, Any]]
    success_rate: float = 0.0
    usage_count: int = 0
    
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
        }


class StrategyEngine:
    """策略引擎"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.strategies: List[Strategy] = []
        self._load_strategies()
    
    def _load_strategies(self) -> None:
        """加载策略"""
        # 初始为空，由 AI 生成
        pass
    
    def find_strategy(self, domain: str, context: Dict[str, Any]) -> Optional[Strategy]:
        """查找匹配策略"""
        for s in self.strategies:
            if s.domain == domain:
                # 简单匹配逻辑
                if all(cond in str(context) for cond in s.applicable_when):
                    return s
        return None
    
    def evolve_strategy(self, exp: Experience) -> None:
        """基于经验进化策略"""
        # TODO: 实现策略进化逻辑
        pass


__all__ = [
    "Experience",
    "ExperienceStore",
    "Strategy",
    "StrategyEngine",
    "normalize_task_type",
]
