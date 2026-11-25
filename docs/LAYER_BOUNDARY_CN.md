# Evo Agent 分层边界

本文件保留为简要入口。完整、权威的目录归属、依赖方向、数据所有权、配置规则和渐进迁移方案见：

[项目结构与工程约束](PROJECT_STRUCTURE_AND_ENGINEERING_RULES_CN.md)

## 当前目录职责

- `src/core/`：跨领域模型、协议、共享算法和稳定接口。
- `src/admin/`：Admin 应用用例、编排和运行时适配。
- `src/admin/routes/`：HTTP 请求/响应适配；不得实现完整业务流程。
- `src/domains/`：内置专业能力。
- `src/workers/`：工种 Worker handler 与注册 manifest。
- `executors/`：外部平台、浏览器、CLI、设备和脚本适配器。
- `admin-ui/`：通过 Admin API 操作，不持有权威业务状态。
- `plugins/`：遵守公开协议的可选扩展。

## 不可跨越的职责边界

1. Mission 是任务目标、拆解、依赖、授权、验收和重规划的唯一决策者。
2. Talent Center 是 Role、Employee、Worker 生命周期的权威管理者。
3. TaskQueue 是队列执行状态的权威来源。
4. Broker 是不可信 Skill 的执行授权和隔离边界。
5. Validator 独立作出策略验证判定并签名。
6. Artifact Store 保存 Broker 管理的不可变 Skill 产物。
7. Experience 记录有来源的结果，不授予执行权限。

## 重构约束

不做一次性大搬迁。每次迁移一个完整职责单元，先补 characterization/contract tests，再迁移调用方，最后删除旧入口。禁止双写、平行状态机、重复 Runtime 和仅为演示而存在的生产分支。
