"""
JavaScript 领域命令

初始化、分析、重构的统一入口
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

from core import TenantManager, get_distributed_config
from .analyzer import JSAnalyzer
from .fingerprint import FingerprintManager
from .reconstructor import JSReconstructor


def _build_feedback_metadata(
    capability_id: str,
    task_type: str,
    frameworks: Optional[List[str]] = None,
    libraries: Optional[List[Dict[str, Any]]] = None,
    patterns: Optional[List[str]] = None,
    decision: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "capability_id": capability_id,
        "task_type": task_type,
        "frameworks": frameworks or [],
        "libraries": [lib["name"] if isinstance(lib, dict) and "name" in lib else lib for lib in (libraries or [])],
        "patterns": patterns or [],
    }
    if decision:
        metadata["decision"] = decision
    if extra:
        metadata.update(extra)
    return metadata


def init_workspace(workspace: Path, tenant_id: str = "default") -> Dict[str, Any]:
    """初始化 JavaScript 分析工作区"""
    # 创建租户
    tenant_mgr = TenantManager(workspace)
    tenant = tenant_mgr.create_tenant(
        tenant_id=tenant_id,
        name=f"JS Tenant {tenant_id}",
        domains=["javascript"]
    )
    
    # 创建目录结构
    dirs = [
        workspace / ".tenants" / tenant_id / "data",
        workspace / ".tenants" / tenant_id / "experiences",
        workspace / ".tenants" / tenant_id / "skills",
        workspace / "input",
        workspace / "output",
        workspace / ".config",
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    
    # 创建领域配置文件
    config_path = workspace / ".config" / "javascript.json"
    if not config_path.is_file():
        dist_config = get_distributed_config(workspace)
        import json
        domain_config = {
            "extends": "core",
            "domain": "javascript",
            "repos": {
                "fingerprints": {
                    "owner": dist_config.registry.owner,
                    "repo": "evo-javascript-fingerprints",
                    "branch": "main"
                }
            },
            "tools": {
                "parser": "acorn",
                "bundler_detector": True,
            }
        }
        with open(config_path, "w") as f:
            json.dump(domain_config, f, indent=2, ensure_ascii=False)
    
    return {
        "success": True,
        "tenant_id": tenant_id,
        "workspace": str(workspace),
        "status": "initialized",
    }


def analyze_bundle(
    workspace: Path,
    bundle_path: Path,
    tenant_id: str = "default",
    save_experience: bool = True,
    capability_id: str = "builtin.javascript",
    decision: Optional[Dict[str, Any]] = None,
    skill_template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """分析 JS 代码包"""
    # 初始化分析器
    analyzer = JSAnalyzer(workspace, tenant_id)
    skill_template = skill_template if isinstance(skill_template, dict) else {}
    
    # 执行分析
    result = analyzer.analyze(bundle_path, skill_template=skill_template)
    
    # 生成指纹
    fp_mgr = FingerprintManager(workspace, tenant_id)
    fingerprints = fp_mgr.generate_from_analysis(
        {
            "frameworks": result.frameworks,
            "libraries": result.libraries,
            "code_signals": result.code_signals,
        },
        run_id=f"analyze_{hash(bundle_path) % 100000}"
    )
    
    # 记录经验
    if save_experience:
        from core import Experience, ExperienceStore
        exp = Experience(
            id=f"js_analyze_{hash(bundle_path) % 10000}",
            domain="javascript",
            task_type="analyze",
            input_summary=str(bundle_path),
            output_summary=f"Frameworks: {result.frameworks}",
            quality_score=result.confidence,
            metadata=_build_feedback_metadata(
                capability_id=capability_id,
                task_type="analyze",
                frameworks=result.frameworks,
                libraries=result.libraries,
                patterns=result.patterns,
                decision=decision,
                extra={
                    "bundle_path": str(bundle_path),
                    "fingerprints_generated": len(fingerprints.get("framework_rules", [])),
                    "skill_template": skill_template,
                },
            ),
        )
        exp_store = ExperienceStore(workspace, tenant_id)
        exp_store.save(exp)
    
    return {
        "success": True,
        "frameworks": result.frameworks,
        "libraries": result.libraries,
        "patterns": result.patterns,
        "fingerprints_generated": len(fingerprints.get("framework_rules", [])),
        "confidence": result.confidence,
        "skill_template_applied": bool(skill_template),
        "skill_template": skill_template,
    }


def reconstruct_project(
    workspace: Path,
    analysis_result: Dict[str, Any],
    source_dir: Path,
    tenant_id: str = "default",
    capability_id: str = "builtin.javascript",
    decision: Optional[Dict[str, Any]] = None,
    skill_template: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """重构项目"""
    reconstructor = JSReconstructor(workspace, tenant_id)
    skill_template = skill_template if isinstance(skill_template, dict) else {}

    plan = reconstructor.create_plan(analysis_result, source_dir, skill_template=skill_template)
    result = reconstructor.execute_plan(
        plan,
        capability_id=capability_id,
        decision=decision,
        skill_template=skill_template,
    )
    
    return result
