# Skill Replay 真实接线审计（2026-11-19）

## 1. 审计基线

- Repository: `xinghunbuxiu/evo-agent`
- PR: #1（Open，未合并）
- Branch: `automation/mission-learning-evidence-api-first`
- Audited HEAD: `5114ff201898bb1b86998881a614a7baff0810c6`
- Scope: Mission delivery candidate -> Worker result -> Broker staging/replay -> Validator -> immutable Artifact Store.

本文件记录代码调用链审计结果，不代表端到端闭环已经完成。

## 2. 已确认的真实调用链

### 2.1 Worker 返回候选的传输能力存在

`src/workers/javascript_reverse/runtime.py` 中的 reconstruct handler 会从能力执行结果中提取并保留 `skill_candidate`。  
`tests/test_javascript_skill_candidate_transport.py` 覆盖了“能力结果显式带有候选时，Worker handler 能把候选带回任务结果”。

这只证明传输能力，不证明生产能力会生成候选。

### 2.2 当前 JavaScript 能力没有生成 Executable Skill

调用关系：

```text
JavaScriptCapabilityProvider.execute(reconstruct)
  -> domains.javascript.commands.reconstruct_project
  -> JSReconstructor.create_plan
  -> JSReconstructor.execute_plan
  -> TaskResult.data
  -> Worker reconstruct handler
  -> Mission extract_task_snapshot
  -> create_mission_delivery_skill_candidate
```

在审计 HEAD：

- `src/domains/javascript/reconstructor.py::JSReconstructor.execute_plan()` 返回 `success`、`target_dir`、`framework`、组件数量及 `skill_template`。
- 返回对象没有 `skill_candidate`。
- `src/domains/javascript/provider.py::JavaScriptCapabilityProvider.execute()` 只是把重建结果放入 `TaskResult.data`，没有调用模型生成代码。
- `src/admin/model_provider_runtime.py` 已有租户级 OpenAI-compatible 模型调用能力，但当前 JavaScript reconstruct 路径没有调用它来生成可执行候选。

因此，当前生产路径通常进入 `create_mission_delivery_skill_candidate()` 的 Recipe 分支。Recipe 的 `execution_contract.kind` 为 `non_executable_recipe`，并被明确标记为 `replay_eligible=false`。这条路径是安全的，但不是 Executable Skill 自动生成。

### 2.3 Mission 交付门禁已经存在

`src/workers/javascript_reverse/runtime.py::complete_javascript_reverse_promotion_action()` 在沉淀交付经验前检查：

- reconstruct 的 `evaluation_verdict == pass`；
- `evaluation_metrics.has_target_dir is True`；
- reconstruct task evidence ID 存在。

门禁不满足时，Promotion 被阻断，不保存成功交付 Experience，也不生成候选。

`src/admin/knowledge_runtime.py::create_mission_delivery_skill_candidate()` 对交付验收再次检查，并且只接受显式 Executable Candidate 的 `python_run_context` 契约和同步模块级 `run(context)` 入口。没有候选时会保存 Recipe，而不会把自然语言误当 Python。

### 2.4 Broker / Validator Runtime 是可选 API 能力，不是自动 Mission 接线

- `src/admin/server.py` 启动时创建可选 `SkillReplayRuntime`，并将其注入 Mission 相关路由。
- `src/admin/skill_replay_runtime.py::replay_candidate()` 提供候选 staging、Broker Replay、Validator 请求和 Broker promotion 的流程。
- 在审计 HEAD 的 `server.py` 中，没有发现 Mission promotion handler 自动调用 `replay_candidate()` 的调用点。
- 因此，适配器和路由存在，不等于每次 Mission 交付后会自动执行 Replay。

当前自动 Mission 路径只创建本地 Draft/Recipe 候选；Replay 仍是独立的显式 Runtime/API 流程。

## 3. 另一个必须先解决的协议缺口：Replay 输入

当前 `SkillReplayRuntime.replay_candidate()` 构造的 Mission context 只有：

- `tenant_id`
- `mission_run_id`
- `node_id`
- `task_id`

