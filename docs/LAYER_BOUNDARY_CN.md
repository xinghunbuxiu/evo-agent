# Evo 个人公司智脑 · 分层边界

## 原则

1. **`src/core/`** 只放跨领域内核（决策、存储、租户、队列），不写具体工种逻辑
2. **`src/domains/`** 只放内置能力实现（如 JavaScript analyze/reconstruct）
3. **`src/admin/`** 负责 HTTP、会话、策略治理与运行时编排
4. **`src/workers/`** 与 **`executors/`** 放外部工种与执行器，通过能力包与任务队列接入
5. **运行时数据**（`.queue/`、`.tenants/`、`.admin/`）与代码分离，不入库

## 目录结构（当前）

```
evo-os/
├── src/
│   ├── core/           # 内核：capabilities、decision、learning、tenant、task_queue
│   ├── admin/          # Admin API + 各 runtime（strategy、autonomy、self_media…）
│   ├── domains/        # 内置能力包（javascript / android 占位 / pc 占位）
│   ├── workers/        # 工种 worker（如自媒体运营）
│   └── server.py       # 平台自检（冒烟，非 HTTP 服务）
├── admin-ui/           # 管理前端
├── plugins/            # 可插拔能力扩展
├── executors/          # 外部执行器（CLI/脚本）
├── openSpec/workers/   # 工种 OpenSpec
├── .config/            # evo.json 等平台配置
└── evo_workbench/      # 默认工作区（Docker 挂载）
```

## 工作区边界

| 路径 | 用途 | 清空策略 |
|------|------|----------|
| `EVO_ADMIN_WORKSPACE` | 租户数据、经验、输入样本 | 按租户管理 |
| `.cache/` | 分布式缓存、指纹等 | 可重建 |
| `.queue/` | 异步任务 | 消费后归档或清理 |
| `.tenants/` | 租户隔离目录 | 勿删生产租户 |
| `.admin/` | Admin 运行时 JSON | 服务可重建 |

## 调用边界

- **对外入口**：`admin.server:create_app`（FastAPI），非 MCP stdio
- **能力调用**：`DecisionEngine` → `CapabilityRegistry` → `domains/*` 或 `plugins/*`
- **指纹**：`POST /api/fingerprint/generate`，实现见 `domains/javascript/fingerprint.py`

更完整的模块说明见 [ARCHITECTURE.md](../ARCHITECTURE.md)。
