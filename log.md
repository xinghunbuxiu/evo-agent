# Evo（evo-os）变更日志

## 2026-08-26 - 仓库更名 evo-mcp → evo-os

- 修改人：AI助手
- 影响文件：仓库目录名、README/START/脚本路径示例、MCP config `WORKSPACE_ROOT`、UI 副标
- 变更概要：去掉「产品=MCP」歧义；品牌仍为 **Evo**，副标 **个人公司智脑**；ChatGPT 本地改代码仍用兄弟仓 `../workspace-mcp`
- 用法：见 README「本仓库 vs workspace-mcp」

## 2026-08-25 - Workspace MCP 拆出为独立仓库

- 修改人：AI助手
- 影响文件：删除 `mcp_workspace/`、`mcp-superassistant/`、`scripts/init_workspace_mcp.py`、`scripts/start_workspace_mcp.sh`、`scripts/start_auto_task.sh`、`scripts/workspace_agent_loop.py`、`docs/WORKSPACE_MCP_CN.md`、`docs/AUTO_TASK_CN.md`
- 变更概要：通用本地改项目 / ChatGPT shell MCP / 自动任务循环迁至独立项目 `../workspace-mcp`，与本仓（原 evo-mcp）解耦
- 用法：见 `../workspace-mcp/README.md`

## 2026-08-25 - 删除 mcp_bridge，仅保留 Workspace MCP

- 修改人：AI助手
- 影响文件：删除 `mcp_bridge/`、`scripts/start_chatgpt_bridge.sh`、`docs/CHATGPT_MCP_BRIDGE_CN.md`；更新 `init_workspace_mcp.py`、`start_workspace_mcp.sh`、`docs/WORKSPACE_MCP_CN.md`
- 变更概要：通用本地改项目只保留 workspace；init 不再提供 `--merge-evo`
- 用法：`python scripts/init_workspace_mcp.py /path/to/project` → `./scripts/start_workspace_mcp.sh`

## 2026-08-25 - 通用 Workspace MCP（含 shell，可改本地项目）

- 修改人：AI助手
- 影响文件：`mcp_workspace/server.py`、`scripts/init_workspace_mcp.py`、`docs/WORKSPACE_MCP_CN.md`、`mcp-superassistant/config.json`
- 变更概要：任意项目 `init_workspace_mcp.py` 后自动具备 list/grep/read/write/shell/git
- 用法：ChatGPT 连 `http://127.0.0.1:3006/sse`

## 2026-08-25 - ChatGPT 经 SuperAssistant 操作 evo-mcp（已废弃）

- 修改人：AI助手
- 变更概要：原 `mcp_bridge` 业务桥已删除；请改用 Workspace MCP

## 2026-08-09 - Playwright 验收员工工作台经验卡


- 修改人：AI助手
- 影响文件：`ChildWorkspace.vue`、`playwright_verify_experience_cards.py`、`m1_knowledge_learning_probe_runtime.py`（KEEP 落盘）
- 变更概要：修复 `loadWorkspace` 覆盖 `?tab=growth`；实网补知识卡在成长页可见（`knowledge_learning`）
- 验证：`test_output/playwright_experience/*_report.json` → ok=true

## 2026-08-09 - DeepSeek 实网补知识 + work_nodes 空经验卡修复

- 修改人：AI助手
- 影响文件：`m1_knowledge_learning_probe_runtime.py`、`work_nodes_runtime.py`、`scripts/live_deepseek_knowledge_probe.py`
- 变更概要：`EVO_M1_LIVE_MODEL=1` 用租户已配模型跑补知识写回；修复 `experience_cards` 为空时 IndexError；实网探测 ok + M1 33/33
- 关联需求：继续（DeepSeek 已通后推进供给环）

## 2026-08-09 - Playwright 验证 DeepSeek 连接

- 修改人：AI助手
- 影响文件：`tenant_policies.py`、`CompanySettings.vue`、`scripts/playwright_verify_deepseek.py`、admin-ui dist
- 变更概要：修复租户策略 PUT 因未标注 `Request` 导致 422；Playwright 登录→制度页填 DeepSeek→保存→真实 chat/completions 冒烟通过
- 验证：`scripts/playwright_verify_deepseek.py` → ok=true；回复 `pong`
- 安全：截图中的 API Key 已暴露，建议轮换

## 2026-08-09 - 渠道执行器可选 Playwright

- 修改人：AI助手
- 影响文件：`executors/toutiao/scripts/browser_backend.py`、`cli.py`、`requirements-playwright.txt`、README_PLAYWRIGHT.md
- 变更概要：`EVO_CHANNEL_BROWSER=playwright` 时登录/探测/辅助发文走 Chromium；失败回退本地 stub；intake 核心零改
- 关联需求：使用 Playwright

## 2026-08-09 - 经验卡反哺路由 + 补知识独立就绪

