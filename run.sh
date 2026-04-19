#!/bin/bash
# RestoreX 启动脚本
# 作用：启动 AI 引擎，指示 AI 读取并执行 workflow.yaml
#
# 用法：
#   ./run.sh [workspace] [profile]
#
# 示例：
#   ./run.sh . strict
#   ./run.sh /path/to/project balanced

set -euo pipefail

WORKSPACE="${1:-.}"
PROFILE="${2:-strict}"
RUN_ID="run_$(date +%Y%m%d_%H%M%S)_$$"

echo "======================================"
echo "RestoreX AI Workflow Runner"
echo "======================================"
echo "Workspace: $(cd "$WORKSPACE" && pwd)"
echo "Profile: $PROFILE"
echo "Run ID: $RUN_ID"
echo "======================================"
echo ""
echo "[指令] 请 AI 读取 workflow.yaml 并按步骤执行："
echo ""
echo "  1. 读取 workflow.yaml 了解完整流程"
echo "  2. 逐个执行每个 step 对应的 rule"
echo "  3. 验证每个 step 的 postconditions"
echo "  4. 成功后自动进入 next_on_success"
echo "  5. 失败后按 on_failure 处理"
echo ""
echo "======================================"
echo ""

# 检查环境
cd "$WORKSPACE"

if [ ! -f "config/workflow.yaml" ]; then
    echo "[错误] config/workflow.yaml 不存在"
    exit 1
fi

if [ ! -d "src/engine" ]; then
    echo "[错误] src/engine/ 目录不存在"
    exit 1
fi

echo "[状态] 环境检查通过"
echo "[提示] AI 请开始执行 workflow..."
echo ""
echo "workflow.yaml 路径: $(pwd)/config/workflow.yaml"
echo ""

# 导出变量供 AI 使用
export RESTOREX_WORKSPACE="$(pwd)"
export RESTOREX_PROFILE="$PROFILE"
export RESTOREX_RUN_ID="$RUN_ID"

echo "环境变量："
echo "  RESTOREX_WORKSPACE=$RESTOREX_WORKSPACE"
echo "  RESTOREX_PROFILE=$RESTOREX_PROFILE"
echo "  RESTOREX_RUN_ID=$RESTOREX_RUN_ID"
echo ""
echo "======================================"
echo "等待 AI 执行..."
echo "======================================"

# 脚本到此结束，AI 接管后续执行
# AI 应该：
# 1. 读取 workflow.yaml
# 2. 解析 steps
# 3. 逐个执行 rule
# 4. 输出结果
