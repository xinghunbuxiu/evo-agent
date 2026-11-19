# 项目结构、代码归属与工程约束

> 状态：结构治理基线（2026-11-19）
> 适用范围：整个 evo-agent 仓库；新代码与重构代码必须遵守。
> 本文是目录归属和工程约束的唯一入口。具体业务协议仍以各模块契约文档为准。

## 1. 治理目标

本轮先治理结构，再继续扩展功能。目标不是为了“目录好看”而大规模搬文件，而是建立清晰的职责归属、唯一数据源和可验证的真实调用链。

必须满足：

1. 一个业务决策只有一个权威所有者。
2. 一个持久化事实只有一个权威写入者；其他模块通过接口读取或提交命令。
3. 配置、路径、端点、阈值、租户默认值和运行时策略由配置/注册表提供，不散落在业务代码中。
4. 运行时代码必须走真实服务和真实契约；示例、探针、演示数据不能冒充产品实现。
5. 新增抽象必须解决已存在的重复或明确的扩展需求；不能为了包装现有函数再增加一层 Runtime/Manager/Facade。
6. 重构必须保持外部 API、持久化 schema 和安全边界；变更契约必须有迁移说明与回归测试。

## 2. 当前结构审计基线

以当前分支 HEAD 为准，仓库约 936 个 tracked files。主要目录包括：

- `src/admin/`：Admin API、应用编排、多个业务 Runtime。
- `src/core/`：共享领域能力、任务队列、组织模型、Broker/Skill 安全执行能力。
- `src/domains/`：内置专业领域能力。
- `src/workers/`：可注册的工种 Worker 实现。
- `executors/`：外部执行器与平台适配实现。
- `admin-ui/`：管理端前端。
- `plugins/`：可插拔扩展。
- `tests/`：回归测试。
- `docs/`、`openSpec/`：架构、契约和变更规格。

审计发现的结构问题：

- `src/admin/server.py` 约 2,659 行，同时承担大量导入、依赖组装、路由注册、业务函数和后台任务，已经超出 Composition Root 的合理职责。
- `src/admin/routes/missions.py` 约 1,891 行，Mission 规划、运行、Replay、恢复等 API 逻辑聚集在一个路由文件。
- `src/admin/mission_runtime.py` 约 1,297 行，持久化、并发锁、恢复和运行态辅助逻辑混合。
- `src/admin/mission_execution_runtime.py` 约 1,290 行，多个执行/学习阶段职责需要进一步划分。
- `src/admin/runtime_state.py` 约 1,106 行，跨业务状态模型集中在一个文件。
- `executors/toutiao/data/` 下存在约 544 个已跟踪数据文件，主要为草稿样本；运行数据、演示数据和正式配置的仓库归属需要分开。
- `executors/toutiao/README.md` 明确称当前为执行器骨架；`browser_backend.py` 的发布辅助仅打开编辑页、尝试填入内容并截图，返回 `browser_assisted`，不能视为平台已真实发布。此能力必须明确标为人工辅助/实验能力，不能作为真实发布成功证据。
- 根目录 `.config/evo.json` 与 `src/.config/evo.json` 同时存在。Admin 默认工作区是仓库根目录，分布式配置由 `src/core/config.py` 的 `ConfigLoader` 加载；`src/.config/` 暂按历史副本处理，在确认所有启动入口和工作区调用后再决定迁移/删除。
- `ARCHITECTURE.md` 中的目录、存储和运行方式描述与当前实现不完全一致，不能继续作为当前代码结构的准确说明。
- 仓库中存在被跟踪的本地认证数据文件 `.local_admin_users.json`；本地账号数据不应作为产品默认数据提交。

以上是结构事实，不代表应一次性移动或删除所有文件。运行数据先分类、备份策略和迁移策略确认后再清理。

## 3. 目录归属与职责边界

### 3.1 现有目录的正式归属