- 修改人：AI助手
- 影响文件：`intake_runtime.py`、`formal_task_evolution_runtime.py`、`model_provider_runtime.py`、M1 probe、IntakeWorkspace
- 变更概要：analyze 按 journal 商业/学习卡加权；补知识+一轮正式任务可达成独立候选
- 关联需求：继续分析优化 / 冲刺 90%+

## 2026-08-09 - 自主学习模型 + 补知识写回经验

- 修改人：AI助手
- 影响文件：
  - `src/admin/model_provider_runtime.py`（新增 OpenAI 兼容调用）
  - `src/core/tenant.py`、`routes/tenant_policies.py`、`knowledge_learning_runtime.py`、`external_learning_runtime.py`
  - `admin-ui` CompanySettings / ChildWorkspace
  - `m1_knowledge_learning_probe_runtime.py`、`scripts/m1_ops_check.py`
- 变更概要：租户可配 DeepSeek 等模型；补知识走模型（可 mock）；写回 experience_journal；工作台可见
- 关联需求：冲刺完成度 ~90%

## 2026-08-09 - 第二工种仅配置路由探测

- 修改人：AI助手
- 影响文件：`src/admin/m1_intake_probe_runtime.py`、`scripts/m1_ops_check.py`、`docs/EVO_MAINLINE_STATUS_CN.md`
- 变更概要：双工种员工仅靠 capability 配置分流，验证 intake 核心无硬编码工种分支
- 关联需求：/loop 1m tick 自动测试

## 2026-08-09 - 接单通演示财务可见断言

- 修改人：AI助手
- 影响文件：`src/admin/m1_intake_probe_runtime.py`、`scripts/m1_ops_check.py`、`docs/EVO_MAINLINE_STATUS_CN.md`
- 变更概要：结算后校验财务 project 列表与 revenue，闭合「演示财务可见」缺口
- 关联需求：/loop 1m 自动去测试完成

## 2026-08-09 - 履约产物回挂接单/工作台

- 修改人：AI助手
- 影响文件：
  - `src/admin/intake_runtime.py`（extract/attach artifacts）
  - `src/admin/server.py`（finalize_operation_result 挂钩）
  - `admin-ui` ChildWorkspace / IntakeWorkspace
  - `m1_intake_probe_runtime.py`、`scripts/m1_ops_check.py`
- 变更概要：operation 完成后草稿等路径回挂 fulfillment.artifacts，UI 可见
- 关联需求：/loop 双环唤醒继续

## 2026-08-09 - 结算自动本地经验导出

- 修改人：AI助手
- 影响文件：
  - `src/admin/local_git_export_runtime.py`（commercial settle 本地导出）
  - `src/admin/intake_runtime.py`（settle 调用导出并回写 growth_state）
  - `src/admin/m1_intake_probe_runtime.py`、`scripts/m1_ops_check.py`
  - `admin-ui` ChildWorkspace 展示导出状态
  - `docs/INTAKE_ARCHITECTURE_CN.md`、`docs/EVO_MAINLINE_STATUS_CN.md`
- 变更概要：消费环结算后经验先落本地 Git 降级目录，供给环可见导出路径
- 关联需求：/loop 继续优化双环

## 2026-08-09 - 路由反馈飞轮：改派原因 + 结算加权

- 修改人：AI助手
- 影响文件：
  - `src/admin/intake_runtime.py`（feedback 读写、analyze 加分、assign override、settle 回写）
  - `src/admin/routes/intake_routes.py`、`admin-ui` intake API/UI
  - `src/admin/m1_intake_probe_runtime.py`、`scripts/m1_ops_check.py`（反馈文件恢复 + P0 加权断言）
  - `docs/INTAKE_ARCHITECTURE_CN.md`、`docs/EVO_MAINLINE_STATUS_CN.md`
- 变更概要：育成改派记录原因；结算成功写入 feedback，下次智脑分析按能力历史加权；UI 展示反馈分与改派原因
- 关联需求：双环继续优化 / 智脑可维护

## 2026-08-09 - 双环衔接：结算回写员工成长 + 看板双环

- 修改人：AI助手
- 影响文件：
  - `src/admin/intake_runtime.py`（`apply_supply_growth_from_commercial_intake`）
  - `src/admin/trainer_coaching_runtime.py`（商业结算带教事件）
  - `src/admin/m1_intake_probe_runtime.py` / `scripts/m1_ops_check.py`
  - `admin-ui`：DashboardOverview、ChildWorkspace、companyTree、IntakeWorkspace、plugins 类型
- 变更概要：
  - 接单结算后写入员工经验卡 / growth_state 商业实绩 / 育成带教履历
  - 总览并列「消费环漏斗 + 供给环成长」；员工成长页展示商业结算数
- 关联需求：/loop 双环优化

