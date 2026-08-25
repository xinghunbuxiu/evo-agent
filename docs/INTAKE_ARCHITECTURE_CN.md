# 商业接单（Intake）架构

配置驱动的**商业消费环**：公司接单 → 智脑按 capability 推荐员工 → 育成确认分派 → 插件履约 → 结算入财务 → 经验上云。

**原则**：一切以可结算的商业交付为目的；路由与履约**禁止**写死平台/工种品牌字符串（如某内容渠道名），只认 capability、work_type 配置与 worker 注册表。

## 状态机

```
received → analyzing → assigned → in_progress → delivered → settled
                ↘ cancelled
```

| 状态 | 触发 |
|------|------|
| `received` | 接单台创建 |
| `analyzing` | 智脑路由生成候选 |
| `assigned` | 育成确认分派并创建正式任务 |
| `in_progress` | 员工提交任务结果 |
| `delivered` | 育成确认任务（approve） |
| `settled` | 财务记入营收 |
| `cancelled` | 取消 |

## 核心实体

`runtime["intake_center"].items[]`：

- `intake_id`, `title`, `description`, `expected_deliverables[]`
- `needed_capabilities[]`（能力语义，非工种名）
- `budget` / `quoted_amount` / `settled_amount` / `currency`
- `status`, `member_id`, `task_id`, `project_id`
- `routing`（候选与理由）, `fulfillment`（worker 契约摘要）
- `source`：`outsourcing` | `internal`

## 配置

- `.admin/intake_routing_policies.json`：按 `when_capability` 匹配 `resolve_by`
- `work_types.json` 可选 `collaboration.can_provide_capabilities` / `intake.default_capabilities`
- Worker manifest `task_types`（`operation_*`）驱动履约计划，intake 核心不写死平台名
- `finalize_operation_result` 完成后调用 `attach_operation_artifacts_to_intake`：把 `draft_path` / `article_path` 等通用路径写入 `fulfillment.artifacts`，并镜像到正式任务 metadata（员工工作台 / 接单台可见）

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/autonomy/intake/policies` | 策略摘要 |
| GET | `/api/autonomy/intake` | 列表 + 漏斗汇总 |
| POST | `/api/autonomy/intake` | 创建接单 |
| POST | `/api/autonomy/intake/{id}/analyze` | 智脑路由 |
| POST | `/api/autonomy/intake/{id}/assign` | 育成确认分派 |
| POST | `/api/autonomy/intake/{id}/settle` | 财务结算 |
| POST | `/api/autonomy/intake/{id}/cancel` | 取消 |

任务 submit/approve 钩子会推进 `in_progress` / `delivered`；settle 调用 `upsert_finance_period`。

## 路由反馈飞轮（反硬编码）

- 文件：`.admin/intake_routing_feedback.json`（运行时追加，非写死工种分支）
- **改派**：育成分派 ≠ 智脑推荐时记录 `assign_override` + `override_reason`
- **结算成功**：记录 `settle_success`，下一轮 `analyze` 对同能力重叠成员加分；多次被改派跳过则轻微减分
- 结算后自动把商业经验卡落到 `.admin/local_git_exports/<tenant>/exports/commercial/`（远端未就绪时本地验收）；成功则清 `pending_git_export`，失败则保留标记
