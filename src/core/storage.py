"""
Evo Core - 分布式存储系统

统一管理所有领域的分布式数据：
- 经验 (experiences) - 跨领域共享
- 知识 (knowledge) - 技能、策略、模式
- 指纹 (fingerprints) - 各领域专用
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Dict
from dataclasses import dataclass

from .config import DistributedConfig, RepoConfig, get_distributed_config


@dataclass
class StorageConfig:
    """存储配置"""
    distributed: DistributedConfig = None
    local_cache_dir: str = ".cache/distributed"
    archive_after_days: int = 30
    compress_after_days: int = 90
    max_file_size_mb: float = 10.0
    
    def __post_init__(self):
        if self.distributed is None:
            self.distributed = get_distributed_config()


@dataclass
class KnowledgeContainer:
    """统一描述一个知识容器。

    这里不绑定具体 provider 实现，只表达：
    - 这层容器存什么
    - 在哪儿
    - 当前是否可写/可用
    """

    container_id: str
    name: str
    purpose: str
    backend: str
    scope: str
    writable: bool
    status: str
    location: str
    provider: Optional[str] = None
    branch: Optional[str] = None
    repo_full_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.container_id,
            "name": self.name,
            "purpose": self.purpose,
            "backend": self.backend,
            "scope": self.scope,
            "writable": self.writable,
            "status": self.status,
            "location": self.location,
            "provider": self.provider,
            "branch": self.branch,
            "repo_full_name": self.repo_full_name,
            "metadata": self.metadata or {},
        }


class KnowledgeContainerResolver:
    """把本地目录、平台共享层、Git 仓库统一成容器视角。"""

    PURPOSE_TO_CONFIG_REPO = {
        "skills": "knowledge",
        "knowledge": "knowledge",
        "experiences": "experiences",
        "registry": "registry",
        "strategies": "knowledge",
        "reports": "knowledge",
        "config": "registry",
    }

    def __init__(self, workspace: Path, config: Optional[DistributedConfig] = None):
        self.workspace = workspace
        self.config = config or get_distributed_config(workspace)
        self.git_provider_name = self._detect_git_provider_name()

    def build_tenant_containers(
        self,
        tenant_id: str,
        *,
        git_knowledge: Optional[dict[str, Any]] = None,
        knowledge_policy: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        containers: list[KnowledgeContainer] = []

        tenant_root = self.workspace / ".tenants" / tenant_id
        containers.extend(
            [
                self._local_container(tenant_root / "skills", "skills", "本地技能层"),
                self._local_container(tenant_root / "experiences", "experiences", "本地经验层"),
                self._local_container(tenant_root / "strategies", "strategies", "本地策略层"),
            ]
        )

        platform_root = self.workspace / ".platform_shared"
        containers.append(
            KnowledgeContainer(
                container_id="platform_shared",
                name="平台共享层",
                purpose="platform_shared",
                backend="filesystem",
                scope="platform",
                writable=bool((knowledge_policy or {}).get("allow_platform_promotion", False)),
                status="ready" if platform_root.exists() else "standby",
                location=str(platform_root),
                metadata={
                    "share_mode": (knowledge_policy or {}).get("share_mode"),
                    "review_required": (knowledge_policy or {}).get("review_required"),
                },
            )
        )

        containers.extend(self._git_containers(git_knowledge))
        containers.extend(self._fallback_config_containers(git_knowledge))
        return [container.to_dict() for container in containers]

    def resolve_repo(self, purpose: str, git_knowledge: Optional[dict[str, Any]] = None) -> tuple[str, str]:
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        repo = repos.get(purpose)
        if isinstance(repo, dict) and repo.get("full_name"):
            return str(repo["full_name"]), str(repo.get("url") or "")

        config_repo_name = self.PURPOSE_TO_CONFIG_REPO.get(purpose, "knowledge")
        repo_config = getattr(self.config, config_repo_name)
        if isinstance(repo_config, RepoConfig):
            return repo_config.full_name, repo_config.url
        return "", ""

    def _local_container(self, path: Path, purpose: str, name: str) -> KnowledgeContainer:
        return KnowledgeContainer(
            container_id=f"local:{purpose}",
            name=name,
            purpose=purpose,
            backend="filesystem",
            scope="tenant",
            writable=True,
            status="ready" if path.exists() else "pending",
            location=str(path),
        )

    def _git_containers(self, git_knowledge: Optional[dict[str, Any]]) -> list[KnowledgeContainer]:
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        provider = git_knowledge.get("provider") if isinstance(git_knowledge, dict) else None
        containers: list[KnowledgeContainer] = []

        for repo_key, repo in repos.items():
            if not isinstance(repo, dict):
                continue
            full_name = str(repo.get("full_name") or "")
            url = str(repo.get("url") or "")
            branch = str(repo.get("branch") or "master")
            containers.append(
                KnowledgeContainer(
                    container_id=f"git:{repo_key}",
                    name=f"Git {repo_key}",
                    purpose=repo_key,
                    backend="git_repo",
                    scope="tenant",
                    writable=True,
                    status="ready" if full_name else "pending",
                    location=url or full_name,
                    provider=str(provider or "git"),
                    branch=branch,
                    repo_full_name=full_name or None,
                    metadata={
                        "private": bool(repo.get("private", True)),
                        "bootstrapped_at": git_knowledge.get("bootstrapped_at") if isinstance(git_knowledge, dict) else None,
                    },
                )
            )
        return containers

    def _fallback_config_containers(self, git_knowledge: Optional[dict[str, Any]]) -> list[KnowledgeContainer]:
        existing_purposes = set()
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        for key in repos.keys():
            existing_purposes.add(str(key))

        fallback_specs = [
            ("skills", "默认知识仓", self.config.knowledge),
            ("experiences", "默认经验仓", self.config.experiences),
            ("registry", "默认注册仓", self.config.registry),
        ]
        containers: list[KnowledgeContainer] = []
        for purpose, name, repo in fallback_specs:
            if purpose in existing_purposes:
                continue
            containers.append(
                KnowledgeContainer(
                    container_id=f"config:{purpose}",
                    name=name,
                    purpose=purpose,
                    backend="git_repo",
                    scope="platform",
                    writable=False,
                    status="standby",
                    location=repo.url,
                    provider=self.git_provider_name,
                    branch=repo.branch,
                    repo_full_name=repo.full_name,
                    metadata={"source": "distributed_config"},
                )
            )
        return containers

    def _detect_git_provider_name(self) -> str:
        api_base = str(getattr(self.config, "api_base", "") or "").lower()
        knowledge_base = str(getattr(self.config.knowledge, "base_url", "") or "").lower()
        if "gitee.com" in api_base or "gitee.com" in knowledge_base:
            return "gitee"
        if "gitlab" in api_base or "gitlab" in knowledge_base:
            return "gitlab"
        if "github.com" in api_base or "github.com" in knowledge_base:
            return "github"
        return str(getattr(self.config, "platform", "") or "git")


class UnifiedDistributedStore:
    """统一分布式存储"""
    
    def __init__(self, workspace: Path, config: Optional[StorageConfig] = None):
        self.workspace = workspace
        self.config = config or StorageConfig()
        self.dist_config = self.config.distributed
        
        self.cache_dir = workspace / self.config.local_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.sync_index_path = self.cache_dir / "sync_index.json"
        self.sync_index = self._load_sync_index()
    
    def _load_sync_index(self) -> dict:
        """加载同步索引"""
        if self.sync_index_path.is_file():
            with open(self.sync_index_path) as f:
                return json.load(f)
        return {
            "version": "2.0",
            "last_sync": None,
            "repos": {}
        }
    
    def _save_sync_index(self) -> None:
        """保存同步索引"""
        with open(self.sync_index_path, "w") as f:
            json.dump(self.sync_index, f, indent=2)
    
    # ==================== 经验存储 ====================
    
    def save_experience(self, experience: dict, domain: str = "general") -> None:
        """保存经验（按领域分类）"""
        exp_file = self.cache_dir / "experiences" / f"{domain}.jsonl"
        exp_file.parent.mkdir(parents=True, exist_ok=True)
        
        record = {
            **experience,
            "_domain": domain,
            "_stored_at": json.dumps({})
        }
        
        with open(exp_file, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def load_experiences(self, domain: Optional[str] = None, limit: int = 100) -> list[dict]:
        """加载经验"""
        if domain:
            exp_file = self.cache_dir / "experiences" / f"{domain}.jsonl"
            if not exp_file.is_file():
                return []
            files = [exp_file]
        else:
            exp_dir = self.cache_dir / "experiences"
            if not exp_dir.is_dir():
                return []
            files = list(exp_dir.glob("*.jsonl"))
        
        experiences = []
        for exp_file in files:
            with open(exp_file) as f:
                for line in f:
                    if len(experiences) >= limit:
                        break
                    try:
                        experiences.append(json.loads(line))
                    except:
                        pass
        return experiences
    
    # ==================== 知识存储 ====================
    
    def save_knowledge(self, knowledge: dict, knowledge_type: str, id: str) -> None:
        """保存知识（技能/策略/模式）"""
        kb_dir = self.cache_dir / "knowledge" / knowledge_type
        kb_dir.mkdir(parents=True, exist_ok=True)
        
        kb_file = kb_dir / f"{id}.json"
        with open(kb_file, "w") as f:
            json.dump(knowledge, f, indent=2, ensure_ascii=False)
    
    def load_knowledge(self, knowledge_type: str) -> list[dict]:
        """加载知识"""
        kb_dir = self.cache_dir / "knowledge" / knowledge_type
        if not kb_dir.is_dir():
            return []
        
        items = []
        for f in kb_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    items.append(json.load(fp))
            except:
                pass
        return items
    
    # ==================== 领域专用存储 ====================
    
    def get_domain_store(self, domain: str, repo_name: str) -> "DomainStore":
        """获取领域专用存储"""
        return DomainStore(self.workspace, domain, repo_name, self)


class DomainStore:
    """领域专用存储"""
    
    def __init__(self, workspace: Path, domain: str, repo_name: str, parent: UnifiedDistributedStore):
        self.workspace = workspace
        self.domain = domain
        self.repo_name = repo_name
        self.parent = parent
        self.domain_dir = parent.cache_dir / "domains" / domain
        self.domain_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, data: dict, data_type: str, id: str) -> None:
        """保存领域数据"""
        type_dir = self.domain_dir / data_type
        type_dir.mkdir(parents=True, exist_ok=True)
        
        data_file = type_dir / f"{id}.json"
        with open(data_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load(self, data_type: str, id: Optional[str] = None) -> Any:
        """加载领域数据"""
        type_dir = self.domain_dir / data_type
        if not type_dir.is_dir():
            return [] if id is None else None
        
        if id:
            data_file = type_dir / f"{id}.json"
            if data_file.is_file():
                with open(data_file) as f:
                    return json.load(f)
            return None
        else:
            items = []
            for f in type_dir.glob("*.json"):
                try:
                    with open(f) as fp:
                        items.append(json.load(fp))
                except:
                    pass
            return items


# 分片存储（大数据量）
class ShardConfig:
    """分片配置"""
    def __init__(self, shard_count: int = 4, key_func=None):
        self.shard_count = shard_count
        self.key_func = key_func or (lambda x: hash(x) % shard_count)


class ShardedStore:
    """分片存储"""
    
    def __init__(self, base_path: Path, config: ShardConfig):
        self.base_path = base_path
        self.config = config
        self.shards = [base_path / f"shard_{i}" for i in range(config.shard_count)]
        for shard in self.shards:
            shard.mkdir(parents=True, exist_ok=True)
    
    def _get_shard(self, key: str) -> Path:
        """获取分片路径"""
        shard_idx = self.config.key_func(key)
        return self.shards[shard_idx]
    
    def save(self, key: str, data: dict) -> None:
        """保存数据"""
        shard = self._get_shard(key)
        file_path = shard / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def load(self, key: str) -> Optional[dict]:
        """加载数据"""
        shard = self._get_shard(key)
        file_path = shard / f"{key}.json"
        if file_path.is_file():
            with open(file_path) as f:
                return json.load(f)
        return None


__all__ = [
    "UnifiedDistributedStore",
    "StorageConfig",
    "DomainStore",
    "ShardedStore",
    "ShardConfig",
]