## 2026-08-09 - 商业接单消费环：看板入口 + 结算闭环探测 + 文档

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/IntakeWorkspace.vue`（结算金额录入）
  - `admin-ui/src/views/Settings.vue` / `TrainerDispatchPanel.vue` / `ChildWorkspace.vue` / `FinanceWorkspace.vue` / `DashboardOverview.vue`
  - `admin-ui/src/api/plugins.ts`（intake_funnel 类型）
  - `src/admin/commercial_runtime.py`（就绪度含接单步骤）
  - `src/admin/m1_intake_probe_runtime.py`（新增）
  - `scripts/m1_ops_check.py`（P0 接单探测）
  - `docs/EVO_MAINLINE_STATUS_CN.md` / `docs/INTAKE_ARCHITECTURE_CN.md` / `docs/PRODUCT_M1_CHECKLIST_CN.md` / `README.md`
- 变更概要：
  - 公司总览展示接单漏斗；育成主线增加「接单对接」入口
  - 商业化就绪增加「商业接单已接入」；M1 P0 探测 create→assign→settle
  - 文档明确供给环 vs 消费环与反硬编码约束
- 关联需求：商业智脑 · 接单消费面

## 2026-05-31 01:10 - UI M11：遗留清理与站点元信息

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/components/Navbar.vue`（删除）
  - `admin-ui/src/components/QuickAction.vue`（删除）
  - `admin-ui/src/components/StatCard.vue`（删除）
  - `admin-ui/index.html`（修改：标题/描述/theme-color/favicon）
  - `admin-ui/public/favicon.svg`（新增）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 移除 AppShell 迁移后已无引用的旧顶栏与 Dashboard 卡片组件
  - 浏览器标签与 PWA theme-color 对齐「Evo · 个人公司智能体平台」
- 关联需求：UI 重设计 M11

## 2026-05-31 00:55 - UI M10：登录页与控制台视觉统一

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/Login.vue`（修改：分栏品牌区 + 表单卡片）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 登录/注册页采用与 AppShell 一致的 slate/teal 设计；更新产品文案
  - 大屏左侧品牌说明，右侧 SubNav 式登录/注册切换
- 关联需求：UI 重设计 M10

## 2026-05-31 00:40 - UI M9：Mission 运行列表 + 详情子导航

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/MissionRunsWorkspace.vue`（新增）
  - `admin-ui/src/views/MissionRunDetail.vue`（修改：页头 + SubNav）
  - `admin-ui/src/components/MissionRunDetailPanel.vue`（修改：section 分区）
  - `admin-ui/src/main.ts`（修改：missions 路由）
  - `admin-ui/src/utils/companyTree.ts`（修改：Mission 运行入口）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：树选中）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - Mission 列表与详情纳入 AppShell；详情 `?section=` 分摘要/动作链/成长/续跑
  - 续跑成功自动跳转新 mission_run_id
- 关联需求：UI 重设计 M9

## 2026-05-31 00:25 - UI M8：智脑页接入 AppShell 子导航

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/Knowledge.vue`（修改：页头 + SubNav 四分区）
  - `admin-ui/src/views/Evolution.vue`（修改：页头 + SubNav 四分区）
  - `admin-ui/src/views/Tasks.vue`（修改：统一页头）
  - `admin-ui/src/main.ts`（修改：`/organization/knowledge|evolution|tasks` 路由）
  - `admin-ui/src/utils/companyTree.ts`（修改：智脑分组）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：树选中）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 知识库/成长控制台/任务队列纳入左树「智脑」，统一 WorkspacePageHeader + SubNav
  - URL `?section=` 深链分区；旧路径保留 alias
- 关联需求：UI 重设计 M8

## 2026-05-31 00:10 - UI M7：育成师支撑工具独立页

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/TrainerToolsWorkspace.vue`（新增）
  - `admin-ui/src/views/Settings.vue`（修改：移除折叠支撑工具区）
  - `admin-ui/src/main.ts`（修改：tools 路由）
  - `admin-ui/src/utils/companyTree.ts`（修改：支撑工具入口）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：树选中）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 支撑工具迁到 `/organization/trainer/.../tools`，SubNav 分摘要/工种/Git/制度
  - 育成师主页只保留带教主流程，公司级修改仍跳转公司设置
- 关联需求：UI 重设计 M7

## 2026-05-30 23:55 - UI M6：公司设置分区 SubNav

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/CompanySettings.vue`（修改：section 分流 + SubNav）
  - `admin-ui/src/utils/companyTree.ts`（修改：公司设置默认工种入口）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 公司设置页按 `?section=overview|structure|policies|worktypes|integrations` 分屏展示
  - 避免单页堆叠制度/工种/Gitee/插件；子导航徽章展示员工数、工种数等
- 关联需求：UI 重设计 M6

## 2026-05-30 23:35 - UI M5：育成师/员工子导航 + 工作台瘦身

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/components/shell/WorkspaceSubNav.vue`（沿用/完善）
  - `admin-ui/src/views/Settings.vue`（修改：landing 与 mode 分流、育成师 SubNav）
  - `admin-ui/src/components/TrainerMainlineShell.vue`（修改：SubNav、compact 模式）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改：编排 SubNav）
  - `admin-ui/src/views/ChildWorkspace.vue`（已有 tab SubNav + URL 同步）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 育成师 URL 带 `?mode=` 时进入专注工作台，隐藏 landing 与辅助工具折叠区
  - 四条主线与任务编排四 Tab 统一为 WorkspaceSubNav，减少大卡片切换
  - 工作台 compact 隐藏重复 hero；页头增加节点流水快捷入口
