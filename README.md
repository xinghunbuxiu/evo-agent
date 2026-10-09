# Evo — 个人公司智脑（仓库名：`evo-os`）

> 仓库原名 `evo-mcp`，已更名为 **`evo-os`**，避免被误认为「MCP 协议产品」。产品品牌仍为 **Evo**。

为**一个人经营一家公司**设计的商业智脑：你是公司管理者，平台默认两条职能线配合你运转：

| 角色 | 职责 |
|------|------|
| **育成师** | 塑造岗位成员的人格与能力，接你的经营目标，补知识、排任务、复盘，直到成员能独立完成该类工作 |
| **财务** | 看业务有没有真实收益与成本，支撑「继续投 / 收缩 / 改策略」 |
| **岗位成员** | 由你在平台创建，执行具体工种（测试工种见 `openSpec/workers/`，默认关闭） |

底层仍有任务队列、经验沉淀、Git 知识容器与 Admin 控制台；**产品主线是「育成 + 管账 + 工种交付」**，不是代码逆向或 MCP 工具。

### 本仓库 vs `workspace-mcp`

| | **evo-os（本仓）** | **workspace-mcp（兄弟仓）** |
|--|--|--|
| 是什么 | Evo 个人公司智脑：Admin、接单、育成、财务、工种插件 | 通用本地项目 MCP（shell 等），给 ChatGPT SuperAssistant 用 |
| 入口 | `http://127.0.0.1:8000`（Admin HTTP） | `http://127.0.0.1:3006/sse`（可选） |
| 关系 | 产品本体 | **可选**本地改代码工具；与产品主线无关 |

在本仓调试时若需 ChatGPT 改代码，用 `./scripts/start_chatgpt_workspace.sh`（转发到 `../workspace-mcp`），不要把本仓当成 MCP 服务本体。

**内置职能**：育成师、财务。**业务工种**不在配置文件里写死，由用户在平台 **「添加工种」** 写入 `.admin/work_types.json`（API：`PUT /api/work-types`）。

### 工种 vs 执行器插件

| 层 | 是什么 | 谁维护 |
|----|--------|--------|
| **工种**（work_type） | 岗位边界、目标、绑定的 worker / 能力包 | **用户**在 Admin 添加 |
| **Worker 插件**（openSpec/workers/） | 任务 handler、Mission 模板等**实现代码** | 研发放入仓库，**默认不启用** |
| **evo.json** | 仅 Git 仓、存储、学习阈值等平台基建 | 部署时配置 |

正确流程（**商业消费环优先**）：公司空间 **添加工种并配置能力** → 育成 **画像建档** → **接单台**录入外包/经营任务 → 智脑按 capability 推荐 → 育成确认分派 → 员工交付 → 接单台 **结算入账** → 复盘/经验/Gitee。  
对内训练仍可用育成「派任务」；与接单共用正式任务与复盘链路，路由/履约**不写死工种名**（见 [docs/INTAKE_ARCHITECTURE_CN.md](docs/INTAKE_ARCHITECTURE_CN.md)）。

- 添加工种：`/organization/parent/workspace` → `PUT /api/work-types`
- 建档入口：`/organization/trainer/talent_development_officer/workspace?mode=portrait&work_type_id=<工种ID>`
- 派任务入口：`?mode=dispatch&dispatchTab=assign&member=<员工ID>`（绑定工种建档成功后会自动跳转）
- 分配任务成功后会自动打开 `/organization/child/<员工ID>/workspace`（**高亮当前待执行/待提交任务**）
- 任务确认完成后系统自动：Memory Hub 思考 → 下一轮任务建议 → 可独立运营判定 → 训练复盘入库
- 补知识验证完成后，系统**自动推荐下一轮正式任务**（无进行中任务时写入 task_center.recommendations）
- 达到可独立运营标准后，系统向育成官与公司收件箱发送**放手提示**
- 育成官派任务「闭环总览」可查看该员工的 **补知识任务进度**，并一键启动验证
- 员工工作台任务区展示 **系统自主思考** 摘要
- 公司看板（首页）展示各工种员工数、任务状态与**接单漏斗**
- **接单台**：`/organization/intake`（新建 / 漏斗看板 / 分析 / 分派 / 结算）；左树职能区「接单台」
- API：`GET/POST /api/autonomy/intake*`、`POST .../analyze|assign|settle|cancel`
- **UI M1**：登录后全局 **左树右栏**（`AppShell`）— 左侧公司菜单（部门→工种→员工），右侧 **节点流水**（思考→归档 7 阶段）；见 `/dashboard`
- **UI M2**：工作节点服务端聚合 + Gitee 按节点归档
  - API：`GET /api/autonomy/work-nodes`、`GET /api/autonomy/work-nodes/skills`、`POST /api/autonomy/work-nodes/{task_id}/archive`
  - 任务 `approve` 后自动归档（无 Token 时落盘 `.admin/local_git_exports/`）
  - 看板 Tab：技能库（ExperienceStore）、归档（手动补归档）；育成师/员工工作台可跳转节点流水
