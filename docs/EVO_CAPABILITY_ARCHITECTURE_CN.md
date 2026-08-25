# Evo 可插拔能力架构

## 定位

`evo` 的目标不是固定流程编排器，而是一个可自主决策、可持续成长的智能分析内核。

为了支撑未来：

- 只先做 `JavaScript`，后续再扩 `Android / PC`
- 企业可替换分析器、评估器、成长逻辑
- 核心仍保持稳定

系统不再把 `domains/` 视为写死边界，而是把它们看作：

`builtin capability providers`

也就是内置能力插件。

## 三层模型

### 1. Core Kernel

核心内核必须稳定，不能随着单个领域或企业需求被反复改写。

职责：

- Admin HTTP API 与统一任务模型
- 能力注册与发现
- 决策框架
- 成长反馈框架
- 多租户与存储边界

### 2. Capability Providers

能力提供者只回答：

- 我能处理什么任务
- 我怎么执行
- 我输出什么结果

能力提供者可以是：

- 内置 JavaScript 逆向能力
- 后续 Android / PC 能力
- 企业定制能力

### 3. Growth Layer

成长层负责：

- 经验记录
- 经验筛选
- 策略提升
- 技能演化
- 反馈回灌

它不绑定某个领域，而是为所有能力提供者服务。

## 当前落地

本次已引入：

- `src/core/capabilities.py`
  - `CapabilityDescriptor`
  - `TaskContext`
  - `TaskResult`
  - `CapabilityProvider`
  - `CapabilityRegistry`

- `src/domains/javascript/provider.py`
  - 将现有 JavaScript 逻辑包装为 `builtin.javascript`

- `src/domains/__init__.py`
  - 提供内置能力注册入口

- `src/core/decision.py`
  - 提供最小可用 `DecisionEngine`
  - 基于任务类型、偏好标签、历史经验自动选择 capability

- `src/core/orchestration.py`
  - 提供 `StrategyProvider` / `EvaluatorProvider` 协议
  - 支撑“能力选择之后的策略选择”和“统一结果评估”

## 现阶段语义调整

保留 `src/domains/` 目录，但语义改为：

`内置能力集合`

而不是：

`系统只能存在这些固定领域`

后续推荐逐步演化到：

```text
src/
  core/
    cognition/
    growth/
    infra/
    capabilities.py
  builtin/
    javascript/
    android/
    pc/
  extensions/
    enterprise_x/
```

## 接入协议

一个能力模块只要实现 `CapabilityProvider`，就可以被内核接入。

最小要求：

1. 提供 `descriptor`
2. 实现 `execute(context)`
3. 声明支持的 `task_type`

## 任务流

当前统一任务上下文：

`TaskContext`

包含：

- `workspace`
- `tenant_id`
- `task_type`
- `input_path`
- `source_dir`
- `parameters`
- `signals`
- `history`

统一结果模型：

`TaskResult`

包含：

- `success`
- `capability_id`
- `task_type`
- `summary`
- `confidence`
- `data`
- `feedback`

这样未来决策层、成长层、企业定制层都可以围绕统一模型工作，而不是直接耦合具体目录实现。

## 最小自主决策

当前 `DecisionEngine` 已经承担最小自主能力：

- 显式指定 capability 时，尊重人工选择
- 未指定时，根据 `task_type` 找候选 capability
- 根据 `preferred_tags`、`signals`、最近经验进行打分
- 选出当前最优能力并执行
- 在选中 capability 后继续选择 strategy
- 执行完成后统一跑 evaluator
- 将候选评分与最终选择写入 `TaskResult.feedback.decision`
- `reconstruct` 任务也走同一套决策链
- 当未显式提供 `analysis_result` 时，能力可先自行分析再继续重构

## 当前经验反馈增强

当前 JavaScript 内置能力写入经验时，已经开始记录：

- `capability_id`
- 标准化后的 `task_type`
- `frameworks / libraries / patterns`
- 指纹生成数量或重构目标目录
- 本次 `decision` 摘要

这让经验开始具备“参与下一次选择”的条件，而不再只是静态日志。

此外，`DecisionEngine` 现在还会额外写入一层编排经验：

- 选中了哪个 capability
- 选中了哪条 strategy
- evaluator 的评分与 verdict
- 本次执行反馈摘要

后续决策在给 capability 与 strategy 打分时，会优先参考这些带评估结果的历史经验。

## 当前编排层能力

当前内置 JavaScript 已经具备：

- `builtin.javascript.analyze.default`
- `builtin.javascript.reconstruct.scaffold`
- `builtin.javascript.evaluator`

因此系统现在已经不是：

`只选一个 capability`

而是：

`先选 capability -> 再选 strategy -> 执行 -> 统一评估`

这意味着系统已经从：

`调用方手工指定 javascript 模块`

开始转向：

`内核基于上下文和经验自动选择能力`

## 下一步建议

### 第一阶段

- 保持 JavaScript 为唯一正式能力
- 让所有 analyze/reconstruct 入口都改为走 `CapabilityRegistry`
- 补充 `DecisionEngine`，让能力选择不再写死在调用方

### 第二阶段

- 把经验写入从“日志记录”升级为“可参与策略选择”
- 引入 `EvaluatorProvider` 与 `GrowthProvider` 协议
- 支持企业替换评估与成长逻辑

### 第三阶段

- 引入插件加载机制
- 支持从配置或扩展目录动态加载 provider
- 将 Android / PC 也按 provider 模式接入

当前这一步已经开始落地，详见：

- [PLUGIN_SYSTEM_CN.md](PLUGIN_SYSTEM_CN.md)

## 核心原则

`evo` 的核心不是固定流程，而是稳定内核 + 可插拔能力 + 可进化反馈。
