# Skill Replay / Broker Artifact Store 接线审计（2026-11-20）

## 1. 审计基线

- Repository: `xinghunbuxiu/evo-agent`
- PR: #1（Open，未合并）
- Branch: `automation/mission-learning-evidence-api-first`
- Audited HEAD: `5a0cb2a2c3ec4a2727db684ecbe81a5ed3e419ec` (Broker v2 execution implementation is the next commit; see the follow-up section below)
- Scope: Mission candidate -> Broker stage/replay -> independent Validator -> immutable Artifact Store -> Catalog/reuse.
- CI at audited HEAD:
  - Python regression run `44656030826`: success.
  - Admin UI Build run `44656030704`: success.

本审计区分“模块存在”“API 可调用”和“生产链路已端到端贯通”。只有当前 HEAD 的实际调用和协议绑定才算完成。

## 2. Mission 入口与授权边界

当前提供显式 API：

`POST /api/missions/{mission_run_id}/skills/{skill_id}/replay`

路由执行以下检查后才调用 Replay Runtime：

- 必须存在登录会话；
- Mission run 必须存在且租户授权通过；
- 仅 tenant_admin / member 可发起；
- node_id 必须属于该 Mission；
- 请求只允许 `node_id`，并要求规范 UUID `Idempotency-Key`；
- 先在 Mission action 中持久化请求身份，再产生 Broker side effect；
- 重复请求返回既有结果或冲突，不盲目再次执行。

因此，当前是“经授权的显式 Replay API”，不是每次 Mission 交付完成后自动触发 Replay。普通 Mission 在 Replay Runtime 未配置时仍可执行。

## 3. Executable Candidate 的生产来源

当前 JavaScript 生产链路：

```text
JavaScriptCapabilityProvider.execute(reconstruct)
  -> reconstruct_project
  -> JSReconstructor.create_plan
  -> JSReconstructor.execute_plan
  -> TaskResult.data
  -> Worker reconstruct handler
  -> Mission task snapshot
  -> create_mission_delivery_skill_candidate
```

在本审计 HEAD：

- `JSReconstructor.execute_plan()` 返回重建结果、目标目录、框架、组件数和 `skill_template`，没有生成 `skill_candidate`。
- `JavaScriptCapabilityProvider` 传递重建结果，不调用模型生成 Python Skill。
- Worker 的候选传输能力只说明上游显式返回候选时可以透传，不代表当前 reconstruct 能力会生成候选。
- 因此，正常生产路径没有 Executable Candidate 时会沉淀为 `non_executable_recipe`，不能进入 Broker。
- 已有显式候选创建入口会做 Python AST/入口契约检查并绑定来源，但该入口本身不调用 LLM、不执行代码、不提升信任等级。

结论：当前不能宣称系统已经自动把 Mission 经验生成成可执行 Skill。模型生成仍是独立待实现能力；生成结果只能是 Draft，必须经过静态检查、Broker Replay 和独立 Validator。

## 4. Broker 与 Artifact Store 当前边界

### 已实现

- Broker 有独立 Unix Socket 服务和请求协议；Admin/Mission 不在本进程执行候选代码。
- Candidate Stage 支持 v1 和 Manifest v2 两种请求形状。
- v2 Stage 会规范化 Manifest，核对 Skill ID/version，重算 canonical Manifest SHA-256，并把 Manifest 与代码摘要一起写入 Broker 自有候选存储。
- Stage 回执由 Broker 签名；客户端校验回执身份和签名。
- Artifact Store 使用 Broker 私有目录、原子 create-once 发布和 readback 校验，避免覆盖已发布内容。
- Broker Catalog 不把 Draft 候选当成已发布 Artifact。
- 最新 HEAD 增加了 Manifest-bearing Candidate 的 fail-closed 测试：在当前 v2 全链路未完成时，Replay 必须在回调、Stage 和执行副作用前拒绝该候选。

### 尚未贯通

当前 Mission `replay_candidate()` 对带 `parameters.manifest` 的候选明确抛出配置错误。原因是它后续仍走 v1 binding / execution / Validator / promotion 路径。

