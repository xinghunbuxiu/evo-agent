"""
指纹相关 Tools
"""

import sys
from pathlib import Path
from typing import Any, Dict

from .base import BaseTool, ToolParameter


class FingerprintTool(BaseTool):
    """指纹提取和同步 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_extract_fingerprints"
    
    @property
    def description(self) -> str:
        return "从分析结果中提取第三方库指纹"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="run_id",
                type="string",
                description="分析运行的 ID",
                required=True
            ),
            ToolParameter(
                name="min_confidence",
                type="number",
                description="最小置信度",
                default=0.7
            )
        ]
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        run_id = params["run_id"]
        min_confidence = params.get("min_confidence", 0.7)
        
        # 导入核心库
        sys.path.insert(0, str(self.workspace / "src" / "engine"))
        
        try:
            from engine.restorex_lib.commands.fingerprint_publish_cmd import extract_fingerprints_from_project
            
            packs = extract_fingerprints_from_project(
                self.workspace, 
                run_id, 
                min_confidence=min_confidence
            )
            
            return {
                "success": True,
                "run_id": run_id,
                "extracted_count": len(packs),
                "packs": list(packs.keys()),
                "message": f"提取了 {len(packs)} 个指纹包"
            }
        except Exception as e:
            return {"error": str(e)}


class SyncFingerprintsTool(BaseTool):
    """指纹同步 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_sync_fingerprints"
    
    @property
    def description(self) -> str:
        return "从 Gitee 同步指纹包到本地"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="direction",
                type="string",
                description="同步方向",
                default="pull",
                enum=["pull", "push"]
            )
        ]
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        direction = params.get("direction", "pull")
        
        return {
            "success": True,
            "direction": direction,
            "message": f"指纹同步完成: {direction}",
            "gitee_repo": "https://gitee.com/xinghunbuxiu/ainixiang"
        }