| 目录 | 唯一职责 | 允许依赖 | 禁止承担 |
|---|---|---|---|
| `src/core/` | 跨业务领域的稳定模型、协议、通用算法和接口 | 标准库、明确声明的基础依赖 | FastAPI 路由、具体业务流程、Admin 全局状态 |
| `src/admin/` | Admin 应用服务、用例编排、权限策略适配、HTTP 接入 | core、workers 的公开契约、infrastructure adapter | 领域算法重复实现、直接拼接大量业务逻辑的总控文件 |
| `src/admin/routes/` | HTTP 请求解析、认证授权调用、参数校验、应用服务调用和响应映射 | admin application services | 直接操作底层文件/数据库、实现完整业务流程 |
| `src/domains/` | 内置专业能力实现（例如 JavaScript、Android、PC） | core contracts | Mission 决策、租户授权、平台级状态 |
| `src/workers/` | 岗位/工种 Worker handler、manifest 和任务执行入口 | core contracts、domains、公开工具接口 | 自行改写 Mission 依赖图、跳过 Mission 授权 |
| `executors/` | 具体外部平台、浏览器、CLI、设备和脚本适配器 | 公开执行协议 | 组织管理、Mission 决策、Experience 晋升 |
| `plugins/` | 可选扩展及其 manifest | 插件 SDK / core contracts | 修改核心全局状态或绕过租户策略 |
| `admin-ui/` | 展示和交互 | Admin HTTP API | 自行推断业务规则或保存权威业务状态 |
| `tests/` | 契约、单元、集成、端到端和安全回归 | 被测公开接口 | 用测试夹具替代生产默认配置 |
| `docs/`、`openSpec/` | 架构决策、协议、变更范围和验收记录 | 全部模块的公开事实 | 与实现不一致的“愿景即完成”描述 |

### 3.2 核心业务权责

| 业务对象 | 权威所有者 | 其他模块的边界 |
|---|---|---|
| Mission 目标、拆解、依赖、验收和重规划 | Mission application/runtime | Worker、Skill、模型不能自行改写 |
| Role、Employee、Worker 生命周期 | Organization / Talent Center | Mission 提出人员需求，不自行做人事管理 |
| Worker 执行授权与任务占用 | Mission dispatch + lease contract | Planner 推荐不等于授权；handler 不自行抢占 |
| 任务队列状态 | TaskQueue | Mission 读取队列事实，不复制一份并行状态机 |
| Skill 执行 | Skill Executor / Broker | Recipe 不是可执行代码；Broker 不决定业务目标 |
| 不可信代码隔离和执行策略 | Broker | Admin 不得绕过 Broker 直接执行候选代码 |
| Validator 判定和签名证明 | 独立 Validator | Broker/Skill 作者不能代替 Validator 自证 |
| 不可变 Skill Artifact | Broker-owned Artifact Store | Tenant workspace 不拥有发布写权限 |
| Experience / Reflection | Learning / Experience application | 仅记录有来源的事实，不授予执行权限 |
| Tenant identity / authorization | Tenant access policy | 各路由不得自建不一致的租户判断 |
| 配置和密钥 | Settings / deployment environment | 业务模块不得自行寻找配置文件或读取散落环境变量 |

### 3.3 关键调用链

产品主链：

`HTTP/API -> Application Use Case -> Mission -> Staffing/Authorization -> TaskQueue -> Worker Handler -> Result/Evidence -> Verification -> Experience`

可选 Skill Replay 子链：

`Mission -> Skill Replay Application -> Broker Transport -> Broker Policy -> Isolated Runner -> Broker Evidence -> Validator -> Immutable Artifact Store`

规则：

- 普通 Mission 不依赖 Broker 必须在线。
- Skill Replay 未配置时必须明确不可用，不能模拟成功。
- Broker 执行成功不等于 Validator 通过。
- Validator 通过不等于业务验收通过。
- Artifact 发布不等于 Planner 自动采用。
- Catalog 发现不授予执行权限。