- 关联需求：UI 重设计 M5

## 2026-05-30 23:10 - UI M4：统一页头 + 财务看板 + 全局刷新

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/components/shell/WorkspacePageHeader.vue`（新增）
  - `admin-ui/src/views/FinanceWorkspace.vue`（新增）
  - `admin-ui/src/main.ts`（修改：财务路由）
  - `admin-ui/src/composables/companyConsole.ts`（修改：financeOverview）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：财务注入、树选中、轮询刷新）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `admin-ui/src/views/CompanySettings.vue`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/views/OrganizationNode.vue`（修改）
  - `admin-ui/src/utils/organization.ts`（修改：财务链接）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 各职能页统一 AppShell 风格页头；左侧树「财务」进入独立看板
  - AppShell 每 60s（页面可见时）与路由切换时刷新 autonomy / workNodes / 财务
  - 员工提交任务、育成师确认后触发 refreshOverview，左侧徽章与看板同步
- 关联需求：UI 重设计 M4

## 2026-05-30 22:45 - UI M3：总览页 + 树徽章 + 移动端导航

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/Dashboard.vue`（修改：总览与详情分流）
  - `admin-ui/src/components/worknodes/DashboardOverview.vue`（修改：待关注/最近节点/工种快照）
  - `admin-ui/src/utils/companyTree.ts`（修改：workNodes 徽章）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：移动端抽屉菜单）
  - `admin-ui/src/components/worknodes/NodePhasePanel.vue`（修改：归档详情与一键归档）
  - `admin-ui/src/components/worknodes/WorkNodeWorkspace.vue`（修改：返回总览）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 总览页独立展示统计与可点击节点列表，工种/员工 scope 才进入节点流水工作台
  - 左侧公司树按 workNodes 显示「待确认 / 进行中」；小屏支持抽屉式公司导航
  - 节点流程面板展示 Gitee/本地归档路径，支持详情内一键归档
- 关联需求：UI 重设计 M3

## 2026-05-30 22:15 - UI M2：工作节点 API + Gitee 归档 + 技能 Tab

- 修改人：AI助手
- 影响文件：
  - `src/admin/work_nodes_runtime.py`（新增/完善）
  - `src/admin/routes/work_nodes_routes.py`（新增）
  - `src/admin/routes/system_runtime.py`（修改：approve 后自动归档、注册路由）
  - `admin-ui/src/api/workNodes.ts`（新增）
  - `admin-ui/src/components/shell/AppShell.vue`（修改：服务端节点列表）
  - `admin-ui/src/components/worknodes/SkillsPlaceholderPanel.vue`（修改）
  - `admin-ui/src/components/worknodes/ArchivePlaceholderPanel.vue`（修改）
  - `admin-ui/src/components/worknodes/WorkNodeWorkspace.vue`（修改）
  - `admin-ui/src/utils/workNodes.ts`（修改：archive 类型）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改：节点流水跳转）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改：节点流水跳转）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 后端聚合 work-nodes / skills，按节点路径写入 Gitee experiences（失败则本地 `.admin/local_git_exports/`）
  - 育成确认任务后自动触发节点归档并写回 `task.work_node_archive`
  - 看板技能 Tab 接 ExperienceStore；归档 Tab 支持手动补归档；AppShell 优先拉服务端节点
- 关联需求：UI 重设计 M2

## 2026-05-30 21:30 - UI M1：左树右栏 + 工作节点流水

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/components/shell/AppShell.vue`（新增）
  - `admin-ui/src/components/shell/CompanyTreeNav*.vue`（新增）
  - `admin-ui/src/components/worknodes/*.vue`（新增）
  - `admin-ui/src/utils/companyTree.ts`（新增）
  - `admin-ui/src/utils/workNodes.ts`（新增）
  - `admin-ui/src/composables/companyConsole.ts`（新增）
  - `admin-ui/src/App.vue`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `admin-ui/src/style.css`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 全局 AppShell：左侧公司树（部门→工种→员工）+ 右侧内容区
  - Dashboard 改为节点流水工作台：7 阶段时间轴、经验/归档 Tab（技能 M2 占位）
  - 客户端从 task_center / memory_hub / experience_journal 聚合 WorkNode
- 关联需求：UI 重设计 M1

## 2026-05-30 21:00 - 修复 Admin 登录 500（Vite 代理端口）

- 修改人：AI助手
- 影响文件：
  - `admin-ui/vite.config.ts`（修改）
  - `log.md`（修改）
