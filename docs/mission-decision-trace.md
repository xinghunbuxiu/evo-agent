# Mission 分析决策追溯规范

## 目标

每个 mission 节点都应回答三个可审计问题：

1. **系统做了什么判断？** 例如缺少输入、复用现有能力、经验不足或能力缺口。
2. **判断依据是什么？** 能力注册表命中项、必需输入缺失代码、经验/已验证技能计数。
3. **下一步为什么这样做？** 由状态、缺口类型、验收条件和建议动作共同解释。

追溯记录是规则与证据的结构化摘要，不是模型的隐藏思维链；不得把密钥、令牌或不必要的原始敏感内容写入日志。

## 当前实现

`MissionPlanner.plan()` 的每个节点现在会返回 `decision_trace`，每条记录包括：

- `step`：阶段名称，当前为 `input_validation`、`capability_match`、`knowledge_check`、`status_decision`。
- `rule_id`：稳定的规则标识，可用于定位代码、筛选日志和建立回归测试。
- `result`：该规则的结果。
- `evidence`：可机器读取的证据，例如 blocker code、能力 ID、经验/技能计数、最终缺口类型。

当前规则 ID：

| Rule ID | 含义 |
| --- | --- |
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

目前的 mission kind 选择主要依赖显式 `mission_kind`、匹配的 `work_type_id` 和模板回退规则；节点拆解来自模板，能力选择依赖注册表、输入规则与经验/技能信号。因此，`decision_trace` 能解释当前规则为何得出结果，但**不能证明系统已经具备对任意自然语言目标的通用语义理解**。后续应增加任务意图/约束/交付物的结构化解析层，并把解析字段、置信度、待澄清问题及规则版本写入同一追溯链。

## 回归测试

运行：

```bash
python -m unittest tests.test_mission_planner_trace -v
```

测试覆盖缺少输入、能力缺口，以及决策轨迹的稳定结构。测试应与真实 CI 运行结果一起判定；仅新增测试文件不代表测试已经通过。