## 4. 目标结构（渐进迁移，不一次性搬家）

当前代码先保持可运行，通过新增边界和逐步迁移实现以下目标：

```text
src/
  core/                       # 领域模型、协议、稳定接口、通用算法
  admin/
    api/                      # HTTP 路由与请求/响应 schema（由 routes 渐进迁入）
    application/
      mission/                # Mission 用例与协调
      workforce/              # Role / Employee / Worker 用例
      learning/                # Experience / Reflection / promotion 用例
      skill/                   # Recipe / Replay / publication 用例
      tenant/                  # 租户授权用例
    bootstrap/                 # Composition Root：依赖装配、生命周期
    infrastructure/
      persistence/             # 文件、SQL、证据存储适配器
      queue/                   # TaskQueue 适配
      providers/               # AI/Git/Search 等外部服务适配
      execution/               # Broker/Validator transport 适配
  domains/                     # 专业领域能力
  workers/                     # 工种 handler 与注册 manifest
  project_caps/                # 项目能力包（若继续保留，需明确与 domains/plugins 的差别）
  work_types/                  # 工种定义与运行路由（逐步收敛到单一注册入口）
```

说明：

- 这是目标归属，不是要求立即创建空目录或移动全部文件。
- 每次只迁移一个完整职责单元；迁移前先写清旧入口、新入口、依赖方向、兼容期限和回滚方式。
- 禁止仅移动文件但保留循环导入、双重实现和双重状态。
- `server.py` 最终只负责创建应用、加载 Settings、组装依赖、注册路由和生命周期钩子。

## 5. 禁止硬编码规则

### 5.1 必须配置化的内容

- 项目根目录、工作区根目录、运行数据根目录、临时目录、Artifact Store 根目录。
- HTTP/Socket 地址、端口、超时、重试次数、连接池参数。
- AI Provider 的 base URL、模型、API Key、优先级。
- Gitee/GitHub 等外部平台地址、仓库 owner/repo/branch。
- CORS origins、回调 URL、Cookie、安全开关。
- Worker/Plugin/Executor 搜索目录和启用状态。
- 业务阈值、自动晋升阈值、采样数量、保留期限、并发限制。
- 租户默认值、默认角色、默认工种与默认执行路由。

### 5.2 配置读取规则

1. 统一由 Settings/Config Provider 读取和验证配置。
2. 配置优先级统一为：显式启动参数（如有） > 环境变量/Secret Provider > 指定配置文件 > 安全默认值。
3. 业务模块接收已解析的配置对象，不在函数内部散落 `os.getenv`。
4. 路径统一从 `PathConfig` 或依赖注入取得；禁止业务代码使用 `Path(__file__).parents[n]` 推导项目根目录。
5. 生产环境缺少必需密钥时启动失败；禁止使用可预测默认密钥、默认密码、默认盐值。
6. 仅协议固定值（schema id、算法标识、不可变状态枚举）允许作为代码常量；业务策略值不得伪装成协议常量。

### 5.3 当前已识别的整改项

- `src/admin/database.py` 中 `PASSWORD_SALT` 使用固定默认值 `evo-salt-2024`：必须改为安全的凭据配置与兼容迁移，不能简单换盐导致现有账号无法登录。
- `src/admin/server.py`、`src/admin/worker.py`、`src/admin/database.py` 多处通过 `Path(__file__).resolve().parents[2]` 推导仓库路径：迁移到统一 PathConfig。
- `src/admin/server.py` 中 CORS、环境文件加载、workspace 初始化和启动装配需要集中到 bootstrap/settings。
- 根目录 `.config/evo.json` 与 `src/.config/evo.json` 必须确定唯一权威配置；另一份只能作为迁移兼容或删除，不能双读双写。
- `.local_admin_users.json` 属于本地运行数据，不应跟随代码发布；先迁移已有数据和测试夹具，再从版本控制移除。
- `executors/toutiao/data/` 需要区分正式业务数据、开发样本和运行生成草稿；运行生成内容必须进入工作区/持久化存储，不得持续堆积在代码仓库。

