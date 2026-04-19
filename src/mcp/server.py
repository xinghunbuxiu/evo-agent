#!/usr/bin/env python3
"""
MCP Server 核心
负责协议处理、请求路由和生命周期管理
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from .tools.registry import ToolRegistry
from .handlers.request_handler import RequestHandler


class RestoreXMCPServer:
    """RestoreX MCP 服务核心"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.tool_registry = ToolRegistry(self.workspace)
        self.request_handler = RequestHandler(self.tool_registry)
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个 MCP 请求"""
        method = request.get("method")
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                result = self._handle_initialize()
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                params = request.get("params", {})
                result = await self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list()
            else:
                result = {"error": f"未知方法: {method}"}
            
            if request_id is not None:
                result["id"] = request_id
            
            return result
            
        except Exception as e:
            return {
                "id": request_id,
                "error": f"处理请求失败: {str(e)}"
            }
    
    def _handle_initialize(self) -> Dict[str, Any]:
        """处理初始化请求"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "serverInfo": {
                "name": "restorex-mcp-server",
                "version": "1.0.0",
                "workspace": str(self.workspace)
            }
        }
    
    def _handle_tools_list(self) -> Dict[str, Any]:
        """返回可用 Tools 列表"""
        return {
            "tools": self.tool_registry.get_all_definitions()
        }
    
    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Tool 调用"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return {"error": "缺少 tool name"}
        
        return await self.tool_registry.execute(tool_name, arguments)
    
    def _handle_resources_list(self) -> Dict[str, Any]:
        """返回可用 Resources 列表"""
        return {
            "resources": [
                {
                    "uri": "workflow://current",
                    "name": "当前 Workflow",
                    "mimeType": "text/yaml"
                },
                {
                    "uri": "cache://structure",
                    "name": "Cache 结构",
                    "mimeType": "application/json"
                }
            ]
        }
    
    async def run_stdio(self) -> None:
        """通过 STDIO 运行服务"""
        while True:
            try:
                line = input()
                if not line:
                    continue
                
                request = json.loads(line)
                response = await self.handle_request(request)
                
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
                
            except EOFError:
                break
            except json.JSONDecodeError as e:
                self._send_error(f"JSON 解析错误: {e}")
            except Exception as e:
                self._send_error(str(e))
    
    def _send_error(self, message: str) -> None:
        """发送错误响应"""
        print(json.dumps({"error": message}, ensure_ascii=False))
        sys.stdout.flush()
