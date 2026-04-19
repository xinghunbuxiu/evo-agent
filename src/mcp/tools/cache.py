"""
Cache 相关 Tools
"""

import sys
from pathlib import Path
from typing import Any, Dict

from .base import BaseTool, ToolParameter


class CacheTool(BaseTool):
    """缓存验证 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_verify_cache"
    
    @property
    def description(self) -> str:
        return "验证 cache 分层结构是否完整"
    
    @property
    def parameters(self) -> list:
        return []
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sys.path.insert(0, str(self.workspace / "src" / "engine"))
        
        try:
            from engine.restorex_lib.cache_paths import get_cache_paths
            
            paths = get_cache_paths(self.workspace)
            
            results = {}
            for attr in ["core", "ai_generated", "project", "remote", "runtime"]:
                path = getattr(paths, attr)
                exists = path.exists()
                if not exists:
                    path.mkdir(parents=True, exist_ok=True)
                results[attr] = {
                    "path": str(path),
                    "exists": exists or path.exists()
                }
            
            all_exist = all(r["exists"] for r in results.values())
            
            return {
                "success": all_exist,
                "all_exist": all_exist,
                "paths": results,
                "message": "缓存结构完整" if all_exist else "部分目录已创建"
            }
        except Exception as e:
            return {"error": str(e)}