- **UI M3**：总览与导航体验
  - `/dashboard` 总览页：待关注节点、最近节点、工种快照（点击进入节点/工种流水）
  - 左侧树徽章同步 workNodes 状态（待确认 / 进行中）；小屏「菜单」抽屉导航
  - 节点详情面板展示归档路径与一键归档；详情页「返回总览」
- **UI M4**：职能页统一 + 财务看板 + 自动刷新
  - 共享页头 `WorkspacePageHeader`（员工 / 公司设置 / 育成师 / 组织节点 / 财务）
  - `/organization/finance` 财务看板（各项目净收益明细）
  - AppShell：财务数据注入、左侧树高亮员工/财务路由、路由切换与 60s 轮询刷新
  - 任务提交 / 育成确认后同步刷新公司节点与树徽章
- **UI M5**：育成师/员工子导航 + 工作台瘦身
  - 共享 `WorkspaceSubNav`：员工 Tab（任务/思考/成长/归档/沟通）同步 URL `?tab=`
  - 育成师：`?mode=` 进入工作台后隐藏 landing，顶栏子导航（建档/编排/复盘/策略）
  - 任务编排子 Tab（总览/分配/确认/协作）改为 SubNav；工作台 compact 模式减少重复信息
- **UI M6**：公司设置分区导航
  - `/organization/parent/workspace?section=`：总览 / 结构 / 制度 / 工种 / 接入
  - 各分区独立页头与按需刷新；左侧树「公司设置」默认进入工种配置
- **UI M7**：育成师支撑工具独立页
  - `/organization/trainer/{id}/tools?section=`：摘要 / 工种 / Git / 制度（只读）
  - 从 Settings.vue 移除折叠「次要支撑工具」大块，主工作台更轻
  - 左侧树职能区新增「支撑工具」入口
- **UI M8**：智脑页接入 AppShell 子导航
  - `/organization/knowledge?section=`：总览 / 索引 / 技能 / 导出
  - `/organization/evolution?section=`：总览 / 复盘 / 轨迹 / 策略
  - `/organization/tasks` 统一页头；旧 `/knowledge` `/evolution` `/tasks` 仍可用（alias）
  - 左侧树新增「智脑」分组（知识库、成长控制台、任务队列）
- **UI M9**：Mission 运行列表 + 详情子导航
  - `/organization/missions` 列表；`/organization/missions/{id}?section=` 详情四分区
  - 摘要 / 动作链 / 成长 / 续跑；旧 `/missions/{id}` 保留 alias
  - 左树智脑区新增「Mission 运行」
- **UI M10**：登录页与控制台视觉统一
  - `/login` `/register`：左品牌区（slate-900）+ 右表单卡片，与 AppShell 同系 slate/teal
  - 文案对齐「个人公司智脑」；登录/注册 SubNav 与控制台一致
- **UI M11**：遗留清理与站点元信息
  - 移除未引用的旧组件 `Navbar.vue`、`QuickAction.vue`、`StatCard.vue`（已由 AppShell 与 Dashboard 组件替代）
  - `index.html` 标题/描述/theme-color 对齐产品品牌；新增 `public/favicon.svg`（slate/teal）
- 创建员工 API：`POST /api/autonomy/members`（可选 `work_type_id`）
- **同岗位复制建档（模式 A）**：`POST /api/autonomy/members/clone`（`source_member_id`、`name`、`account_id`、`content_direction`；可选 `prefill_first_task`）
- 员工工作台侧边栏 **「复制同岗位 · 新账号」** → 复制成功后跳转育成官派任务页
- 任务确认 / 复制建档 / 可独立运营放手时，自动写入**育成师带教履历**（`experience_journal` 中带【带教】标记）
- 公司看板组织结构按 **部门 → 工种 → 员工** 分组展示（运营 / 研发）
- **跨工种协作（配置驱动）**：员工按 `needed_capability` 发起请求、并行执行；育成师指派提供方；提供方任务 approve 后通知请求方 `ready_to_integrate`（见 [docs/COLLABORATION_ARCHITECTURE_CN.md](docs/COLLABORATION_ARCHITECTURE_CN.md)）
  - 配置：`.admin/collaboration_policies.json`、`.admin/deliverable_templates.json`
  - API：`POST/GET /api/autonomy/collaborations`、`POST .../assign`、`POST .../mark-integrated`
  - **UI**：育成官「任务编排 → 协作队列」；员工工作台「需要其他工种配合」+ `integration_pending` 待对接横幅

