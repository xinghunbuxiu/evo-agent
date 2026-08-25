"""
Evo Core - 进化智能平台核心

提供跨领域的通用能力：
- 分布式存储系统
- 配置管理
- AI 学习引擎
- 多租户隔离

所有领域 (JS/Android/PC/Dev) 共享核心层
"""

__version__ = "2.0.0"

from .config import (
    get_distributed_config,
    DistributedConfig,
    RepoConfig,
    ConfigLoader,
    ConfigError,
)
from .storage import (
    UnifiedDistributedStore,
    StorageConfig,
    KnowledgeContainer,
    KnowledgeContainerResolver,
    ShardedStore,
    ShardConfig,
)
from .learning import (
    Experience,
    ExperienceStore,
    Strategy,
    StrategyEngine,
)
from .skill_system import (
    Skill,
    SkillTrustLevel,
    SkillRegistry,
    SkillExecutor,
)
from .tenant import TenantManager
from .capability_types import (
    CAPABILITY_TYPE_ALIASES,
    CAPABILITY_TYPE_CATALOG,
    normalize_capability_type,
    infer_capability_type,
    capability_type_label,
    capability_type_catalog,
)
from .capabilities import (
    CapabilityDescriptor,
    TaskContext,
    TaskResult,
    CapabilityProvider,
    CapabilityRegistry,
    get_capability_registry,
)
from .decision import (
    CandidateScore,
    DecisionRecord,
    DecisionEngine,
)
from .orchestration import (
    StrategyDescriptor,
    StrategySelection,
    EvaluationResult,
    StrategyProvider,
    EvaluatorProvider,
    StrategyRegistry,
    EvaluatorRegistry,
    get_strategy_registry,
    get_evaluator_registry,
)
from .plugins import (
    PluginRegistrationResult,
    PluginLoadSummary,
    PluginLoader,
)
from .mission_planner import (
    MissionPlanner,
    MISSION_KIND_TEMPLATES,
)
from .git_provider import (
    ManagedRepo,
    GitProvider,
    GitProviderError,
    GiteeProvider,
    GitLabProvider,
    get_git_provider,
)

__all__ = [
    # 配置
    "get_distributed_config",
    "DistributedConfig", 
    "RepoConfig",
    "ConfigLoader",
    "ConfigError",
    # 存储
    "UnifiedDistributedStore",
    "StorageConfig",
    "KnowledgeContainer",
    "KnowledgeContainerResolver",
    "ShardedStore",
    "ShardConfig",
    # 学习
    "Experience",
    "ExperienceStore",
    "Strategy",
    "StrategyEngine",
    # 技能系统（云端优先）
    "Skill",
    "SkillTrustLevel",
    "SkillRegistry",
    "SkillExecutor",
    # 租户
    "TenantManager",
    "CAPABILITY_TYPE_ALIASES",
    "CAPABILITY_TYPE_CATALOG",
    "normalize_capability_type",
    "infer_capability_type",
    "capability_type_label",
    "capability_type_catalog",
    # 能力协议
    "CapabilityDescriptor",
    "TaskContext",
    "TaskResult",
    "CapabilityProvider",
    "CapabilityRegistry",
    "get_capability_registry",
    # 决策层
    "CandidateScore",
    "DecisionRecord",
    "DecisionEngine",
    # 策略/评估编排
    "StrategyDescriptor",
    "StrategySelection",
    "EvaluationResult",
    "StrategyProvider",
    "EvaluatorProvider",
    "StrategyRegistry",
    "EvaluatorRegistry",
    "get_strategy_registry",
    "get_evaluator_registry",
    # 插件
    "PluginRegistrationResult",
    "PluginLoadSummary",
    "PluginLoader",
    "MissionPlanner",
    "MISSION_KIND_TEMPLATES",
    # Git provider
    "ManagedRepo",
    "GitProvider",
    "GitProviderError",
    "GiteeProvider",
    "GitLabProvider",
    "get_git_provider",
]
