#!/usr/bin/env python3
"""项目初始化命令 - 创建标准目录结构和初始配置。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from restorex_lib.cache_paths import ensure_cache_structure, get_cache_paths
from restorex_lib.fs_utils import write_json


def cmd_init_project(
    workspace: Path,
    skip_verify: bool = False,
) -> dict[str, Any]:
    """初始化新项目，创建标准结构。
    
    创建：
    1. cache 分层目录结构
    2. 默认配置文件
    3. plugin 代码清单（用于完整性校验）
    4. .gitignore
    
    Returns:
        {"ok": True, "created": [...], "issues": [...]}
    """
    created = []
    issues = []
    
    # 1. 创建 cache 分层结构
    cache_paths = ensure_cache_structure(workspace)
    created.append("cache/ layered structure")
    
    # 2. 创建默认配置文件
    _create_default_configs(workspace, cache_paths, created, issues)
    
    # 3. 生成 plugin manifest
    _generate_plugin_manifest(workspace, created, issues)
    
    # 4. 创建 .gitignore
    _create_gitignore(workspace, created)
    
    # 5. 检查输入文件
    if not skip_verify:
        input_issues = _check_input_files(workspace)
        issues.extend(input_issues)
    
    return {
        "ok": len([i for i in issues if not i.startswith("Missing")]) == 0,
        "created": created,
        "issues": issues,
    }


def _create_default_configs(
    workspace: Path,
    cache_paths: Any,
    created: list,
    issues: list
) -> None:
    """创建默认配置文件。"""
    
    # project_hints.json
    hints_path = cache_paths.project / "project_hints.json"
    if not hints_path.exists():
        hints = {
            "version": "1.0",
            "module_hints": {},
            "hotspot_candidates": [],
            "dedupe_target_prefixes": [],
            "flow_tag_extra_patterns": [],
        }
        write_json(hints_path, hints)
        created.append("cache/project/project_hints.json")
    
    # semantic_rules.json
    semantic_path = cache_paths.project / "semantic_rules.json"
    if not semantic_path.exists():
        rules = {
            "version": "1.0",
            "rules": [],
            "patterns": {},
        }
        write_json(semantic_path, rules)
        created.append("cache/project/semantic_rules.json")
    
    # fingerprint_publish.yaml
    publish_config = workspace / "cache" / "project" / "fingerprint_publish.yaml"
    if not publish_config.exists():
        config = {
            "version": "1.0",
            "publish": {
                "target": "gitee",
                "repo": "",
                "branch": "main",
                "auto_publish": {
                    "conditions": [
                        "verify_report.ok == true",
                        "final_summary.applied_renames_total >= 50"
                    ],
                    "require_review_if": [
                        "final_summary.suspicious_renames > 0"
                    ]
                }
            }
        }
        import yaml
        with open(publish_config, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        created.append("cache/project/fingerprint_publish.yaml")
    
    # version file
    version_path = cache_paths.core / "version"
    if not version_path.exists():
        version_path.write_text("1.0.0\n", encoding='utf-8')
        created.append("cache/core/version")


def _generate_plugin_manifest(
    workspace: Path,
    created: list,
    issues: list
) -> None:
    """生成 plugin 代码清单。"""
    script_path = workspace / "script" / "generate_plugin_manifest.py"
    if script_path.exists():
        try:
            result = subprocess.run(
                ["python3", str(script_path), "--workspace", str(workspace)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                created.append("cache/core/plugin_manifest.json")
            else:
                issues.append(f"Failed to generate plugin manifest: {result.stderr}")
        except Exception as e:
            issues.append(f"Failed to generate plugin manifest: {e}")
    else:
        issues.append("Manifest generator not found: script/generate_plugin_manifest.py")


def _create_gitignore(workspace: Path, created: list) -> None:
    """创建 .gitignore 文件。"""
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        content = """# RestoreX generated
output/
cache/runtime/
cache/ai_generated/analysis_cache/
cache/ai_generated/chain_graph_cache/
__pycache__/
*.pyc

# But keep these
cache/core/
cache/project/
cache/remote/
cache/ai_generated/fingerprints/
cache/ai_generated/portraits/
spec/
!spec/fingerprint_registry.json
.workflow/temp_*/
"""
        gitignore.write_text(content, encoding='utf-8')
        created.append(".gitignore")


def _check_input_files(workspace: Path) -> list[str]:
    """检查必要的输入文件。"""
    issues = []
    
    manifest = workspace / "input" / "manifest.json"
    if not manifest.exists():
        issues.append("Missing: input/manifest.json (create this file with bundle metadata)")
    
    raw_bundle = workspace / "input" / "raw_bundle"
    if not raw_bundle.exists() or not any(raw_bundle.iterdir()):
        issues.append("Missing: input/raw_bundle/ (place bundle files here)")
    
    return issues
