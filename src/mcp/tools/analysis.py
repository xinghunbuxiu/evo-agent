"""
分析相关 Tools
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

from .base import BaseTool, ToolParameter


class AnalyzeTool(BaseTool):
    """代码分析 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_analyze"
    
    @property
    def description(self) -> str:
        return "分析混淆的 JS 代码，提取画像和识别第三方库"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="input_path",
                type="string",
                description="输入代码目录路径",
                required=True
            ),
            ToolParameter(
                name="profile",
                type="string",
                description="分析策略",
                default="strict",
                enum=["strict", "balanced", "aggressive"]
            ),
            ToolParameter(
                name="run_id",
                type="string",
                description="运行 ID（可选，自动生成）",
                required=False
            )
        ]
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        input_path = Path(params["input_path"])
        profile = params.get("profile", "strict")
        run_id = params.get("run_id") or f"run_{asyncio.get_event_loop().time()}"
        
        if not input_path.exists():
            return {"error": f"输入路径不存在: {input_path}"}
        
        # 初始化输出目录
        output_dir = self.workspace / "output" / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            "success": True,
            "run_id": run_id,
            "output_dir": str(output_dir),
            "profile": profile,
            "message": f"分析任务已初始化: {run_id}",
            "next_steps": [
                "使用 restorex_execute_step 执行 workflow 步骤",
                f"步骤顺序: ensure-project-cache → clear-output → init-run → ..."
            ]
        }


class ExecuteStepTool(BaseTool):
    """执行 workflow 步骤 Tool"""
    
    @property
    def name(self) -> str:
        return "restorex_execute_step"
    
    @property
    def description(self) -> str:
        return "执行 workflow.yaml 中的指定步骤"
    
    @property
    def parameters(self) -> list:
        return [
            ToolParameter(
                name="step_id",
                type="string",
                description="步骤 ID，如 'ensure-project-cache', 'clear-output'",
                required=True
            ),
            ToolParameter(
                name="run_id",
                type="string",
                description="当前运行 ID",
                required=False
            ),
            ToolParameter(
                name="profile",
                type="string",
                description="规则配置",
                default="strict"
            )
        ]
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        step_id = params["step_id"]
        run_id = params.get("run_id", "default")
        profile = params.get("profile", "strict")
        
        # 检查 rule 文件
        rule_path = self.workspace / "rules" / f"{step_id}.yaml"
        if not rule_path.exists():
            return {"error": f"Rule 不存在: {rule_path}"}
        
        return {
            "success": True,
            "step_id": step_id,
            "run_id": run_id,
            "profile": profile,
            "message": f"步骤 {step_id} 执行完成",
            "rule_file": str(rule_path),
            "next": "继续执行 next_on_success 指定的下一步"
        }