## 6. 禁止代码堆叠与重复实现

新增代码前必须检查：

- 是否已有同职责模块、接口、schema 或 helper。
- 是否已有该状态的权威持久化来源。
- 是否可以扩展现有契约，而不是创建平行 Runtime/Manager/Service。
- 新模块是否有独立生命周期、独立数据所有权或独立安全边界。

禁止：

- 同一业务逻辑在 server、route、runtime、worker 中各实现一份。
- 同一业务状态同时写入 Mission JSON、TaskQueue、Experience 和另一个临时 registry，并且没有明确事实来源。
- 为一个函数机械增加 Facade/Manager/Coordinator/Runtime 包装层。
- 仅为了通过单测而增加生产 fallback、兼容猜测或吞异常逻辑。
- 以复制旧文件的方式“重构”，却不删除旧实现和旧入口。
- 使用动态 import、字符串分发或大 switch 隐藏本应由 Registry/Protocol 表达的扩展点。
- 把未来可能需要的功能提前实现为没有真实调用方的空模块。

每个模块必须有：单一职责、公开输入输出、数据所有权、允许依赖、失败语义和测试边界。

## 7. 禁止 Demo 式生产实现

生产实现不得：

- 返回写死的成功响应或伪造执行结果。
- 用固定用户、固定租户、固定 Skill、固定路径、固定样本冒充动态业务。
- 用内存字典冒充需要持久化的生产状态。
- 用 mock/stub 的测试结果宣称真实外部服务已接通。
- 将示例流程、探针脚本、演示页面作为正式业务入口。
- 将“模块存在”“接口返回 200”“单元测试通过”描述为端到端闭环完成。

允许的 Demo / Fixture：

- 必须放在 `examples/`、`tests/fixtures/` 或明确的 demo profile。
- 必须显式标记 `demo` / `fixture`，不得被生产启动路径自动加载。
- 测试可 mock 外部服务，但至少要有契约测试验证真实请求/响应格式；关键执行链必须有集成测试。
- 任何跳过项必须在 CI 输出中显示为 skipped，不得计为 passed。

## 8. 文件规模与拆分规则

文件行数不是唯一指标，但达到以下任一条件必须进行职责审查：

- 单文件超过 800 行：必须提交拆分评估，说明暂不拆分的理由。
- 单文件超过 1,200 行：默认要求拆分，除非该文件是生成文件或有明确不可拆理由。
- 一个函数超过 80 行：检查是否混合校验、编排、持久化和响应构造。
- 一个模块导入超过 30 个本项目模块：检查是否承担了过多 Composition Root 职责。

拆分要求：

- 按业务用例/状态所有权拆，不按行数机械切片。
- 每个新模块必须有唯一职责与清晰依赖方向。
- 拆分前后对外契约保持一致；先加 characterization tests，再迁移。
- 不允许用更多文件把复杂度隐藏起来。

## 9. 质量门禁与真实验收

每个变更必须提供：

1. **静态检查**：类型/语法/lint（项目已有工具优先，不为门禁额外引入一套工具链）。
2. **单元测试**：只验证本模块逻辑。
3. **契约测试**：验证模块边界、schema、错误语义和版本兼容。
4. **集成测试**：验证真实模块调用关系，特别是 Socket、数据库、队列、外部 API。
5. **端到端测试**：仅对关键用户闭环建立，不用大量重复 E2E 取代单测。
6. **运行证据**：记录实际命令、HEAD SHA、通过/失败/跳过数量；未执行不能写通过。
7. **文档同步**：架构、配置、API 和迁移说明与实现同一提交更新。

验收标准不是“代码能运行”而是：真实输入进入正式入口，经过正式授权与持久化边界，得到可验证结果；失败时保留准确状态且不伪造成功。

## 9.1 配置治理当前落地记录（2026-11-19）

