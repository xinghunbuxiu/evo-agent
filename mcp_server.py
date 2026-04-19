#!/usr/bin/env python3
"""
RestoreX MCP Server - 入口文件

模块化 MCP 服务入口，所有实现位于 mcp/ 目录

Usage:
    python3 mcp_server.py
    python3 mcp_server.py --workspace /path/to/project
"""

import sys
import asyncio
import argparse
from pathlib import Path

# 确保可以导入 src 下的模块
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "src" / "engine"))

from src.mcp import RestoreXMCPServer


def main():
    parser = argparse.ArgumentParser(description="RestoreX MCP Server")
    parser.add_argument("--workspace", "-w", default=".", help="工作目录")
    parser.add_argument("--transport", "-t", default="stdio", choices=["stdio"], help="传输方式")
    
    args = parser.parse_args()
    
    workspace = Path(args.workspace).resolve()
    
    print(f"[MCP] RestoreX Server 启动", file=sys.stderr)
    print(f"[MCP] Workspace: {workspace}", file=sys.stderr)
    print(f"[MCP] Transport: {args.transport}", file=sys.stderr)
    print(f"[MCP] 等待连接...", file=sys.stderr)
    
    server = RestoreXMCPServer(workspace)
    
    if args.transport == "stdio":
        asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
