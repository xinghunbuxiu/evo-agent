# 商业智脑原则（实现约束）

Evo 是**个人公司的商业智脑操作系统**。实现与评审须遵守本文件。

## 1. 商业优先

- 主环是**消费环**：接单 → 分析分派 → 交付 → **结算** → 经验上云。
- 供给环（育成、补知识、训练）是**产能投资**，不是产品终点。
- Intake 必须可携带商业字段：`budget` / `quoted_amount` / `settled_amount` / `currency` / `project_id`。
- 验收以 **delivered → settled（财务可见）** 为准，不只是训练票 approve。

## 2. 智脑可配置（禁止业务硬编码）

| 允许 | 禁止 |
|------|------|
| `needed_capability`、策略 JSON、`work_types` 注册表 | 核心路径 `if work_type == "…"` / `if channel == "toutiao"` |
| 成员 `can_provide_capabilities`、负载、独立运营度 | 硬编码员工 id / 部门名分支 |
| worker 插件 manifest 驱动履约 | 把某平台 CLI 路径写进 intake 核心 |
| Schema + `.admin/*_policies.json` | 为演示在 server 里塞死工种名 |

首条业务线（如自媒体）**只能**作为 worker / executor / work_type 配置出现；intake / 路由层只认 capability 与插件契约。

## 3. 两条环

1. **供给环**：建档 → 补知识 → 训练 → 复盘 → 技能/经验 → Gitee。  
2. **消费环**：接单台 → 智脑路由 → 育成确认 → 员工履约 → 财务结算 → 沉淀反哺。

## 4. 相关文件

- 接单架构：[INTAKE_ARCHITECTURE_CN.md](./INTAKE_ARCHITECTURE_CN.md)
- 协作（同构能力语义）：[COLLABORATION_ARCHITECTURE_CN.md](./COLLABORATION_ARCHITECTURE_CN.md)
- 策略 Schema：`docs/schemas/intake_routing_policies.schema.json`