- 变更概要：
  - 前端 API 代理默认端口从 8010 改为 8000，与 uvicorn 启动端口一致，避免登录请求 500
- 关联需求：本地运行 / 登录 500

## 2026-05-24 30:10 - 跨工种协作 UI（育成师队列 + 员工待对接）

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/utils/collaborationView.ts`（新增）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 育成官任务编排新增「协作队列」工作位：查看进行中请求、指派提供方、跳转派任务
  - 员工工作台新增协作发起表单与 integration_pending 横幅（不阻塞主任务；ready 时可标记已对接）
  - 能力选项从 deliverable_templates 配置读取，不写死工种
- 关联需求：协作架构 UI 落地

## 2026-05-24 29:35 - 跨工种协作架构 + 配置驱动 runtime/API

- 修改人：AI助手
- 影响文件：
  - `docs/COLLABORATION_ARCHITECTURE_CN.md`（新增）
  - `docs/schemas/collaboration_policies.schema.json`（新增）
  - `docs/schemas/deliverable_templates.schema.json`（新增）
  - `.admin/collaboration_policies.json`（新增）
  - `.admin/deliverable_templates.json`（新增）
  - `src/admin/collaboration_policy_runtime.py`（新增）
  - `src/admin/collaboration_runtime.py`（新增）
  - `src/admin/routes/collaboration_routes.py`（新增）
  - `src/admin/routes/system_runtime.py`（修改）
  - `src/admin/runtime_state.py`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 落地配置驱动的跨工种协作：能力语义、策略路由、交付物模板、integration_pending 子状态
  - 通用 API 与 task submit/approve hook；不写死 App/Java 等具体工种
  - 请求方并行执行；提供方 approve 后按模板通知 requester 可对接
- 关联需求：协作架构（非硬编码）

## 2026-05-24 29:05 - 育成师带教履历 + 看板按部门分组

- 修改人：AI助手
- 影响文件：
  - `src/admin/trainer_coaching_runtime.py`（新增）
  - `src/admin/runtime_state.py`（修改）
  - `src/admin/routes/system_runtime.py`（修改）
  - `src/admin/formal_task_evolution_runtime.py`（修改）
  - `admin-ui/src/utils/organization.ts`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `admin-ui/src/components/TrainerExclusivePanel.vue`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 任务 approve、模式 A 复制建档、可独立运营放手时自动写入育成师 experience_journal 带教履历
  - 育成官「自我发展」视图展示带教履历时间线
  - 公司看板员工节点按部门（运营/研发）→ 工种 → 成员三层分组
- 关联需求：育成师成长 + 组织结构

## 2026-05-24 28:35 - 模式 A 复制建档 + 工种部门元数据

- 修改人：AI助手
- 影响文件：
  - `src/admin/member_clone_runtime.py`（新增）
  - `src/admin/runtime_state.py`（修改）
  - `src/admin/routes/system_runtime.py`（修改）
  - `src/work_types.py`（修改）
  - `scripts/bootstrap_self_media_worktype.py`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `admin-ui/src/api/workTypes.ts`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `admin-ui/src/components/CompanyWorkTypesPanel.vue`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 新增 `POST /api/autonomy/members/clone`（`account_variant`：同工种换账号/换内容方向）
  - 复制画像与训练策略骨架，不复制任务/登录态；可选预填首轮派任务草案
  - 工种支持 `department_id`/`department_label`（运营/研发）；员工写入 `organization` 与 `content_profile`
  - 员工工作台增加「复制同岗位 · 新账号」入口，成功后跳转育成官派任务页
- 关联需求：模式 A 复制 + 组织结构

## 2026-05-24 28:05 - 补知识后自动派任务建议 + 独立运营放手提示

- 修改人：AI助手
- 影响文件：
  - `src/admin/formal_task_evolution_runtime.py`（修改）
  - `src/admin/knowledge_learning_runtime.py`（修改）
  - `src/admin/task_center_runtime.py`（修改）
  - `src/admin/routes/system_runtime.py`（修改）
  - `admin-ui/src/utils/memberEvolutionView.ts`（修改）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 补知识进入 candidate_found/validated/resolved 后自动生成「补知识后验证任务」建议并通知育成官
  - 可独立运营达标后自动写入育成官线程与公司收件箱放手提示（independence_handoff）
  - 派任务/员工工作台展示放手提示与补知识后任务建议状态
- 关联需求：继续完成系统

## 2026-05-24 27:45 - 补知识回写 training_plan + M1 runtime 直调

- 修改人：AI助手
- 影响文件：
  - `src/admin/knowledge_learning_runtime.py`（新增）
  - `src/admin/formal_task_evolution_runtime.py`（新增）
  - `src/admin/task_center_runtime.py`（新增）
  - `src/admin/m1_evolution_probe_runtime.py`（新增）
  - `src/admin/routes/system_runtime.py`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `admin-ui/src/utils/memberEvolutionView.ts`（修改）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 补知识任务验证（memory_hub_auto）走轻量验证并回写 training_plan：status/summary/next_action/stage
  - GET learning-tasks、validate、自动补知识创建后同步回写员工训练计划
  - M1 进化探测改为 runtime 直调（不再 create_app/TestClient），秒级完成
- 关联需求：继续完成系统

## 2026-05-24 27:25 - 补知识可视化 + 员工思考摘要 + M1 探测缓存

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/utils/memberEvolutionView.ts`（新增）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 育成官派任务闭环总览展示该员工自动触发的补知识任务（状态/调研问题/启动验证）
  - 员工工作台任务区展示系统自主思考摘要，并提示补知识进度
  - M1 进化探测复用 TestClient 缓存；支持 `EVO_M1_SKIP_EVOLUTION=1` 跳过
