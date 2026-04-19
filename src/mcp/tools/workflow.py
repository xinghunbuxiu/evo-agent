"""
Workflow 相关 Tools
"""

from pathlib import Path
from typing import Any, Dict, List

from .base import BaseTool, ToolParameter


class WorkflowTool(BaseTool):
    """Workflow 读取 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_read_workflow"
    
    @property
    def description(self) -> str:
        return "读取并解析 workflow.yaml，返回所有步骤"
    
    @property
    def parameters(self) -> list:
        return []
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        workflow_path = self.workspace / "config" / "workflow.yaml"
        
        if not workflow_path.exists():
            return {"error": "workflow.yaml 不存在"}
        
        try:
            import yaml
            with open(workflow_path) as f:
                workflow = yaml.safe_load(f)
            
            steps = workflow.get("workflow", {}).get("steps", [])
            
            return {
                "success": True,
                "workflow_version": workflow.get("version", "unknown"),
                "workflow_name": workflow.get("workflow", {}).get("name", "unknown"),
                "total_steps": len(steps),
                "steps": [
                    {
                        "id": s["id"],
                        "name": s["name"],
                        "rule": s.get("rule", ""),
                        "next_on_success": s.get("next_on_success", "end")
                    }
                    for s in steps
                ]
            }
        except Exception as e:
            return {"error": f"解析 workflow 失败: {e}"}
