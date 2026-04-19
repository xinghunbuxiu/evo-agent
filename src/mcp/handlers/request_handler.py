"""
请求处理器
将 MCP 请求路由到对应的 Tool
"""

from typing import Any, Dict
from ..tools.registry import ToolRegistry


class RequestHandler:
    """MCP 请求处理器"""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
    
    async def handle_tool_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 Tool 调用请求"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return {"error": "缺少 tool name"}
        
        return await self.tool_registry.execute(tool_name, arguments)