- 关联需求：继续完成系统

## 2026-05-24 27:05 - 工作台任务高亮 + 补知识自动化 + 进化闭环自检

- 修改人：AI助手
- 影响文件：
  - `src/admin/routes/system_runtime.py`（修改）
  - `admin-ui/src/views/ChildWorkspace.vue`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 修复 memory_hub 绑定缺失 import；Memory Hub 判定需外部学习时自动创建补知识学习任务
  - 员工工作台高亮当前待执行/待提交正式任务（顶部横幅 + 指标卡 ring）
  - M1 P0 新增 assign→submit→approve→下一轮建议 进化闭环探测（TestClient，跑完恢复 runtime）
- 关联需求：继续完成系统 / 自主进化

## 2026-05-24 26:35 - 任务确认后自主进化闭环（全工种）

- 修改人：AI助手
- 影响文件：
  - `src/admin/routes/system_runtime.py`（修改）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 任务 approve 后对所有岗位成员统一：Memory Hub 思考 → 下一轮任务建议 → 育成跟进消息 → 可独立运营判定 → training-review 持久化
  - 下一轮推荐草案融合 memory_hub 决策（主方案/验证目标）；operation 工种保留 Git 导出与自动派下一轮
  - assign/submit 后触发 training-review 轻量更新
  - 派任务闭环总览展示「系统自主思考」与「可独立运营判定」；确认完成后自动切到任务分配视图
- 关联需求：自主进化思考闭环

## 2026-05-24 26:10 - 派任务后跳转工作台 + 看板工种摘要

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `admin-ui/src/utils/workTypeDashboard.ts`（新增）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 分配正式任务（含一键采纳建议）成功后自动打开对应员工工作台
  - 派任务面板增加「打开员工工作台」按钮
  - 公司看板新增「岗位工种摘要」：按工种统计员工数、待提交/待确认任务，可直达工作台
- 关联需求：派任务→工作台 / 公司看板

## 2026-05-24 25:55 - 建档后跳转派任务 + bootstrap mission_kind

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/components/TrainerPortraitPanel.vue`（修改）
  - `scripts/bootstrap_self_media_worktype.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 绑定工种的员工建档完成后自动跳转派任务页（assign 子页）并预填 Mission 草案
  - 画像面板增加「去派任务」按钮；新增 goToTrainerDispatchForMember 路由同步
  - bootstrap 脚本写入 mission_kind/worker_id，与 Admin「添加工种」字段对齐
- 关联需求：建档→派任务闭环

## 2026-05-24 25:40 - 派任务 Mission 推荐 + M1 工种链路自检

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/utils/formalTaskRecommendation.ts`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/components/TrainerDispatchPanel.vue`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `src/work_type_runtime.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 切换员工/加载工种与 Mission 模板时强制刷新派任务草案；派任务面板展示工种 ID 与 mission_kind
  - 推荐逻辑支持按 capability_type 回退匹配 Mission 模板
  - M1 P0 增加临时探测工种链路（添加工种→建档 job_id→worker 路由→Mission 模板），跑完自动恢复
  - work_type runtime index 中 worker 默认 enabled 与 registry 对齐为 false
- 关联需求：派任务 / M1 自检

## 2026-05-24 25:25 - 育成官建档：工种下拉 + 添加工种后跳转

- 修改人：AI助手
- 影响文件：
  - `src/admin/runtime_state.py`（修改）
  - `src/admin/routes/system_runtime.py`（修改）
  - `admin-ui/src/api/plugins.ts`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `admin-ui/src/components/TrainerPortraitPanel.vue`（修改）
  - `admin-ui/src/components/CompanyWorkTypesPanel.vue`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 创建/编辑员工时从 `GET /api/work-types` 下拉选择岗位工种，写入 `primary_role` 与 `current_jobs.job_id`
  - `POST /api/autonomy/members` 支持 `work_type_id`，后端校验工种存在
  - 公司空间添加工种后可「去建档」，保存后自动跳转育成官画像页并预填 `work_type_id`
- 关联需求：添加工种 / 育成官建档

## 2026-05-24 25:10 - 公司空间「添加工种」UI

- 修改人：AI助手
- 影响文件：
  - `admin-ui/src/api/workTypes.ts`（新增）
  - `admin-ui/src/components/CompanyWorkTypesPanel.vue`（新增）
  - `admin-ui/src/views/CompanySettings.vue`（修改）
  - `src/admin/routes/catalog.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 公司空间 `/organization/parent/workspace` 增加岗位工种列表与添加工种表单，对接 `GET/PUT /api/work-types`
  - 保存时可勾选同时启用执行器；原「工种开关」改名为「执行器开关」
  - 后端 PUT 校验保留 ID 与重复 work_type_id
