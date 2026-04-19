"""
RestoreX MCP Server

提供 AI 逆向工程能力的 MCP (Model Context Protocol) 服务。
模块化设计，解耦 Tools、Handlers 和 Server 核心。

Usage:
    from mcp import RestoreXMCPServer
    server = RestoreXMCPServer(workspace)
"""

from .server import RestoreXMCPServer
from .tools.registry import ToolRegistry

__version__ = "1.0.0"
__all__ = ["RestoreXMCPServer", "ToolRegistry"]
