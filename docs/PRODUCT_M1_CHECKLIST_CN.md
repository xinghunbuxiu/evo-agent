# M1 清单：个人公司智脑 · 可演示正式运营

目标：**你能在 Admin 里完成一条完整故事**——「我要搞头条自媒体」→ 育成师带出一名运营成员 → 成员执行头条任务 → 财务看到是否有收益信号 → 你决定是否继续。

完成度以 `[ ]` / `[x]` 在迭代时勾选；下列「现状」基于当前仓库（2026-05-24 第 5 轮 · 去硬编码后）。

**自动化验收**：

| 命令 | 含义 |
|------|------|
| `PYTHONPATH=src python3 scripts/m1_ops_check.py` | **P0 8/8**：干净默认环境（无预置成员/财务） |
| 同上 + `--with-worker-smoke` | **P0 + W 全绿**：临时跑头条 A/B/C，**默认清理**冒烟产物 |
| 公司空间启用 `self_media_operations` 后重跑 | **P0 + W 全绿**：持久启用工种，**保留**财务落盘 |

---

## 零、干净默认环境（P0）

| 检查项 | 要求 | 现状 |
|--------|------|------|
| 预置成员 | 无 `self_media_child` | **已通过** |
| 内置角色 | 仅 `talent_development_officer` + 财务节点 | **已通过** |
| 财务脏数据 | 无 `toutiao_default` / `default` / `test` 项目文件 | **已通过** |
| 工种默认 | `self_media_operations` 默认关闭 | **已通过** |

---

## 一、育成师 · 五步闭环

| 步骤 | 产品要求 | 现状 | 相关 API / 模块 |
|------|----------|------|-----------------|
| 1 接目标 | 你在关系层或项目里下达经营目标（如头条自媒体） | 部分 | `POST /api/autonomy/relationship/parent-message` |
| 2 塑人格 | 育成师为岗位成员建档：角色、口吻、长期目标 | 已有 | `POST /api/autonomy/employees`，`PUT /api/autonomy/identity` |
| 3 补知识 | 育成师触发调研/学习，形成可执行认知（非空泛） | 弱 | `POST /api/autonomy/memory-hub/run`，`background_research_runtime` |
| 4 排任务 | 分配正式任务，成员执行工种队列 | 已有 | `POST /api/autonomy/tasks/assign` → 队列 `operation_*` |
| 5 复盘晋级 | 提交 → 育成师批准；判定「可独立承担」或继续训练 | 部分 | `POST /api/autonomy/tasks/submit`，`POST /api/autonomy/tasks/approve`，`POST /api/autonomy/training-review` |

### M1 验收标准（育成师）

- [ ] 新建一名岗位成员（用户通过育成师 `POST /api/autonomy/employees` 创建），人格与训练计划可保存、可回看
- [x] 育成师分配的首个正式任务能进入 `self_media_operations` 队列并产生可读结果
- [x] Memory Hub 巡检后，关系层有一条育成官总结（非空模板）
- [x] UI 上能区分：育成师工作台 vs 子女工作台 vs 公司管理者视图
- [x] 文档化「可独立运营」判定规则（见下方 **可独立运营判定**）

### 可独立运营判定（M1 · 人工批准 + 规则）

成员 `training_plan.independence_criteria` 满足 **全部** 时可由育成师点「批准晋级」：

1. `operation_validate` 最近一次为 `passed`（账号 `logged_in`，执行器 `available`）
2. `operation_analytics` 至少完成 `works` + `income` 各一次，且财务 `GET /api/finance/summary` 有 `updated_at`
3. `operation_publish_draft` 至少一次成功，`draft_path` 文件存在
4. `operation_feedback_collect` 至少一次成功，`headline` 非占位
5. 育成师在 `training-review` 中确认 `training_stage` 为 `stabilizing` 或更高

### 建议实现顺序

1. 在 Admin 启用 `self_media_operations`（Settings → 工种）并添加工种  
2. 固定一条演示租户 + 育成师创建岗位成员  
3. 打通 `tasks/assign` → `operation_validate` → `operation_analytics`  

---

## 二、财务 · 最小数据模型（M1）