- 关联需求：添加工种 / Admin UI

## 2026-05-24 24:50 - 架构对齐：工种仅走「添加工种」，移除 evo.json domains 清单

- 修改人：AI助手
- 影响文件：
  - `.config/evo.json`（修改）
  - `.config/evo.json.example`（修改）
  - `README.md`（修改）
  - `scripts/bootstrap_self_media_worktype.py`（修改）
  - `log.md`（修改）
- 变更概要：
  - 明确业务工种唯一数据面为 `.admin/work_types.json`（PUT /api/work-types），不在 evo.json 写 android/javascript 等
  - openSpec/workers 定位为执行器插件源码，非「已添加工种」；内置边界仍仅育成师+财务
- 关联需求：添加工种 / 禁止配置写死工种

## 2026-05-24 24:35 - 去硬编码第 7 步：清空内置工种 + domain 动态化

- 修改人：AI助手
- 影响文件：
  - `src/workers/registry.py`（修改）
  - `openSpec/workers/javascript_reverse/definition.py`（新增）
  - `src/workers/javascript_reverse/__init__.py`（修改）
  - `src/core/mission_planner.py`（修改）
  - `src/admin/worker_route_runtime.py`（修改）
  - `src/admin/background_research_runtime.py`（修改）
  - `src/admin/server.py`（修改）
  - `src/project_caps.py`（修改）
  - `admin-ui/src/views/Settings.vue`（修改）
  - `openSpec/workers/self_media_operations/definition.py`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - `BUILTIN_WORKER_DEFINITIONS` 置空；`javascript_reverse` 迁到 openSpec，`default_enabled: false`
  - Worker 默认关闭；registry 未显式启用则 false；Mission 模板/上下文解析从 Worker 定义动态加载
  - 去除 goal 关键词自动推断 JS 工种；`resolve_experience_domain` 改读 manifest.experience_domain
  - 预置 `project.javascript` 包启动时清理；JS 调研循环仅在启用 `javascript_reverse` 时跑
- 关联需求：禁止育成师/财务以外硬编码工种

## 2026-05-24 24:10 - 去硬编码第 6 步：剩余硬编码动态化 + 工种引导脚本