`SkillReplayMissionAdapter`、`build_skill_replay_execution_request_id()` 和当前 v1 Broker Mission context 校验均要求这组精确身份字段。Replay 调用没有传入经过 schema 校验的业务输入对象，也没有把原任务输入、目标文件引用或输出契约作为独立字段传入 Skill 的 `run(context)`。

这意味着当前 Replay 适合验证“某个绑定候选在 Broker 环境中能否被调用并产生结构化输出”，但尚不能证明它能在下一次真实任务中接收新的业务输入并完成同一类业务工作。

不能通过把原始路径或任意任务 payload 直接塞进现有身份 context 来绕过此缺口。需要单独定义版本化、限长、schema 校验、租户绑定和摘要绑定的 Replay Input Contract，并明确哪些输入可进入隔离执行环境。

## 4. Manifest 状态

`docs/BROKER_PUBLISHED_SKILL_MANIFEST_DESIGN.md` 将 Slice B 标记为进行中。当前设计要求 Manifest 摘要与代码摘要一起被 Broker、Validator、Artifact Store、Catalog 和 Mission binding 绑定。

当前 Mission `replay_candidate()` 路径仍使用 v1 candidate staging helper，只提交代码与身份，没有将 Manifest 贯穿 staging -> validation -> publication -> Catalog -> replay。因此不能把 Manifest v2 设计文档或独立 Manifest 校验模块的存在，描述为已完成端到端 Manifest 闭环。

## 5. 当前 CI 事实

审计 HEAD `5114ff201898bb1b86998881a614a7baff0810c6`：

- Admin UI Build run `44536724231`：成功。
- Python Regression run `44536723893`：失败在依赖安装阶段。
- 失败下载项：`pydantic_core-2.50.5` wheel。
- 日志显示下载速度约 738 bytes/s，最终触发 `files.pythonhosted.org` read timeout。
- Regression suite 步骤被跳过，故本次没有 Python 测试通过/失败数量。

此前将 pip timeout 调为 120 秒、retries 调为 10 次，未解决本次 Runner 下载问题。下一步应让 Runner 支持部署级可配置的可信 PyPI 镜像/代理或预热 wheel cache；不应在 workflow 中硬编码某家镜像，也不应跳过依赖或测试。

## 6. 实施顺序与边界

按项目结构治理文档的 Phase 0 / Phase 4 约束，先完成配置、数据、模块职责和真实输入边界审计，再推进接线。

1. 定义 Replay Input Contract：输入 schema、大小上限、允许的文件引用、敏感字段规则、输入摘要和版本兼容。
2. 明确 Skill Manifest v2 与 Replay Input Contract 的关系：Manifest 声明输入/输出 schema；Mission 提供符合 schema 的输入；Broker 对输入摘要和绑定进行签名。
3. 确定 Executable Skill 生成责任归属。模型生成只产生 Draft；提示词、输出 JSON、AST/Manifest 校验、失败降级和模型来源证据均需测试。
4. 将真实 Mission Promotion 接入 Replay Runtime；先持久化 candidate binding 和幂等请求 ID，再产生 Broker side effect。
5. 只有 Broker 执行成功、独立 Validator 对精确代码/Manifest/输入/输出证据签名通过，才允许发布不可变 Artifact。
6. 业务交付验收仍由 Mission 的业务验收流程决定；不得把 Replay 或 Validator 通过等同于下一次业务任务成功。

## 7. 禁止的捷径

- 不把 Recipe 改名为 Executable Skill。
- 不在 Admin/Mission 进程执行候选代码。
- 不因模型生成成功就赋予 verified/cloud trust。
- 不让 Worker 自己签发独立 Validator 证明。
- 不把 Broker 执行成功、Validator 通过、业务验收通过合并成一个布尔值。
- 不把任务路径、任意文件系统路径或原始敏感 payload 混入当前身份 context。
- 不新增没有真实调用方的并行 Runtime、Manager、Store 或协议层。
- 不以 mock 的 Mission -> Broker 调用测试替代真实 Socket 集成证据。
