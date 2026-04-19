#!/usr/bin/env python3
"""新 Cache 分层路径管理

分层结构：
- cache/core/           # 核心代码清单，只读
- cache/ai_generated/   # AI 产物，可读写  
- cache/project/        # 项目配置
- cache/remote/         # 远程来源
- cache/runtime/        # 运行时临时
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass


@dataclass
class CachePaths:
    """Cache 分层路径集合"""
    # 根目录
    cache: Path
    
    # Core - 核心代码（只读）
    core: Path
    
    # AI Generated - AI 产物
    ai_generated: Path
    ai_portraits: Path
    ai_fingerprints: Path
    ai_analysis_cache: Path
    ai_chain_graph_cache: Path
    
    # Project - 项目配置
    project: Path
    
    # Remote - 远程来源
    remote: Path
    remote_profiles: Path
    
    # Runtime - 运行时临时
    runtime: Path
    runtime_evidence: Path
    runtime_logs: Path


def ensure_cache_structure(workspace: Path) -> CachePaths:
    """确保 cache 分层目录结构存在，返回路径对象。"""
    cache = workspace / "cache"
    
    paths = CachePaths(
        cache=cache,
        # Core
        core=cache / "core",
        # AI Generated
        ai_generated=cache / "ai_generated",
        ai_portraits=cache / "ai_generated" / "portraits",
        ai_fingerprints=cache / "ai_generated" / "fingerprints",
        ai_analysis_cache=cache / "ai_generated" / "analysis_cache",
        ai_chain_graph_cache=cache / "ai_generated" / "chain_graph_cache",
        # Project
        project=cache / "project",
        # Remote
        remote=cache / "remote",
        remote_profiles=cache / "remote" / "profiles",
        # Runtime
        runtime=cache / "runtime",
        runtime_evidence=cache / "runtime" / "evidence",
        runtime_logs=cache / "runtime" / "logs",
    )
    
    # 创建所有目录
    for attr_name in dir(paths):
        if attr_name.startswith('_'):
            continue
        val = getattr(paths, attr_name)
        if isinstance(val, Path):
            val.mkdir(parents=True, exist_ok=True)
    
    return paths


def get_cache_paths(workspace: Path) -> CachePaths:
    """获取 cache 路径对象（不创建目录）。"""
    cache = workspace / "cache"
    
    return CachePaths(
        cache=cache,
        core=cache / "core",
        ai_generated=cache / "ai_generated",
        ai_portraits=cache / "ai_generated" / "portraits",
        ai_fingerprints=cache / "ai_generated" / "fingerprints",
        ai_analysis_cache=cache / "ai_generated" / "analysis_cache",
        ai_chain_graph_cache=cache / "ai_generated" / "chain_graph_cache",
        project=cache / "project",
        remote=cache / "remote",
        remote_profiles=cache / "remote" / "profiles",
        runtime=cache / "runtime",
        runtime_evidence=cache / "runtime" / "evidence",
        runtime_logs=cache / "runtime" / "logs",
    )


# 向后兼容：旧代码使用的路径函数

def get_portraits_path(workspace: Path) -> Path:
    """获取 portraits 路径（新结构：cache/ai_generated/portraits/）"""
    return workspace / "cache" / "ai_generated" / "portraits"


def get_fingerprints_path(workspace: Path) -> Path:
    """获取 fingerprints 路径（新结构：cache/ai_generated/fingerprints/）"""
    return workspace / "cache" / "ai_generated" / "fingerprints"


def get_fingerprint_registry_path(workspace: Path) -> Path:
    """获取 fingerprint registry 路径
    
    优先级：
    1. cache/remote/fingerprint_registry.json（远程同步）
    2. spec/fingerprint_registry.json（项目本地）
    """
    remote_path = workspace / "cache" / "remote" / "fingerprint_registry.json"
    if remote_path.is_file():
        return remote_path
    return workspace / "spec" / "fingerprint_registry.json"


def validate_ai_write_path(path: Path, workspace: Path) -> None:
    """验证 AI 写入路径，防止写入 core/ 目录。
    
    Raises:
        PermissionError: 如果路径在 core/ 下
    """
    core_path = workspace / "cache" / "core"
    try:
        path.relative_to(core_path)
        raise PermissionError(
            f"AI cannot write to core/ directory: {path}\n"
            f"Write to cache/ai_generated/ instead."
        )
    except ValueError:
        pass  # path 不在 core/ 下，允许
