"""
Evo Core - 技能系统

设计理念：
1. 技能主要存储在云端（分布式存储）
2. 本地仅做调度执行管理和临时缓存
3. 获取优先级：云端公共 > 本地项目验证 > 自动生成
4. 可信度分层：cloud(高) > verified(中) > draft(低)
5. 验证 OK 后发布到云端共享
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .storage import UnifiedDistributedStore, StorageConfig
from .config import get_distributed_config
from .capability_types import infer_capability_type


class SkillTrustLevel(Enum):
    """技能可信度层级"""
    CLOUD = "cloud"      # 云端公共技能（最高可信度）
    VERIFIED = "verified"  # 本地验证通过（中等可信度）
    DRAFT = "draft"      # 草稿/自动生成（低可信度，需验证）


@dataclass
class Skill:
    """技能定义"""
    id: str
    name: str
    domain: str  # js/android/pc/dev
    description: str
    code: str  # 可执行代码/逻辑
    capability_type: str = "general_dev"
    parameters: Dict[str, Any] = field(default_factory=dict)
    trust_level: SkillTrustLevel = SkillTrustLevel.DRAFT
    source: str = ""  # 来源：cloud/local/generated
    version: str = "1.0.0"
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "capability_type": infer_capability_type(
                capability_type=self.capability_type,
                domain=self.domain,
            ),
            "description": self.description,
            "code": self.code,
            "parameters": self.parameters,
            "trust_level": self.trust_level.value,
            "source": self.source,
            "version": self.version,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            id=data["id"],
            name=data["name"],
            domain=data["domain"],
            capability_type=infer_capability_type(
                capability_type=data.get("capability_type"),
                domain=data.get("domain"),
            ),
            description=data.get("description", ""),
            code=data.get("code", ""),
            parameters=data.get("parameters", {}),
            trust_level=SkillTrustLevel(data.get("trust_level", "draft")),
            source=data.get("source", ""),
            version=data.get("version", "1.0.0"),
            usage_count=data.get("usage_count", 0),
            success_rate=data.get("success_rate", 0.0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class SkillRegistry:
    """
    技能注册表 - 云端优先的调度中心
    
    获取优先级：
    1. 云端公共技能（最高可信度）
    2. 本地验证通过的技能
    3. 自动生成的草稿技能
    """
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        
        # 分布式存储（云端）
        dist_config = get_distributed_config(workspace)
        self.cloud_store = UnifiedDistributedStore(workspace, StorageConfig(distributed=dist_config))
        
        # 本地缓存目录（仅用于验证中和离线）
        self.local_cache = workspace / ".tenants" / tenant_id / ".skill_cache"
        self.local_verified = self.local_cache / "verified"
        self.local_drafts = self.local_cache / "drafts"
        
        for d in [self.local_cache, self.local_verified, self.local_drafts]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 技能索引缓存
        self._index_cache: Optional[Dict[str, List[str]]] = None
    
    def find_skill(
        self,
        domain: str,
        task_type: str,
        prefer_local: bool = False
    ) -> Optional[Skill]:
        """
        查找技能（按优先级）
        
        Args:
            domain: 领域 (js/android/pc/dev)
            task_type: 任务类型
            prefer_local: 是否优先使用本地验证版本
        """
        skill_id = self._generate_skill_id(domain, task_type)
        
        # 优先级 1: 本地验证通过的技能（如果 prefer_local）
        if prefer_local:
            skill = self._load_local_verified(skill_id)
            if skill:
                return skill
        
        # 优先级 2: 云端公共技能
        skill = self._load_from_cloud(domain, skill_id)
        if skill:
            return skill
        
        # 优先级 3: 本地验证通过的技能（非 prefer_local 模式）
        if not prefer_local:
            skill = self._load_local_verified(skill_id)
            if skill:
                return skill
        
        # 优先级 4: 本地草稿
        skill = self._load_local_draft(skill_id)
        if skill:
            return skill
        
        return None
    
    def register_draft(
        self,
        domain: str,
        task_type: str,
        code: str,
        description: str = "",
        parameters: Dict[str, Any] = None
    ) -> Skill:
        """
        注册草稿技能（本地验证阶段）
        
        当云端不存在所需技能时，在本地创建草稿进行验证
        """
        skill_id = self._generate_skill_id(domain, task_type)
        
        skill = Skill(
            id=skill_id,
            name=f"{domain}_{task_type}",
            domain=domain,
            capability_type=infer_capability_type(domain=domain),
            description=description or f"Draft skill for {task_type}",
            code=code,
            parameters=parameters or {},
            trust_level=SkillTrustLevel.DRAFT,
            source="local_draft",
        )
        
        # 保存到本地草稿区
        self._save_local_draft(skill)
        
        return skill
    
    def verify_skill(
        self,
        skill_id: str,
        test_results: List[Dict[str, Any]],
        min_success_rate: float = 0.8
    ) -> bool:
        """
        验证技能（提升到 verified 级别）
        
        通过测试后，技能从草稿升级为本地验证通过
        """
        # 加载草稿
        skill = self._load_local_draft(skill_id)
        if not skill:
            skill = self._load_local_verified(skill_id)
        if not skill:
            return False
        
        # 计算成功率
        if test_results:
            success_count = sum(1 for r in test_results if r.get("success", False))
            skill.success_rate = success_count / len(test_results)
        
        # 验证通过条件
        if skill.success_rate >= min_success_rate:
            skill.trust_level = SkillTrustLevel.VERIFIED
            skill.source = "local_verified"
            skill.updated_at = datetime.now().isoformat()
            
            # 移动到验证通过区
            self._save_local_verified(skill)
            self._remove_local_draft(skill_id)
            
            return True
        
        return False
    
    def publish_to_cloud(
        self,
        skill_id: str,
        require_verified: bool = True
    ) -> bool:
        """
        发布技能到云端（共享给所有用户）
        
        只有验证通过的技能才能发布到云端
        """
        # 加载本地验证通过的技能
        skill = self._load_local_verified(skill_id)
        if not skill:
            return False
        
        if require_verified and skill.trust_level != SkillTrustLevel.VERIFIED:
            return False
        
        # 升级为云端级别
        skill.trust_level = SkillTrustLevel.CLOUD
        skill.source = "cloud"
        skill.updated_at = datetime.now().isoformat()
        
        # 保存到云端
        try:
            self.cloud_store.save_knowledge(
                knowledge=skill.to_dict(),
                knowledge_type=f"skills_{skill.domain}",
                id=skill_id
            )
            
            # 本地保留副本作为缓存
            self._save_local_verified(skill)
            
            return True
        except Exception as e:
            print(f"Failed to publish skill to cloud: {e}")
            return False
    
    def list_skills(self, domain: Optional[str] = None) -> Dict[str, List[Skill]]:
        """列出所有可用技能（按来源分类）"""
        result = {
            "cloud": [],
            "local_verified": [],
            "drafts": [],
        }
        
        # 云端技能
        cloud_skills = self.cloud_store.load_knowledge("skills")
        for s in cloud_skills:
            skill = Skill.from_dict(s)
            if not domain or skill.domain == domain:
                result["cloud"].append(skill)
        
        # 本地验证通过
        for f in self.local_verified.glob("*.json"):
            try:
                with open(f) as fp:
                    skill = Skill.from_dict(json.load(fp))
                    if not domain or skill.domain == domain:
                        result["local_verified"].append(skill)
            except:
                pass
        
        # 草稿
        for f in self.local_drafts.glob("*.json"):
            try:
                with open(f) as fp:
                    skill = Skill.from_dict(json.load(fp))
                    if not domain or skill.domain == domain:
                        result["drafts"].append(skill)
            except:
                pass
        
        return result
    
    # ==================== 私有方法 ====================
    
    def _generate_skill_id(self, domain: str, task_type: str) -> str:
        """生成技能 ID"""
        content = f"{domain}:{task_type}"
        return f"skill_{domain}_{task_type}_{hashlib.md5(content.encode()).hexdigest()[:8]}"
    
    def _load_from_cloud(self, domain: str, skill_id: str) -> Optional[Skill]:
        """从云端加载技能"""
        try:
            data = self.cloud_store.domain_store.load(
                data_type=f"skills_{domain}",
                id=skill_id
            )
            if data:
                return Skill.from_dict(data)
        except:
            pass
        return None
    
    def _load_local_verified(self, skill_id: str) -> Optional[Skill]:
        """加载本地验证通过的技能"""
        skill_file = self.local_verified / f"{skill_id}.json"
        if skill_file.is_file():
            with open(skill_file) as f:
                return Skill.from_dict(json.load(f))
        return None
    
    def _save_local_verified(self, skill: Skill) -> None:
        """保存本地验证通过的技能"""
        skill_file = self.local_verified / f"{skill.id}.json"
        with open(skill_file, "w") as f:
            json.dump(skill.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _load_local_draft(self, skill_id: str) -> Optional[Skill]:
        """加载本地草稿"""
        skill_file = self.local_drafts / f"{skill_id}.json"
        if skill_file.is_file():
            with open(skill_file) as f:
                return Skill.from_dict(json.load(f))
        return None
    
    def _save_local_draft(self, skill: Skill) -> None:
        """保存本地草稿"""
        skill_file = self.local_drafts / f"{skill.id}.json"
        with open(skill_file, "w") as f:
            json.dump(skill.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _remove_local_draft(self, skill_id: str) -> None:
        """删除本地草稿"""
        skill_file = self.local_drafts / f"{skill_id}.json"
        if skill_file.is_file():
            skill_file.unlink()


class SkillExecutor:
    """
    技能执行器 - 调度管理中心
    
    职责：
    1. 从注册表获取技能
    2. 执行技能代码
    3. 记录执行结果
    4. 反馈技能效果（用于验证）
    """
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        self.registry = SkillRegistry(workspace, tenant_id)
        
        # 执行历史（用于验证）
        self.execution_log: List[Dict[str, Any]] = []
    
    def execute(
        self,
        domain: str,
        task_type: str,
        context: Dict[str, Any],
        prefer_local: bool = False
    ) -> Dict[str, Any]:
        """
        执行技能
        
        流程：
        1. 查找技能（云端 → 本地验证 → 草稿）
        2. 执行技能代码
        3. 记录执行结果
        4. 返回结果
        """
        # 1. 查找技能
        skill = self.registry.find_skill(domain, task_type, prefer_local)
        if not skill:
            return {
                "success": False,
                "error": f"No skill found for {domain}/{task_type}",
                "suggestion": "Create a draft skill using register_draft()",
            }
        
        # 2. 执行技能
        try:
            # TODO: 实现具体的技能执行逻辑
            # 这里可以是：
            # - 调用 AI 模型
            # - 执行预设代码
            # - 调用外部工具
            result = self._execute_skill_code(skill, context)
            
            # 3. 记录执行
            execution_record = {
                "skill_id": skill.id,
                "domain": domain,
                "task_type": task_type,
                "trust_level": skill.trust_level.value,
                "success": result.get("success", False),
                "timestamp": datetime.now().isoformat(),
            }
            self.execution_log.append(execution_record)
            
            # 4. 返回结果
            return {
                "success": result.get("success", False),
                "skill_id": skill.id,
                "skill_trust_level": skill.trust_level.value,
                "result": result.get("data"),
                "message": result.get("message", ""),
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "skill_id": skill.id,
            }
    
    def _execute_skill_code(self, skill: Skill, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能代码（占位实现）"""
        # TODO: 实现具体的执行逻辑
        # 可以是 Python 代码执行、AI 调用、外部命令等
        return {
            "success": True,
            "data": {"executed": skill.name, "context": context},
            "message": f"Executed skill: {skill.name}",
        }
    
    def get_execution_history(self, skill_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取执行历史（用于验证技能）"""
        if skill_id:
            return [r for r in self.execution_log if r["skill_id"] == skill_id]
        return self.execution_log
    
    def verify_and_publish(
        self,
        skill_id: str,
        min_success_rate: float = 0.8,
        auto_publish: bool = True
    ) -> Dict[str, Any]:
        """
        验证并发布技能
        
        简化流程：基于执行历史自动验证并发布
        """
        # 获取该技能的执行历史
        history = self.get_execution_history(skill_id)
        
        if len(history) < 3:
            return {
                "success": False,
                "message": f"Need at least 3 executions to verify, got {len(history)}",
            }
        
        # 验证
        verified = self.registry.verify_skill(skill_id, history, min_success_rate)
        
        if not verified:
            return {
                "success": False,
                "message": "Skill verification failed (success rate too low)",
            }
        
        # 发布
        if auto_publish:
            published = self.registry.publish_to_cloud(skill_id)
            return {
                "success": True,
                "verified": True,
                "published": published,
                "message": "Skill verified and published to cloud" if published else "Skill verified but publish failed",
            }
        
        return {
            "success": True,
            "verified": True,
            "published": False,
            "message": "Skill verified (not published)",
        }


__all__ = [
    "Skill",
    "SkillTrustLevel",
    "SkillRegistry",
    "SkillExecutor",
]
