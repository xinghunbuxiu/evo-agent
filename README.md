# RestoreX MCP Server

RestoreX 的 MCP (Model Context Protocol) 服务实现。

作为独立研发项目，提供完整的 JS 逆向还原能力，通过 MCP 协议供任何 AI 调用。

## 项目地址

- **Gitee**: https://gitee.com/xinghunbuxiu/restorex-core.git

## 架构

```
┌─────────────────────────────────────────────┐
│           AI Client (Windsurf/Cursor/Claude) │
│                  ↓                           │
│              MCP Protocol                    │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│       RestoreX MCP Server (本项目)          │
│  ┌─────────────┐  ┌─────────────────────┐   │
│  │   MCP API   │  │    Tool Registry    │   │
│  │   Layer     │  │   (7 Tools)         │   │
│  └──────┬──────┘  └──────────┬──────────┘   │
│         └────────────────────┘              │
│                  ↓                           │
│         src/engine/ (逆向引擎)              │
│         src/mcp/tools/ (工具实现)            │
└─────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────┐
│         业务工作区 (外部传入)                 │
│    --workspace /path/to/restore_workbench    │
└─────────────────────────────────────────────┘
```

## 安装

### 方式 1: 命令行启动

```bash
cd /path/to/restorex-mcp
python3 -m src.mcp.server --workspace /path/to/restore_workbench
```

### 方式 2: MCP 客户端配置

#### Windsurf (`.windsurf/mcp.json`)

```json
{
  "mcpServers": {
    "restorex": {
      "command": "python3",
      "args": [
        "-m", "src.mcp.server",
        "--workspace", "/path/to/restore_workbench"
      ]
    }
  }
}
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "restorex": {
      "command": "python3",
      "args": [
        "-m", "src.mcp.server",
        "--workspace", "/path/to/restore_workbench"
      ]
    }
  }
}
```

## 项目结构

```
restorex-mcp/                 # 本研发项目
├── src/
│   ├── mcp/                 # MCP 协议层
│   │   ├── server.py        # 服务入口
│   │   ├── tools/           # 工具实现
│   │   │   ├── analysis.py
│   │   │   ├── workflow.py
│   │   │   ├── fingerprint.py
│   │   │   └── ...
│   │   └── handlers/        # 请求处理器
│   └── engine/              # 核心引擎
│       ├── restorex_cli.py
│       └── restorex_lib/    # 逆向分析库
├── config/                  # 默认配置
│   ├── workflow.yaml        # 流程定义
│   └── rules/*.yaml         # 执行规则
├── spec/                    # 指纹规范
│   └── fingerprint_registry.json
└── docs/                    # 技术文档
```

## 提供的 Tools

| Tool | 描述 |
|------|------|
| `restorex_analyze` | 分析混淆代码 |
| `restorex_execute_step` | 执行 workflow 步骤 |
| `restorex_read_workflow` | 读取 workflow 定义 |
| `restorex_extract_fingerprints` | 提取库指纹 |
| `restorex_sync_fingerprints` | 同步 Gitee 指纹 |
| `restorex_get_status` | 获取项目状态 |
| `restorex_verify_cache` | 验证缓存结构 |

## 配置覆盖机制

MCP 服务支持配置覆盖：

1. **默认配置**: `restorex-mcp/config/`
2. **工作区配置**: 如果 `restore_workbench/config/` 存在，则覆盖默认配置

```
restorex-mcp/config/workflow.yaml  →  默认流程
       ↓
restore_workbench/config/workflow.yaml  →  覆盖（如果存在）
```

## 开发

```bash
# 克隆项目
git clone https://gitee.com/xinghunbuxiu/restorex-core.git
cd restorex-core

# 启动 MCP 服务（使用示例工作区）
python3 -m src.mcp.server --workspace /path/to/restore_workbench

# 运行测试
pytest tests/
```

## 许可证

MIT