财务在 UI 已占位（`admin-ui/src/utils/organization.ts` → `financeNode`），**后端 M1 需新增**（建议路径）：

### 2.1 字段（按项目 / 渠道）

| 字段 | 说明 | 来源（M1） |
|------|------|------------|
| `project_id` | 经营项目，如 `self_media_operations` 或 `member_{id}` | payload / work_type / member 动态解析 |
| `channel` | `toutiao` | 固定 |
| `period` | 日 / 周，如 `2026-05-16` | 汇总键 |
| `revenue` | 平台结算或预估收益（元） | 头条 analytics |
| `cost` | 投放 / 工具 / 人力分摊（M1 可手工录入） | Admin 表单 |
| `views` / `likes` / `comments` | 辅助指标 | analytics |
| `net` | `revenue - cost` | 计算 |
| `verdict` | `profitable` / `break_even` / `loss` / `unknown` | 规则 |

### 2.2 M1 验收标准（财务）

- [x] `GET /api/finance/overview` 与 `GET /api/finance/summary?project_id=` 返回上述结构
- [x] 财务组织节点状态从「未启用」变为「有数据」（需至少一次 analytics 写入）
- [x] 项目看板 `revenueSummary` 展示真实数字（至少一条头条 analytics 写入后）
- [x] 育成师或管理者能看到「本项目本周净收益」一句话结论（`formatFinanceHeadline`）

### 2.3 与现有代码衔接

- 写入点：`operation_analytics` 任务完成回调（`summarize_toutiao_analytics_result`）  
- 读取点：`organization.ts` 构建 `BusinessProjectCard.revenueSummary`  
- 暂不要求完整会计科目；M1 只要**能回答「有没有赚到钱」**

---

## 三、头条工种 · 三个必达任务（W 段 · 需启用后验证）

对应 `openSpec/workers/self_media_operations` + `src/workers/self_media_operations`。**默认关闭**；启用 Worker 或使用 `--with-worker-smoke` 后执行 W 段自检。

| 必达任务 | 类型 | M1 成功标准 | 现状 |
|----------|------|-------------|------|
| **A. 账号可用** | `operation_validate` | 账号 `logged_in`，executor `available` | **W 段可验证** |
| **B. 经营数据** | `operation_analytics` | 拉取阅读/互动等指标并落盘，可供财务读取 | **W 段可验证** |
| **C. 内容闭环** | `operation_publish_draft` + `operation_feedback_collect` | 生成可审草稿；发布后能采集评论/反馈摘要 | **W 段可验证** |

### 相关 API（已有）

| 用途 | API |
|------|-----|
| 账号列表 / 登录 | `GET/POST /api/self-media/toutiao/accounts*` |
| 反馈处理 | `POST /api/tenants/{tenant_id}/feedback/collect` |
| 自治状态 | `GET /api/autonomy/status` |
| 任务创建 | Admin 任务 API / 育成师 assign 触发队列 |

### M1 验收标准（头条 · W 段）

- [ ] A：`operation_validate` probe 为 `passed`（启用 Worker 或 `--with-worker-smoke`）
- [ ] B：`operation_analytics` 完成且财务 `project_id=self_media_operations` 有 `updated_at`
- [ ] C：`operation_publish_draft` 草稿路径有效 + `operation_feedback_collect` 的 `headline` 非占位
- [x] Git export 成功或明确降级为「仅本地 workspace」（`.admin/local_git_exports/`）

### Executor 修复提示

- 工作目录：`executors/toutiao/`，CLI：`scripts/cli.py`  
- 历史错误：`invalid choice: 'default'` → 已修复 publish 子命令参数顺序（2026-05-24 验证）

---

## 四、配置与文档对齐（M1 一并完成）

- [x] `README.md` 改为个人公司叙事  
- [x] 本清单与 `EVO_MAINLINE_STATUS_CN.md`  
- [x] `.config/evo.json`：`domains.javascript.enabled = false`  
- [x] 自治默认 `domain` 从 `javascript` 改为经营/自媒体（`.admin/autonomy_runtime.json` → `operations`）  
- [x] Admin UI 首页默认进入「组织 / 公司」而非技术向面板（`/` → `/dashboard` 公司主览）

