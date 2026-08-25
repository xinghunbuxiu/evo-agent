"""
JavaScript 指纹管理

AI 驱动的指纹生成和匹配
使用分布式指纹库存储
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4

from core import UnifiedDistributedStore, StorageConfig, get_distributed_config


class FingerprintManager:
    """指纹管理器"""
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        
        # 使用核心分布式存储
        dist_config = get_distributed_config(workspace)
        self.store = UnifiedDistributedStore(workspace, StorageConfig(distributed=dist_config))
        
        # 获取领域专用存储
        self.domain_store = self.store.get_domain_store("javascript", "fingerprints")
    
    def generate_from_analysis(self, analysis_result: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """从分析结果 AI 生成指纹"""
        fingerprints = {
            "version": "2.0",
            "run_id": run_id,
            "domain": "javascript",
            "generated_at": json.dumps({}),
            "framework_rules": [],
            "library_rules": {},
            "signal_rules": [],
        }
        
        # 生成框架规则
        for framework in analysis_result.get("frameworks", []):
            rule = {
                "id": f"fp_framework_{framework}_{uuid4().hex[:8]}",
                "type": "framework",
                "name": framework,
                "patterns": self._get_framework_patterns(framework),
                "confidence": 0.9,
            }
            fingerprints["framework_rules"].append(rule)
            
            # 保存到领域存储
            self.domain_store.save(rule, "frameworks", rule["id"])
        
        # 生成库规则
        for lib in analysis_result.get("libraries", []):
            lib_name = lib["name"]
            fingerprints["library_rules"][lib_name] = {
                "framework": lib.get("framework"),
                "confidence": lib.get("confidence", 0.8),
                "version_hints": [],
            }
        
        # 生成信号规则
        for signal in analysis_result.get("code_signals", []):
            rule = {
                "id": f"fp_signal_{signal['type']}_{uuid4().hex[:8]}",
                "type": "signal",
                "signal_type": signal["type"],
                "confidence": signal.get("confidence", 0.7),
            }
            fingerprints["signal_rules"].append(rule)
        
        return fingerprints
    
    def _get_framework_patterns(self, framework: str) -> List[str]:
        """获取框架特征模式"""
        patterns = {
            "vue": ["createApp", "Vue.", ".vue"],
            "react": ["createElement", "React.", "jsx"],
            "angular": ["ng-", "@angular"],
        }
        return patterns.get(framework, [])
    
    def load_fingerprints(self, framework: Optional[str] = None) -> Dict[str, Any]:
        """加载指纹"""
        if framework:
            # 加载特定框架指纹
            fp = self.domain_store.load("frameworks", f"fp_framework_{framework}")
            return fp or {}
        else:
            # 加载所有
            return {
                "frameworks": self.domain_store.load("frameworks"),
                "libraries": self.domain_store.load("libraries"),
            }
