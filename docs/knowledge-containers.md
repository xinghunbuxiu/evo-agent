# Knowledge Containers

## Why

Evo 现在不再把知识存储只理解成单一的 Gitee 仓库，而是统一看成一组可组合的“知识容器”：

- 本地私有层
- 平台共享层
- Git 仓库层
- 企业私有仓层

这样后续新增 Gitee、GitLab、企业自建 Git、对象存储时，主流程不需要重写，只是增加新的容器驱动。

## Current Container Model

当前每个租户会被解析成这些容器：

1. `local:skills`
2. `local:experiences`
3. `local:strategies`
4. `platform_shared`
5. `git:*` 或 `config:*`

其中：

- `git:*` 表示租户已经初始化自己的 Git knowledge 仓库
- `config:*` 表示还没初始化租户仓时，回落到平台默认仓配置

## Main Rule

主流程只关心两件事：

1. 这次要写入/读取哪个 purpose
2. 当前租户对应该 purpose 的首选容器是什么

例如：

- 技能同步看 `skills`
- 经验导出看 `experiences`
- 成长报告导出看 `reports`

## Why This Helps

这层抽象能解决三个问题：

- 不把 `domains` 当成固定业务目录
- 不把 `gitee` 写死成唯一知识容器
- 不把“企业不共享”和“平台共享”做成互斥死逻辑

## Next

下一步可以继续做：

1. 给 `git:*` 增加 GitLab provider
2. 给企业私有层增加独立 `enterprise_repo` 容器
3. 给大体积日志/样本增加对象存储容器
4. 把容器选择策略接入自治学习源优先级

## Enterprise Index

企业知识仓要真正进入自治学习主线，不能只“配置 repo”，还需要提供可扫描的知识索引。

建议统一使用：

- `evo/index.json`

索引格式说明见：

- [evo-index-schema.md](evo-index-schema.md)