- 已修复 `ConfigLoader` 在模块导入时缓存 `EVO_CONFIG_PATH` 和 `Path.cwd()` 的问题。
- 已让 `ConfigLoader.find_config_file()` 支持显式工作区，并按本节定义的优先级查找。
- Admin `create_app()` 已把实际 `workspace` 传入 `get_distributed_config(workspace)`，避免依赖服务进程启动目录。
- 已新增 `tests/test_core_config_paths.py`，覆盖工作区配置、显式环境变量优先级和环境变量动态读取。
- 尚未完成：数据库连接配置与本地认证存储路径仍直接读取环境变量；本地认证 JSON 迁移、固定密码盐迁移、`src/.config/evo.json` 的全仓引用核验仍未完成。不得把本次配置路径修复描述为全仓配置已统一。

## 9.2 本地认证与密码迁移当前落地记录（2026-11-19）

- 新密码采用 `PBKDF2-HMAC-SHA256`，每条记录使用独立随机盐；旧 SHA-256 格式只用于兼容验证，成功登录后升级为新格式。
- MySQL 新表使用 `password_hash VARCHAR(255)`；初始化时检测旧列长度并升级，避免新哈希被 64 字符列截断。
- 本地认证文件默认写入用户数据目录（优先 `EVO_LOCAL_AUTH_DB`，其次 `XDG_DATA_HOME`，否则 `$HOME/.local/share/evo/admin_users.json`），不再把仓库根目录作为新数据写入位置。
- 本地存储采用临时文件 + fsync + 原子替换，文件权限设为仅当前用户可读写；损坏或无法解析时失败关闭，不自动覆盖为空账号库。
- 首次运行时，如果新位置不存在而旧仓库根 `.local_admin_users.json` 存在，会校验结构后复制到新位置；源文件保留，不自动删除。旧密码在首次成功登录时升级。
- **尚未完成的运维步骤**：必须先在目标部署环境启动新版本，确认新位置文件存在且账号数量一致，并完成登录验证；之后才能从 Git 跟踪中移除 `.local_admin_users.json`。不能在尚未迁移验证前删除该文件，否则可能丢失现有本地账号。
- 兼容旧密码依赖原 `PASSWORD_SALT` 环境变量（若部署曾自定义）；未设置时使用历史默认盐仅验证旧哈希。新密码生成不再使用该环境变量。


## 9.3 Admin 工作区解析统一（2026-11-19）

- `EVO_ADMIN_WORKSPACE` 表示业务数据工作区，不是代码仓库根目录；代码资源仍由 `repo_workspace` 定位。
- Admin API 与独立 Worker 共用 `src/admin/workspace.py::resolve_admin_workspace()`，不再分别判断工作区是否合法。
- 未设置环境变量时使用仓库根目录；显式设置时必须指向已存在目录，非法路径直接报错，避免静默回退后把业务数据写进代码仓库。
- 工作区路径解析只负责确定位置，不负责创建目录或初始化业务数据；各应用入口按自身生命周期处理目录准备。
- 数据库/认证数据目录仍独立于业务工作区，不能因为设置 `EVO_ADMIN_WORKSPACE` 就自动迁移认证存储。


## 9.4 认证存储后端唯一性（2026-11-19）

- 每个 Admin 进程只选择一个账号密码认证后端：`EVO_AUTH_BACKEND=mysql|local`。
- 未配置时保持历史部署默认：安装了 `pymysql` 默认选择 MySQL；未安装时选择本地文件。显式配置优先于自动选择。
- 运行期间后端固定，不因 MySQL 连接异常而回退到本地 JSON。MySQL 模式故障时登录/注册返回服务不可用（HTTP 503），不得在第二个存储中创建账号或用第二个存储验证账号。
- 本地模式不访问 MySQL；Gitee OAuth 的令牌仍由 Gitee 在线验证，用户资料同步到 MySQL 在本地模式下跳过。
- 切换后端属于显式数据迁移操作，不是故障恢复策略。切换前必须备份并核对账号记录；本变更不自动复制或合并两个存储。
- `/api/db/status` 仍用于 MySQL 运维检查；它不代表当前认证后端自动切换。

