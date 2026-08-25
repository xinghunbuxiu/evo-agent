"""
JavaScript 分析器

AI 驱动的混淆代码分析
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from core import get_distributed_config


@dataclass
class AnalysisResult:
    """分析结果"""
    frameworks: List[str]
    libraries: List[Dict[str, Any]]
    code_signals: List[Dict[str, Any]]
    patterns: List[str]
    confidence: float


class JSAnalyzer:
    """JavaScript 分析器"""
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        self.config = get_distributed_config(workspace)
        
        # 检测框架提示
        self.framework_patterns = {
            "vue": [r"createApp", r"Vue\\.", r"\\.vue"],
            "react": [r"createElement", r"React\\.", r"useState"],
            "angular": [r"ng-", r"@angular"],
            "svelte": [r"svelte", r"\\.svelte"],
        }
    
    def analyze(self, bundle_path: Path, skill_template: Optional[Dict[str, Any]] = None) -> AnalysisResult:
        """分析 JS 代码包"""
        skill_template = skill_template if isinstance(skill_template, dict) else {}
        content = bundle_path.read_text()[:100000]  # 前 100KB
        
        # 检测框架
        frameworks = self._detect_frameworks(content)
        framework_hint = str(skill_template.get("framework_hint") or "").strip().lower()
        if framework_hint and framework_hint not in frameworks:
            frameworks.insert(0, framework_hint)
        elif framework_hint and frameworks and frameworks[0] != framework_hint and framework_hint in frameworks:
            frameworks.remove(framework_hint)
            frameworks.insert(0, framework_hint)
        
        # 检测库
        libraries = self._detect_libraries(content, frameworks)
        
        # 提取代码信号
        signals = self._extract_signals(content)
        
        # 识别模式
        patterns = self._detect_patterns(content)
        
        return AnalysisResult(
            frameworks=frameworks,
            libraries=libraries,
            code_signals=signals,
            patterns=patterns,
            confidence=self._confidence_with_template(
                frameworks=frameworks,
                framework_hint=framework_hint,
            ),
        )

    def _confidence_with_template(self, *, frameworks: List[str], framework_hint: str) -> float:
        confidence = 0.8 if frameworks else 0.5
        if framework_hint and frameworks and frameworks[0] == framework_hint:
            confidence = min(0.95, confidence + 0.08)
        return confidence
    
    def _detect_frameworks(self, content: str) -> List[str]:
        """检测框架"""
        detected = []
        for framework, patterns in self.framework_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content):
                    detected.append(framework)
                    break
        return detected
    
    def _detect_libraries(self, content: str, frameworks: List[str]) -> List[Dict[str, Any]]:
        """检测第三方库"""
        libraries = []
        
        # 基于框架的常见库
        lib_patterns = {
            "vue": ["vue-router", "pinia", "vuex"],
            "react": ["react-dom", "react-router", "redux"],
        }
        
        for fw in frameworks:
            for lib in lib_patterns.get(fw, []):
                if lib in content:
                    libraries.append({
                        "name": lib,
                        "framework": fw,
                        "confidence": 0.9
                    })
        
        return libraries
    
    def _extract_signals(self, content: str) -> List[Dict[str, Any]]:
        """提取代码信号"""
        signals = []
        
        # 常见的混淆信号
        if re.search(r'function\s+[_$a-zA-Z0-9]{1,3}\(', content):
            signals.append({"type": "minified_functions", "confidence": 0.8})
        
        if re.search(r'var\s+[_$a-zA-Z0-9]{1,2}\s*=', content):
            signals.append({"type": "short_variables", "confidence": 0.7})
        
        return signals
    
    def _detect_patterns(self, content: str) -> List[str]:
        """识别代码模式"""
        patterns = []
        
        if "webpack" in content or "webpackJsonp" in content:
            patterns.append("webpack_bundled")
        
        if "rollup" in content:
            patterns.append("rollup_bundled")
        
        if "parcel" in content:
            patterns.append("parcel_bundled")
        
        return patterns