- 修改人：AI助手
- 影响文件：
  - `src/admin/worker_route_runtime.py`（修改）
  - `src/admin/routes/system_runtime.py`（修改）
  - `src/admin/background_research_runtime.py`（修改）
  - `src/core/mission_planner.py`（修改）
  - `src/workers/self_media_operations/monitor.py`（修改）
  - `scripts/bootstrap_self_media_worktype.py`（新增）
  - `docs/PRODUCT_M1_CHECKLIST_CN.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 以 `worker_uses_self_media_tenant_bucket` / `build_operation_job_runtime` 替换 `worker_id == self_media_operations` 分支
  - mission_planner 按 automation 能力类型与 `*_operations` 工种识别运营任务，不再写死工种 ID
  - monitor 动态解析成员与 `_autonomy_job`；新增可选引导脚本启用测试工种（不创建预置成员）
- 关联需求：去硬编码 / M1 演示路径

## 2026-05-24 23:55 - 去硬编码第 5 步：M1 自检分层 + 工种冒烟文档

- 修改人：AI助手
- 影响文件：
  - `scripts/m1_ops_check.py`（修改）
  - `docs/PRODUCT_M1_CHECKLIST_CN.md`（修改）
  - `docs/EVO_MAINLINE_STATUS_CN.md`（修改）
  - `START.md`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - M1 自检支持 `--with-worker-smoke` / `--keep-smoke-artifacts`；W 段默认清理临时财务与草稿，避免脏盘
  - 持久启用 Worker 时 W 段保留落盘；文档补充公司空间启用 → 重启 → 建成员 → 派任务完整路径
  - 主线状态文档对齐「无预置成员、工种默认关闭、P0 8/8」
- 关联需求：M1 运营标准 / 保持环境干净

## 2026-05-24 23:45 - 去硬编码第 4 步：财务动态 project_id + 环境清理

- 修改人：AI助手
- 影响文件：
  - `src/admin/finance_runtime.py`（修改）
  - `src/admin/routes/finance.py`（修改）
  - `src/admin/server.py`（修改）
  - `admin-ui/src/api/finance.ts`（修改）
  - `admin-ui/src/utils/organization.ts`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `admin-ui/src/views/OrganizationNode.vue`（修改）
  - `scripts/m1_ops_check.py`（修改）
  - `docs/PRODUCT_M1_CHECKLIST_CN.md`（修改）
  - `.admin/finance/toutiao_default.json`（删除）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 财务 API 新增 `GET /api/finance/overview`；`project_id` 由 payload/work_type/member 动态解析，不再默认 `toutiao_default`
  - Admin 看板/组织节点改读 overview；服务启动时自动 `purge_preset_finance_data`
  - M1 自检拆为 P0 干净环境（8 项）+ W 段可选工种冒烟（需启用 `self_media_operations`）
- 关联需求：去硬编码 / 保持环境干净

## 2026-05-24 23:35 - 去硬编码第 3 步：工种动态路由

- 修改人：AI助手
- 影响文件：
  - `src/admin/worker_route_runtime.py`（新增）
  - `src/admin/routes/system_runtime.py`（修改）
  - `src/admin/server.py`（修改）
  - `src/admin/background_research_runtime.py`（修改）
  - `src/admin/memory_hub_runtime.py`（修改）
  - `src/admin/mission_runtime.py`（修改）
  - `log.md`（修改）
- 变更概要：
  - 新增 work_type → worker 动态解析，替换 `primary_role == self_media_operations` 硬编码分支
  - 岗位 job runtime / 经验导出 / 育成推荐按成员 current_jobs 与 worker 注册表 dispatch
  - 保留 self_media worker 内部实现，仅当解析到对应 worker_id 时调用
- 关联需求：去硬编码 / 用户创建工种

## 2026-05-24 23:20 - 去硬编码第 2 步：清理 self_media_child + 内置财务

- 修改人：AI助手
- 影响文件：
  - `src/admin/runtime_state.py`（修改）
  - `.admin/autonomy_runtime.json`（修改）
  - `.tenants/default/autonomy_runtime.json`（修改）
  - `.tenants/default/members/self_media_child/`（删除）
  - `log.md`（修改）
- 变更概要：
  - 加载/保存时过滤预置 `self_media_child`，`primary_child_member_id` 仅指向用户创建成员
  - 内置育成师保留；新增 `finance` 内置 runtime 节点
  - 清空测试用 self_media / feedback 租户态与育成对话刷屏残留
- 关联需求：去硬编码 / 内置育成师+财务

## 2026-05-24 23:05 - 去硬编码第 1 步：自媒体工种迁出内置

- 修改人：AI助手
- 影响文件：
  - `openSpec/workers/self_media_operations/definition.py`（新增）
  - `openSpec/workers/README.md`（修改）
  - `src/workers/registry.py`（修改）
  - `src/workers/self_media_operations/__init__.py`（修改）
  - `README.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - `self_media_operations` 从 `BUILTIN_WORKER_DEFINITIONS` 移除，改为 OpenSpec 外部工种
  - `default_enabled: false`；用户添加工种并启用后才注册 task handlers
  - 明确内置边界：育成师 + 财务；其余工种/成员为用户创建
- 关联需求：去硬编码 / 用户创建工种

## 2026-05-24 22:28 - M1 运营标准第 2 轮（自检全绿 + Git 本地降级）

- 修改人：AI助手
- 影响文件：
  - `scripts/m1_ops_check.py`（新增）
  - `src/admin/local_git_export_runtime.py`（新增）
  - `src/admin/server.py`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `docs/PRODUCT_M1_CHECKLIST_CN.md`（修改）
  - `docs/EVO_MAINLINE_STATUS_CN.md`（修改）
  - `README.md`（修改）
  - `START.md`（修改）
  - `log.md`（修改）
- 变更概要：
  - 新增 M1 自检脚本（头条 A/B/C + 育成 + 财务落盘），本地 9/9 通过
  - Git export 远端失败时降级为 `.admin/local_git_exports/` 本地落盘
  - 项目看板卡片展示 `revenueSummary` 收益行
- 关联需求：M1 运营标准 / /loop 持续优化

## 2026-05-24 22:15 - M1 财务闭环与运营向优化（第 1 轮）

- 修改人：AI助手
- 影响文件：
  - `src/admin/finance_runtime.py`（新增）
  - `src/admin/routes/finance.py`（新增）
  - `src/admin/routes/__init__.py`（修改）
  - `src/admin/server.py`（修改）
  - `admin-ui/src/api/finance.ts`（新增）
  - `admin-ui/src/utils/organization.ts`（修改）
  - `admin-ui/src/views/Dashboard.vue`（修改）
  - `executors/toutiao/scripts/cli.py`（修改）
  - `.admin/autonomy_runtime.json`（修改）
  - `log.md`（新增）
- 变更概要：
  - 新增 `GET /api/finance/summary` 与 analytics 完成后的财务落盘
  - Admin 组织/看板财务节点与项目卡片可展示净收益摘要
  - 自治默认域改为 `operations`；头条 `--draft` 未登录也可保存草稿
- 关联需求：M1 财务 / 运营标准
