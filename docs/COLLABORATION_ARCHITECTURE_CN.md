# 跨工种协作架构（配置驱动）

## 1. 目标

在**不写死具体工种**（如 App 前端、Java 后台）的前提下，支持：

- 员工在**职责内并行执行**，不因跨工种依赖而整单阻塞；
- 通过 **能力语义（capability）** 向编排层（育成师）发起协作请求；
- 育成师指派提供方员工与正式任务；
- 提供方任务 **submit → approve** 后，按策略通知请求方「可对接」；
- 请求方**先收尾当前阶段**，再进入对接（`integration_pending`）。

## 2. 分层

| 层 | 角色 | 职责 |
|----|------|------|
| L1 执行层 | 任意 `work_type` 员工 | 本工种任务执行；可发起 `CollaborationRequest` |
| L2 编排层 | 育成师 | 受理请求、指派提供方、审核交付、触发通知 |
| L3 经营层 | 公司管理者 | 可选；争议、加资源、改策略 |

部门（`department_id`）仅用于**路由权重**，不是代码分支。

## 3. 核心实体

### CollaborationRequest

| 字段 | 说明 |
|------|------|
| `request_id` | 唯一 ID |
| `requester_member_id` | 发起方 |
| `requester_task_id` | 关联正式任务（可选） |
| `needed_capability` | 能力语义，如 `auth_api` |
| `target_work_type_id` | 可选，缩小提供方工种 |
| `target_department_id` | 可选，缩小部门 |
| `status` | 状态机 |
| `requester_continues` | 默认 `true` |

### CollaborationAssignment

育成师指派后产生，关联 `provider_member_id` 与 `provider_task_id`。

### IntegrationPending（挂在请求方任务上）

```json
{
  "collaboration_request_id": "...",
  "phase": "waiting_assignment | waiting_delivery | ready_to_integrate | integrated"
}
```

主任务保持 `assigned` / 执行中，**不使用**整单 `blocked`。

## 4. 状态机

```
open → assigned → provider_submitted → approved → integrated → closed
  ↘ cancelled / escalated
```

| 状态 | 触发 |
|------|------|
| `open` | 创建请求 |
| `assigned` | 育成师 `assign` |
| `provider_submitted` | 提供方任务 submit |
| `approved` | 提供方任务 approve |
| `integrated` | 请求方 `mark-integrated` |
| `closed` | 关闭 |

## 5. 配置（非硬编码）

### `.admin/collaboration_policies.json`

- `rules[]`：按 `when_capability` 匹配
- `resolve_by`：`trainer_manual` | `idle_member_in_work_type` | `round_robin`
- `notify_on_approved`：如 `["requester"]`
- `message_template_id`：通知文案模板
- `deliverable_template_id`：交付物结构引用

### `.admin/deliverable_templates.json`

可复用交付物字段定义（如 `api_contract_v1`）。

### `work_types.json` 扩展（可选）

```json
"collaboration": {
  "can_request_capabilities": ["auth_api"],
  "can_provide_capabilities": ["rest_api", "auth_api"]
}
```

## 6. API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/autonomy/collaborations` | 创建协作请求 |
| GET | `/api/autonomy/collaborations` | 列表（`role=orchestrator\|requester\|provider`） |
| GET | `/api/autonomy/collaborations/policies` | 只读策略与模板摘要 |
| POST | `/api/autonomy/collaborations/{id}/assign` | 育成师指派提供方 |
| POST | `/api/autonomy/collaborations/{id}/mark-integrated` | 请求方确认已对接 |

## 7. 与现有模块衔接

| 模块 | 衔接 |
|------|------|
| `task_center` | 提供方仍用 assign / submit / approve |
| `relationship_center` | 线程 `collab:{request_id}` + 审核后 `collaboration_ready` 通知 |
| `tasks/approve` | hook：`maybe_finalize_provider_collaboration` |
| `tasks/submit` | hook：更新为 `provider_submitted` |
| `trainer_coaching_runtime` | 可选记录编排事件 |

## 8. 示例场景（仅配置表达）

登录页需要认证 API：

1. 请求方工种配置 `can_request: auth_api`
2. 策略规则 `when_capability: auth_api` → `prefer_department_id: rnd`，`resolve_by: trainer_manual`
3. 提供方工种配置 `can_provide: auth_api`，交付模板 `api_contract_v1`
4. 全程代码无 App/Java 字符串

## 9. 后续（非 M1 架构阶段）

- Admin UI：协作队列、待对接横幅
- `idle_member_in_work_type` 自动指派
- 交付物 JSON Schema 校验
