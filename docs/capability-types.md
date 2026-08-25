# Capability Types

Evo 后续不应该按“每个知识点一个 plugin”去扩展，而应该按下面三层来长：

1. `plugin`
用于接入能力核，例如 `crawler`、`automation`、`javascript_reverse`

2. `capability_type`
用于定义知识归属的大类，例如：

- `javascript_reverse`
- `android_reverse`
- `pc_reverse`
- `crawler`
- `automation`
- `document_parse`

3. `skill / experience / strategy`
用于持续增长的具体知识条目

## Main Rule

- `plugin` 是少量稳定的能力入口
- `capability_type` 是知识组织和自治决策的主语义
- `skill / experience / strategy` 才是大量增长的部分

## Why

这样做能避免两个问题：

1. 新增一个知识点就要新增一个 plugin
2. `domains` 被误用成固定业务边界

## Current Migration

当前代码已经开始兼容迁移：

- 旧的 `domain` 仍保留，避免打断现有 JS 主线
- 新的 `capability_type` 会逐步进入 capability、tenant、plugin、knowledge
- 后续新增能力优先按 `capability_type` 接入，而不是先扩 `domains/*`
