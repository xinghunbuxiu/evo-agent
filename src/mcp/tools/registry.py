"""
Tool 注册表
负责发现和注册所有 Tools
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool

# 自动导入所有 tools
sys.path.insert(0, str(Path(__file__).parent))


class ToolRegistry:
    """Tool 注册表"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._tools: Dict[str, BaseTool] = {}
        self._discover_and_register()
    
    def _discover_and_register(self) -> None:
        """发现并注册所有 Tools"""
        from .analysis import AnalyzeTool
        from .workflow import WorkflowTool
        from .fingerprint import FingerprintTool
        from .cache import CacheTool
        from .status import StatusTool
        
        tools = [
            AnalyzeTool(self.workspace),
            WorkflowTool(self.workspace),
            FingerprintTool(self.workspace),
            CacheTool(self.workspace),
            StatusTool(self.workspace),
        ]
        
        for tool in tools:
            self._tools[tool.name] = tool
    
    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """获取所有 Tool 定义"""
        return [tool.get_definition() for tool in self._tools.values()]
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取指定 Tool"""
        return self._tools.get(name)
    
    async def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Tool"""
        tool = self.get_tool(name)
        if not tool:
            return {"error": f"未知 Tool: {name}"}
        
        # 验证参数
        error = tool.validate_params(params)
        if error:
            return {"error": error}
        
        try:
            return await tool.execute(params)
        except Exception as e:
            return {"error": f"执行失败: {str(e)}"}
