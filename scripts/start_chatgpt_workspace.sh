#!/usr/bin/env bash
# Evo（evo-os）：用独立 workspace-mcp 工具包启动 ChatGPT SSE 网关
set -euo pipefail
EVO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS_ROOT="$(cd "$EVO_ROOT/../workspace-mcp" && pwd)"
CONFIG="${1:-$EVO_ROOT/mcp-superassistant/config.json}"

if [[ ! -d "$WS_ROOT" ]]; then
  echo "ERROR: 找不到 workspace-mcp: $WS_ROOT" >&2
  exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "[evo] 生成 MCP 配置（仅 shell）..."
  "$WS_ROOT/.venv/bin/python" "$WS_ROOT/scripts/init_workspace_mcp.py" "$EVO_ROOT" --shell-only
  CONFIG="$EVO_ROOT/mcp-superassistant/config.json"
fi

echo "[evo] 使用新工具包: $WS_ROOT"
echo "[evo] 工作区: $EVO_ROOT"
echo "[evo] ChatGPT 扩展: http://127.0.0.1:3006/sse"
exec "$WS_ROOT/scripts/start_workspace_mcp.sh" "$CONFIG"
