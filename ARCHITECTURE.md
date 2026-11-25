# Evo Agent 技术架构

> 当前项目结构、代码归属、配置治理、禁止硬编码、反堆叠和真实验收规则，以 [项目结构与工程约束](docs/PROJECT_STRUCTURE_AND_ENGINEERING_RULES_CN.md) 为准。

## 产品主线

Evo 是以 Mission 为单一任务决策中心的持续学习型智能体平台。主流程：

`目标理解 -> 知识检索 -> Mission 计划与依赖 -> Talent Center 人员安排 -> 授权与 Worker Claim -> TaskQueue 执行 -> 结果与证据 -> 独立验证/业务验收 -> 复盘 -> Experience / Skill`

Mission 负责任务目标、拆解、依赖、执行授权、验收与重规划；Talent Center 负责 Role、Employee、Worker 的生命周期和成长；Worker 执行受授权任务并提交结果和证据。

## 技术边界

| 层 | 代码位置 | 职责 |
|---|---|---|
| Core Kernel | `src/core/` | 稳定领域模型、协议、共享算法和基础接口 |
| Admin Application | `src/admin/` | 用例编排、应用服务、权限策略适配 |
| HTTP API | `src/admin/routes/` | 请求/响应适配，不持有业务规则 |
| Built-in Domains | `src/domains/` | 专业领域能力 |
| Workers | `src/workers/` | 岗位/工种任务处理器 |
| Executors | `executors/` | 外部平台、浏览器、CLI、设备等适配器 |
| Admin UI | `admin-ui/` | 管理界面，通过 Admin API 工作 |
| Extensions | `plugins/` | 可选扩展 |

## Skill 安全边界

Recipe（自然语言经验）与 Executable Skill（可执行代码）是不同资产。可执行 Skill 必须经过 Broker 隔离执行；Validator 独立验收并签名；Artifact Store 保存不可变发布产物。Broker 执行成功、Validator 通过、业务验收通过是三个不同事实，不得合并表达。

Broker/Validator 可选配置缺失时，普通 Mission 仍应正常工作；Skill Replay 必须明确不可用，不得模拟成功或绕过隔离执行。

## 运行入口

- Admin 应用工厂：`admin.server:create_app`
- Python 包路径：`src/`
- 前端：`admin-ui/`
- 配置示例：`.env.example` 与受版本控制的非敏感配置
- 运行数据：工作区与部署指定数据目录，不属于源代码

实际启动、部署、环境变量和迁移说明请以 [START.md](START.md)、[ADMIN_README.md](ADMIN_README.md) 及 [工程约束文档](docs/PROJECT_STRUCTURE_AND_ENGINEERING_RULES_CN.md) 为准。

## 重要说明

仓库正在进行结构治理。文档中的目标结构是渐进迁移方向，不代表所有目标目录已经实现。未完成的迁移、尚未接通的调用链和未执行的测试必须明确标注，不能将设计方案描述为已交付能力。