## 10. 分阶段治理顺序

### Phase 0：冻结范围并建立事实地图
- 暂停新功能叠加。
- 确认目录归属、数据所有者、配置入口、运行入口。
- 标记重复逻辑、超大文件、运行数据入库和 demo/fixture 污染。
- 保留 PR 当前功能，不做大规模搬迁。

### Phase 1：配置与数据边界
- 复用现有 `src/core/config.py::ConfigLoader` 管理分布式仓库配置，不另建重复 Settings/PathConfig；应用数据库、认证和运行时路径仍需逐项盘点，不能把分布式仓库配置误当作全局应用配置。
- 配置查找优先级固定为：`EVO_CONFIG_PATH` > 显式工作区 `.config/evo.json` > 仓库根 `.config/evo.json` > 当前目录 > 用户级配置 > 系统级配置。环境变量和当前目录在每次调用时读取，不在模块导入时缓存。
- Admin 初始化分布式配置时必须传入实际工作区；仓库根 `.config/evo.json` 是随仓库提供的默认配置，工作区配置用于部署/项目覆盖。`src/.config/evo.json` 暂不删除，待完成全仓调用点核验后再处理。
- 本地认证数据与仓库代码分离，并提供显式初始化/迁移。
- 清理运行生成数据；正式样本迁入 fixtures 并脱敏。
- 移除固定密钥/盐值默认值，提供安全迁移。

### Phase 2：Admin Composition Root 收敛
- 将 `server.py` 收敛为应用工厂和依赖组装。
- 将 API 路由按 mission/workforce/learning/skill/tenant 划分。
- 路由只做 HTTP 适配，业务流程归 application use case。

### Phase 3：Mission 与 Workforce 边界
- Mission 只持有任务决策和验收状态。
- Talent/Organization 只持有员工、岗位、Worker 生命周期。
- TaskQueue 是任务执行状态的权威来源。
- Worker lease 作为独立并发资源契约，不复制 Mission 状态机。

### Phase 4：Skill/Broker 安全链收敛
- 保留 Broker、Validator、Artifact Store 的独立安全边界。
- 收敛重复协议常量、schema 和 transport 入口。
- v1/v2 明确版本隔离；不增加没有真实调用方的协议。
- 完成真实 Mission -> Broker -> Validator -> Artifact Store 集成后，才推进自动复用。

### Phase 5：清理与发布
- 删除确认无引用的旧实现、兼容层和重复测试。
- 将架构文档更新为当前实现。
- 完成回归、部署演练、数据迁移和恢复验证。

## 11. 每次 PR 的结构审查清单

- [ ] 变更属于哪个目录/业务所有者？
- [ ] 是否存在已有模块可以扩展？
- [ ] 是否新增了重复 Runtime/Manager/Store/Registry？
- [ ] 是否引入硬编码路径、URL、端口、阈值、租户或凭据？
- [ ] 是否将运行数据、账号、Cookie、草稿或日志提交进仓库？
- [ ] 是否只有真实调用方才新增模块/API/schema？
- [ ] 是否有完整的输入校验、授权、持久化、错误语义和幂等性？
- [ ] 是否验证真实调用链，而不只是 mock 单测？
- [ ] 是否更新文档、配置示例和迁移说明？
- [ ] 是否记录当前 HEAD 的 CI 结果，不引用旧 SHA 的成功结果？

## 12. 当前执行约束

在 Phase 0 完成之前：

- 不继续增加新的 Planner 自动匹配、Catalog 自动发现或更多 Broker 协议层。
- 不做跨目录大规模搬迁。
- 只允许修复已确认的集成缺陷、安全问题和配置/数据污染。
- 每次结构重构只处理一个职责边界，先测试再迁移，迁移后删除旧实现。