### 组织结构（部门 × 工种 × 员工）

| 层 | 说明 | 示例 |
|----|------|------|
| **部门** | 公司编制划分，挂在工种上 | `operations` 运营、`rnd` 研发 |
| **工种** | 具体岗位职责 + 执行器 | 今日头条运营、微信公众号运营（均属运营）；App/PC 开发（属研发） |
| **员工实例** | 一人一号一条任务线 | 张三头条1号、李四头条2号（模式 A 复制） |

添加工种时可指定 `department_id` / `department_label`；建档与复制时自动写入员工的 `organization` 与 `content_profile.content_direction`。

`openSpec/workers/`、`domains/*` 源码**不是**已上线工种列表；不要在 `evo.json` 里写 android / javascript 等工种名。

## 快速开始

详见 **[START.md](START.md)**。

```bash
cp .env.example .env
docker compose up -d evo-admin
# 浏览器打开 http://localhost:8000 → 组织 / 育成师 / 岗位成员工作台
```

本地开发：

```bash
cd src && pip install -r ../requirements.txt
python3 -m uvicorn admin.server:create_app --reload --port 8000 --factory
```

**M1 运营标准自检**（干净默认环境 + 可选已启用工种冒烟）：

```bash
PYTHONPATH=src python3 scripts/m1_ops_check.py
```

默认 **P0 全绿 PASS**（含工种链路探测 + approve→下一轮建议进化闭环探测，跑完自动恢复）；加 `--with-worker-smoke` 可跑 W 段冒烟。

进化闭环探测会加载完整 Admin（约 2～4 分钟）。现已改为 **runtime 直调**（通常数秒内完成）。若只需快速跳过：

```bash
EVO_M1_SKIP_EVOLUTION=1 PYTHONPATH=src python3 scripts/m1_ops_check.py
```

```bash
# 临时验证头条 executor 链路（跑完自动清理产物）
PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke
```

## 架构（产品视角）

```
你（公司管理者）──▶ 接单台（消费前端）
                      │
                 智脑 capability 路由
                      │
                 育成师（≈CTO）确认分派 / 对内带教
                      │
                 岗位成员 ──▶ worker 插件履约
                      │
                 财务结算 ◀── 交付验收
                      │
                 经验 / Gitee ──▶ 反哺智脑
```

代码入口：`src/admin/server.py`（HTTP）、`src/admin/worker.py`（可选队列消费者）。

## 文档

| 文档 | 说明 |
|------|------|
| [START.md](START.md) | 启动与环境 |
| [docs/INTAKE_ARCHITECTURE_CN.md](docs/INTAKE_ARCHITECTURE_CN.md) | **商业接单（消费环）架构**（capability / 策略，非硬编码） |
| [docs/COLLABORATION_ARCHITECTURE_CN.md](docs/COLLABORATION_ARCHITECTURE_CN.md) | **跨工种协作架构**（配置驱动，非硬编码） |
| [docs/PRODUCT_M1_CHECKLIST_CN.md](docs/PRODUCT_M1_CHECKLIST_CN.md) | **M1 正式运营清单**（育成 / 财务 / 可选工种） |
| `scripts/m1_ops_check.py` | **M1 运营标准自检**（P0 含接单消费环 + 可选 W 段） |
| `scripts/bootstrap_self_media_worktype.py` | **可选** 启用测试工种（不创建预置成员） |
| [docs/EVO_MAINLINE_STATUS_CN.md](docs/EVO_MAINLINE_STATUS_CN.md) | 主线进度与完成度 |
| [ADMIN_README.md](ADMIN_README.md) | OAuth、部署、API |
| [docs/evo-autonomy-mainline.md](docs/evo-autonomy-mainline.md) | 自治与成长闭环 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 技术分层（开发参考） |

## 非产品主线（默认关闭）

仓库内 `src/domains/*` 等为**可插拔能力实现**，仅在用户添加工种并绑定对应 project package / worker 后才会注册；**不在** `.config/evo.json` 中预置工种清单。详见 `.config/evo.json`（仅平台 Git / 存储 / 学习阈值）。

## 许可证

MIT
