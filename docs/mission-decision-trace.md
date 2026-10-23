# Mission 分析决策追溯规范

## 目标

每个 mission 节点都应回答三个可审计问题：

1. **系统做了什么判断？** 例如缺少输入、复用现有能力、经验不足或能力缺口。
2. **判断依据是什么？** 能力注册表命中项、必需输入缺失代码、经验/已验证技能计数。
3. **下一步为什么这样做？** 由状态、缺口类型、验收条件和建议动作共同解释。

追溯记录是规则与证据的结构化摘要，不是模型的隐藏思维链；不得把密钥、令牌或不必要的原始敏感内容写入日志。

## 当前实现

`MissionPlanner.plan()` 现在同时返回计划级与节点级决策轨迹。计划级轨迹记录模板选择和计划组装，节点级轨迹记录输入校验、能力匹配、知识检查和状态决策。每条记录包括：

- `step`：阶段名称，当前为 `input_validation`、`capability_match`、`knowledge_check`、`status_decision`。
- `rule_id`：稳定的规则标识，可用于定位代码、筛选日志和建立回归测试。
- `result`：该规则的结果。
- `evidence`：可机器读取的证据，例如 blocker code、能力 ID、经验/技能计数、最终缺口类型。

当前规则 ID：

| Rule ID | 含义 |
| --- | --- |
| `mission.kind_resolution.v1` | 记录选择的任务模板、选择来源及请求的任务类型；不支持的显式类型会明确抛出 `ValueError` |
| `mission.plan_assembly.v1` | 记录计划组装时的节点数量和关联工种 |
| `mission.required_inputs.v1` | 必需输入是否齐全 |
| `mission.capability_match.v1` | 是否存在匹配的能力入口 |
| `mission.knowledge_signals.v1` | 是否存在可复用经验或已验证技能 |
| `mission.status.input_gap.v1` | 输入不足，先补齐输入 |
| `mission.status.reuse_existing.v1` | 可优先复用已有能力与知识 |
| `mission.status.knowledge_gap.v1` | 能力入口存在，但经验积累不足 |
| `mission.status.capability_gap.v1` | 没有直接匹配的能力入口 |
| `mission.status.experience_gap.v1` | 学习/复盘节点缺少首批经验 |

## 建议的完整追溯链

`request_id / mission_id → plan_version → node_id → decision_trace → dispatch_id / worker_id → execution_id → validation_id → experience_id`

每一环应保存前一环的关联 ID、输入/输出摘要、状态、时间戳和失败原因。运行层的时间戳与执行 ID 应在创建任务、分发、执行和验收时记录；规划器只输出判断证据，不伪造运行时间或执行 ID。

## 当前边界

当前任务拆解仍以已注册模板为基础，能力选择依赖注册表、输入规则与经验/Skill 信号；计划级轨迹可以说明模板从哪里来、用了哪些节点，但**不代表系统已经具备对任意自然语言目标的通用语义理解**。显式传入未注册的 `mission_kind` 现在会失败，不再静默改用通用模板。下一步应增加任务意图、约束、交付物的结构化解析与员工能力匹配，并把解析结果、置信度、待澄清问题和规则版本写入同一追溯链。

## 回归测试

运行：

```bash
python -m unittest tests.test_mission_planner_trace -v
```

测试覆盖缺少输入、能力缺口，以及决策轨迹的稳定结构。测试应与真实 CI 运行结果一起判定；仅新增测试文件不代表测试已经通过。


## 主脑协调计划

`build_mission_brain_contract()` 还会生成 `coordination_plan`（`mission.coordination.v1`），把节点状态转换成可审计的下一步动作：

- `request_missing_input`：缺少必需输入，先向任务发起方请求补充。
- `resolve_capability_or_learning_gap`：先补足能力或经验缺口，不直接派发执行。
- `reuse_verified_knowledge_then_validate`：优先复用已验证知识，再按当前项目验收。
- `await_dispatch_authorization`：已经推荐员工，但推荐本身不构成派发授权。
- `prepare_for_authorized_dispatch`：节点具备进入派发审核的条件，仍需运行时完成授权。
- `inspect_evidence_and_reassess`：证据不足或状态不明确，交由主脑重新评估。

协调计划明确输出 `dispatch_authorized=false`，并声明运行时是派发授权责任方。`parallel_safe` 只表达节点是否允许并行，不自动授权并行执行。这样可以区分“主脑建议”“运行时授权”和“实际执行”，避免将员工推荐误记成已派发。

## 已接通的最小运行时闭环

`start_mission()` 将计划交给 `build_mission_run()`，再由 `build_mission_actions()` 逐节点读取协调计划。运行时只有在协调合同版本/所有者/授权位有效、节点状态为 `ready`、无 blocker、存在运行时目标，并且岗位目录明确推荐当前路由中的同一可用 Worker 时，才写入独立的 `mission.dispatch.authorization.v1` 授权证据。规划合同自身的 `dispatch_authorized` 必须保持 `false`；Worker 推荐字段也不会被改写为授权。

真实 Worker handler 收到节点时会同时收到授权证据，并将其写入 `task_queue.submit()` 的任务 payload（`_mission_dispatch_authorization`）。实际派发仍以任务队列返回的 task ID 和 Mission action 的 `task_submitted` 记录为准；刷新阶段按 task ID 读取真实任务状态/结果，拒绝派发和知识复用待办也会保留在运行状态统计中。缺少或格式错误的协调合同会 fail closed，不回退到未受控派发。

本闭环不等于已经实现跨 Worker 的并行锁、租约、取消、崩溃恢复或分布式 exactly-once。当前并行安全标记只用于审计，尚不能单凭它启动并行执行。
