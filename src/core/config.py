"""
Evo Core - 配置管理系统

配置完全外部化，代码中无硬编码默认值。

配置文件搜索路径（按优先级）：
1. $EVO_CONFIG_PATH 环境变量
2. ./.config/evo.json
3. ~/.evo/config.json
4. /etc/evo/config.json

无配置文件时会抛出错误，提示复制 example 文件。
"""

from __future__ import annotations

import os
import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any


class ConfigError(Exception):
    """配置错误"""
    pass


@dataclass
class RepoConfig:
    """仓库配置
    
    支持多平台：Gitee / GitHub / GitLab / 自建
    """
    owner: str
    repo: str
    branch: str = "main"
    description: str = ""
    base_url: str = ""  # 从配置读取，如 https://gitee.com
    
    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"
    
    @property
    def url(self) -> str:
        return f"{self.base_url}/{self.full_name}"


@dataclass
class DistributedConfig:
    """分布式配置"""
    version: str
    platform: str
    api_base: str  # 平台 API 基础路径，如 https://gitee.com/api/v5
    registry: RepoConfig
    experiences: RepoConfig
    knowledge: RepoConfig
    storage: Dict[str, Any]
    learning: Dict[str, Any]
    domains: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DistributedConfig":
        """从字典创建
        
        注意：配置文件必须包含所有必需字段，无硬编码默认值。
        """
        repos = data.get("repos", {})
        
        # 检查必需字段
        required_repos = ["registry", "experiences", "knowledge"]
        for repo in required_repos:
            if repo not in repos:
                raise ConfigError(f"配置缺少必需仓库: repos.{repo}")
        
        # 检查 API 基础路径
        api_base = data.get("api_base") or data.get("gitee_api_base")
        if not api_base:
            raise ConfigError("配置缺少 api_base（如 https://gitee.com/api/v5）")
        
        return cls(
            version=data.get("version", "1.0"),
            platform=data.get("platform", "evo"),
            api_base=api_base,
            registry=RepoConfig(**repos["registry"]),
            experiences=RepoConfig(**repos["experiences"]),
            knowledge=RepoConfig(**repos["knowledge"]),
            storage=data.get("storage", {}),
            learning=data.get("learning", {}),
            domains=data.get("domains", {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version": self.version,
            "platform": self.platform,
            "api_base": self.api_base,
            "repos": {
                "registry": asdict(self.registry),
                "experiences": asdict(self.experiences),
                "knowledge": asdict(self.knowledge),
            },
            "storage": self.storage,
            "learning": self.learning,
            "domains": self.domains
        }
    
    def get_domain_config(self, domain: str) -> Dict[str, Any]:
        """获取领域配置"""
        return self.domains.get(domain, {})


class ConfigLoader:
    """配置加载器"""
    
    CONFIG_PATHS = [
        os.getenv("EVO_CONFIG_PATH"),
        Path.cwd() / ".config" / "evo.json",
        Path.home() / ".evo" / "config.json",
        Path("/etc/evo/config.json"),
    ]
    
    @classmethod
    def find_config_file(cls) -> Optional[Path]:
        """查找配置文件"""
        for path in cls.CONFIG_PATHS:
            if path and Path(path).is_file():
                return Path(path)
        return None
    
    @classmethod
    def load_config_file(cls, path: Optional[Path] = None) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = path or cls.find_config_file()
        if config_path and config_path.is_file():
            with open(config_path) as f:
                return json.load(f)
        return {}
    
    @classmethod
    def apply_env_overrides(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """应用环境变量覆盖"""
        if os.getenv("EVO_GITEE_API"):
            config["gitee_api_base"] = os.getenv("EVO_GITEE_API")
        
        # 覆盖仓库配置
        repos = config.get("repos", {})
        for repo_name in ["registry", "experiences", "knowledge"]:
            if repo_name not in repos:
                repos[repo_name] = {}
            prefix = repo_name.upper()
            if os.getenv(f"EVO_{prefix}_OWNER"):
                repos[repo_name]["owner"] = os.getenv(f"EVO_{prefix}_OWNER")
            if os.getenv(f"EVO_{prefix}_REPO"):
                repos[repo_name]["repo"] = os.getenv(f"EVO_{prefix}_REPO")
        
        config["repos"] = repos
        return config
    
    @classmethod
    def load(cls, workspace: Optional[Path] = None) -> DistributedConfig:
        """加载完整配置
        
        配置文件必须存在，无硬编码默认值。
        """
        # 1. 查找配置文件（工作区优先）
        config_path = None
        loaded_from = None
        
        if workspace:
            workspace_config = workspace / ".config" / "evo.json"
            if workspace_config.is_file():
                config_path = workspace_config
                loaded_from = str(workspace_config)
        
        if not config_path:
            config_path = cls.find_config_file()
            if config_path:
                loaded_from = str(config_path)
        
        # 2. 无配置文件时报错
        if not config_path:
            example_paths = [
                Path.cwd() / ".config" / "evo.json.example",
                Path(__file__).parent.parent.parent / ".config" / "evo.json.example",
            ]
            example_path = None
            for p in example_paths:
                if p.is_file():
                    example_path = p
                    break
            
            msg = "未找到 Evo 配置文件。"
            if example_path:
                msg += f"\n请复制示例文件: cp {example_path} ./.config/evo.json"
            else:
                msg += f"\n请在以下位置创建配置文件:"
                msg += f"\n  - ./.config/evo.json (推荐)"
                msg += f"\n  - ~/.evo/config.json"
                msg += f"\n  - /etc/evo/config.json"
                msg += f"\n或设置环境变量: EVO_CONFIG_PATH"
            raise ConfigError(msg)
        
        # 3. 加载配置文件
        config = cls.load_config_file(config_path)
        if not config:
            raise ConfigError(f"配置文件为空或格式错误: {config_path}")
        
        config["_loaded_from"] = loaded_from
        
        # 4. 环境变量覆盖
        config = cls.apply_env_overrides(config)
        
        return DistributedConfig.from_dict(config)
    
    @classmethod
    def _deep_merge(cls, base: Dict, override: Dict) -> Dict:
        """深度合并"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    @classmethod
    def create_from_example(cls, target_path: Path) -> None:
        """从示例文件创建配置"""
        example_paths = [
            Path.cwd() / ".config" / "evo.json.example",
            Path(__file__).parent.parent.parent / ".config" / "evo.json.example",
        ]
        
        for example_path in example_paths:
            if example_path.is_file():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(example_path, target_path)
                return
        
        raise ConfigError("未找到示例配置文件 evo.json.example")


def get_distributed_config(workspace: Optional[Path] = None) -> DistributedConfig:
    """获取配置"""
    return ConfigLoader.load(workspace)


__all__ = [
    "DistributedConfig",
    "RepoConfig",
    "ConfigLoader",
    "get_distributed_config",
    "ConfigError",
]