Validator 当前仍只接受：

- `mission.skill-validation-request.v1`；
- `mission.skill-replay-binding.v1`；
- 以 tenant、Skill ID/version、code digest、trust level 为键的策略；
- 不包含 `manifest_sha256` 的签名 attestation。

因此，虽然 Candidate Stage v2 和 Manifest v2 binding helper 已存在，仍不能把它们描述为完整的 Manifest v2 Replay 或发布链路。Artifact schema 常量的版本号也不能替代端到端 digest 验证。

## 5. Replay Input Contract 缺口

当前 Mission Replay context 主要承载身份字段：

- tenant_id
- mission_run_id
- node_id
- task_id

调用给 Broker 的 input_summary 是说明性文本，不是经过 Manifest input_schema 校验的业务输入对象。当前不能证明已发布 Skill 能在下一次 Mission 中接收受约束的新输入并完成同类业务工作。

不能把任意任务 payload、绝对路径或原始敏感数据塞进身份 context。必须单独定义版本化、限长、租户绑定、摘要绑定的 Replay Input Contract，并定义允许传入的结构化值与受控文件引用。

## 6. 下一阶段实施顺序

按依赖关系推进，不能提前移除 Mission 当前的 Manifest fail-closed：

1. **Broker v2 execution binding**：独立请求/响应 schema；执行请求、Broker 回执和幂等请求身份同时绑定精确 code digest + canonical Manifest digest；执行前从 Broker 私有 v2 candidate store 加载并重新计算双摘要。v1 保持原样。
2. **Validator v2**：增加独立 v2 request/binding；策略键和签名 attestation 同时绑定 code 与 Manifest digest；验证 v2 Broker execution receipt。v1 保持独立，不接受混合字段。
3. **Artifact Store v2 publication**：验证 Validator v2 签名和精确双摘要；create-once 保存 code + canonical Manifest + 两个摘要；readback 对两者重新计算。
4. **Catalog v2**：只返回经过签名的受限 Manifest 元数据和摘要；不泄漏代码、Mission 原始上下文或内部路径。
5. **Mission v2 Replay**：先持久化 v2 binding 和所有确定性 request ID，再触发副作用；恢复流程也必须重新核验每份签名与摘要。
6. **Replay Input Contract**：Manifest 声明输入/输出 schema，Mission 输入经 schema、大小、租户和文件引用规则校验后进入 Broker；输入摘要加入执行证据与 Validator attestation。
7. **真实 Socket 集成测试**：覆盖 Stage -> Execute -> Validator -> Promotion -> Catalog -> 新 Mission Replay；不能只用 mock 适配器证明端到端。

## 7. 不可突破的验收边界

- Recipe 永远不是 Executable Skill。
- LLM 生成成功不等于 Skill 验证通过。
- Broker 执行成功不等于 Validator 通过。
- Validator 通过不等于业务交付验收通过。
- 只有绑定精确 code + Manifest + Mission/input 身份的独立 Validator 证明，才可用于不可变 Artifact 发布。
- 缺少配置、签名、证据、摘要或状态不确定时 fail closed；普通 Mission 不因此被阻断。
- 未完成真实调用链和真实 Socket 集成测试前，不开启自动 Catalog 匹配或自动 Skill 复用。



## 8. Broker Manifest v2 execution follow-up

The next implementation slice adds an independent Broker execution request/response pair:

- Request schema: `mission.sandbox-broker-request.v4`.
- Response schema: `mission.sandbox-broker-response.v5`.
- Binding schema: `mission.skill-replay-binding.v2`, with both `content_sha256` and `manifest_sha256`.
- Artifact resolution schema: `mission.skill-artifact-resolution.v2`.
- Broker execution resolves v2 candidates only through `load_candidate_manifest()`; the legacy v1 binding still resolves only through `load_for_binding()`.
- The signed response binds the exact v2 binding and both artifact digests. The v1 request/response path remains unchanged.

This slice does not enable Manifest-bearing Mission Replay yet. Validator v2, v2 publication/readback, recovery verification, and Mission runtime wiring remain required before the existing fail-closed guard can be removed.
