"""
Evo Domain: Android 分析

APK 反编译、字节码分析、资源提取
基于 Evo Core 的分布式存储
"""

__version__ = "2.0.0"
__domain__ = "android"

from .analyzer import AndroidAnalyzer
from .decompiler import APKDecompiler

__all__ = ["AndroidAnalyzer", "APKDecompiler"]
