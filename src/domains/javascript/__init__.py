"""
Evo Domain: JavaScript 分析

混淆代码还原、依赖识别、架构重构
继承 Evo Core 的分布式存储和学习能力
"""

__version__ = "2.0.0"
__domain__ = "javascript"

from .analyzer import JSAnalyzer
from .fingerprint import FingerprintManager
from .reconstructor import JSReconstructor
from .commands import (
    init_workspace,
    analyze_bundle,
    reconstruct_project,
)
from .provider import JavaScriptCapabilityProvider

__all__ = [
    "JSAnalyzer",
    "FingerprintManager", 
    "JSReconstructor",
    "JavaScriptCapabilityProvider",
    "init_workspace",
    "analyze_bundle",
    "reconstruct_project",
]
