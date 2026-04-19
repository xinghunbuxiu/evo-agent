"""
状态查询 Tools
"""

from pathlib import Path
from typing import Any, Dict, List

from .base import BaseTool, ToolParameter


class StatusTool(BaseTool):
    """项目状态查询 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_get_status"
    
    @property
    def description(self) -> str:
        return "获取当前项目状态，包括 cache 结构、可用 run、指纹等"
    
    @property
    def parameters(self) -> list:
        return []
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # 检查 cache 结构
        cache_paths = {
            "core": (self.workspace / "cache" / "core").exists(),
            "ai_generated": (self.workspace / "cache" / "ai_generated").exists(),
            "project": (self.workspace / "cache" / "project").exists(),
            "remote": (self.workspace / "cache" / "remote").exists(),
            "runtime": (self.workspace / "cache" / "runtime").exists(),
        }
        
        # 统计 runs
        output_dir = self.workspace / "output"
        runs: List[str] = []
        if output_dir.exists():
            runs = [d.name for d in output_dir.glob("run_*") if d.is_dir()]
        
        # 统计指纹
        fingerprint_dir = self.workspace / "cache" / "remote" / "fingerprint_packs"
        fingerprints = 0
        if fingerprint_dir.exists():
            fingerprints = len(list(fingerprint_dir.rglob("*.json")))
        
        # 统计 portraits
        portraits_dir = self.workspace / "cache" / "ai_generated" / "portraits"
        portraits = 0
        if portraits_dir.exists():
            portraits = len(list(portraits_dir.glob("*.json")))
        
        return {
            "success": True,
            "workspace": str(self.workspace),
            "cache_structure": cache_paths,
            "cache_ready": all(cache_paths.values()),
            "runs_count": len(runs),
            "latest_runs": runs[:5],
            "fingerprints_count": fingerprints,
            "portraits_count": portraits,
            "workflow_exists": (self.workspace / "config" / "workflow.yaml").exists(),
            "engine_exists": (self.workspace / "src" / "engine" / "restorex_cli.py").exists(),
            "summary": {
                "ready_to_use": all(cache_paths.values()) and 
                               (self.workspace / "config" / "workflow.yaml").exists() and
                               (self.workspace / "src" / "engine" / "restorex_cli.py").exists()
            }
        }