---

## 五、M1 完成后的演示脚本（5 分钟）

**前置**：公司空间（`/organization/parent/workspace`）启用「自媒体运营师」→ 保存工种开关 → **重启 Admin**（队列 handler 按 registry 注册）。

1. 登录 Admin → 组织视图：育成师 + 财务（默认无岗位成员）  
2. 育成师工作台 → `POST /api/autonomy/employees` 创建头条运营成员 → 分配正式任务  
3. 子女工作台 / 队列 → 看到 analytics + 草稿/反馈任务成功  
4. 财务 / 项目卡片 → 显示本周收益摘要（非「等待接入」）  
5. 关系层 → 育成官一条复盘消息  

**全部通过 = M1 达成，可对内称为「个人公司智脑 · 首条业务线可运营」。**

> 后端预检：`scripts/m1_ops_check.py`（P0）或 `--with-worker-smoke`（P0+W 且不脏盘）；Admin 5 分钟演示需本地起服务后人工走 UI。

---

## 六、启用工种完整冒烟路径（研发 / 验收）

### 6.1 一键 W 段（不持久启用、不脏数据）

```bash
cd evo-os
PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke
```

默认会在 W 段结束后删除 `self_media_operations` 财务文件与临时草稿，**P0 仍保持 8/8**。

保留产物（调试财务 UI）：

```bash
PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke --keep-smoke-artifacts
```

### 6.2 持久启用（贴近真实运营）

1. **启用 Worker（脚本或 UI）**  
   ```bash
   PYTHONPATH=src python3 scripts/bootstrap_self_media_worktype.py
   ```  
   或 Admin → 公司空间（`/organization/parent/workspace`）→ 工种开关 → 勾选「自媒体运营师」→ 保存

2. **重启 Admin**（`uvicorn` / Docker 容器），使 `operation_*` handler 注册生效。

3. **（可选）添加工种定义**  
   `PUT /api/work-types` 增加 `work_type_id: self_media_operations`（与 Worker manifest 对齐）。

4. **育成师创建成员**  
   `POST /api/autonomy/employees`，body 含 `member_id`、角色、`current_jobs: ["self_media_operations"]` 等。

5. **派任务**  
   `POST /api/autonomy/tasks/assign` → 队列依次跑 `operation_validate` → `operation_analytics` → …

6. **验收**  
   ```bash
   PYTHONPATH=src python3 scripts/m1_ops_check.py   # P0 + W（保留财务落盘）
   curl 'http://localhost:8000/api/finance/overview'
   ```

### 6.3 脏数据清理

| 场景 | 操作 |
|------|------|
| 历史预置财务 | 服务启动自动 `purge_preset_finance_data`；或 `POST /api/finance/purge-preset` |
| W 段临时产物 | 使用 `--with-worker-smoke`（默认清理） |
| 预置成员残留 | 加载 runtime 时过滤 `self_media_child`（见 `runtime_state.py`） |

---

## 七、商业接单消费环（已纳入 P0 探测）

验收口径从「训练票通」升级为「接单可结算」：

1. `/organization/intake` 创建商业任务（预算/报价）  
2. 智脑分析候选（`.admin/intake_routing_policies.json`，capability 驱动）  
3. 育成确认分派 → 员工正式任务  
4. 员工提交 → 育成 approve → intake `delivered`  
5. 接单台结算 → 财务 `channel=commercial` 可见  

自检：`scripts/m1_ops_check.py`（`P0 接单探测*`）；跳过：`EVO_M1_SKIP_INTAKE=1`。  
架构：[INTAKE_ARCHITECTURE_CN.md](INTAKE_ARCHITECTURE_CN.md)。

## 八、M1 之后（不在本清单）

- 财务：多项目、成本分摊、对账导出  
- 育成师：LLM 自动调研与课表  
- 第二工种仅加配置 + worker（intake 核心零改）  
- 经验反哺路由策略  
- 多实例队列 Redis、对外 SLA  
- 生产加固：HTTPS、`SESSION_SECRET`、Session Redis、监控告警
