# 本地启动指南

产品主线：**个人公司商业智脑**（接单台 + 育成师≈CTO + 财务 + 岗位工种）。启动后请从 Admin **接单台 / 组织 / 育成师 / 岗位成员** 进入，不要以 `src/server.py` 的 JS 冒烟作为产品验收。详见 [docs/PRODUCT_M1_CHECKLIST_CN.md](docs/PRODUCT_M1_CHECKLIST_CN.md)、[docs/INTAKE_ARCHITECTURE_CN.md](docs/INTAKE_ARCHITECTURE_CN.md)。

## 1. 环境

```bash
cd /path/to/evo-mcp
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Gitee OAuth / TOKEN（Admin 登录与 Git）
```

## 2. 平台自检（可选 · 研发用）

在**仓库根目录**执行（需存在 `.config/evo.json`，可从 `evo.json.example` 复制）：

```bash
export PYTHONPATH=src
python3 src/server.py
```

仅用于能力包注册冒烟（含内置 JS 插件检测）；**与「个人公司 M1」验收无关**。会创建 `.test_workspace/`。

## 3. Admin API（开发）

```bash
cd src
export PYTHONPATH=.
export EVO_ADMIN_WORKSPACE=/path/to/your/workspace   # 可选，默认仓库根

python3 -m uvicorn admin.server:create_app --host 0.0.0.0 --port 8000 --reload --factory
```

浏览器访问 http://localhost:8000 。前端开发见 `admin-ui/`（`npm run dev`，代理到 8000）。

## 4. Docker

```bash
cp .env.example .env
docker compose up -d evo-admin
# 可选：单独扩容任务消费者
docker compose up -d evo-worker
```

详见 [ADMIN_README.md](ADMIN_README.md)。

## 6. M1 运营验收

```bash
# P0：干净默认环境 + 接单消费环探测
PYTHONPATH=src python3 scripts/m1_ops_check.py

# P0 + W：工种冒烟，默认不留下财务/草稿脏数据
PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke

# 快速跳过长探测
EVO_M1_SKIP_EVOLUTION=1 EVO_M1_SKIP_INTAKE=1 PYTHONPATH=src python3 scripts/m1_ops_check.py
```

UI 商业路径：`/organization/intake` → 分派 → 员工工作台 → 结算 → `/organization/finance`。  
详见 [docs/PRODUCT_M1_CHECKLIST_CN.md](docs/PRODUCT_M1_CHECKLIST_CN.md) 第六节与第七节。

## 5. 目录说明

| 路径 | 作用 |
|------|------|
| `.config/` | 平台配置 `evo.json` |
| `.admin/` | 运行时状态（gitignore） |
| `.queue/` | 任务队列（gitignore） |
| `.tenants/` | 租户数据（gitignore） |
| `evo_workbench/` | Docker 示例工作区挂载点 |
| `plugins/` | 可插拔能力扩展 |
| `executors/` | 外部执行器（如自媒体） |
| `openSpec/workers/` | 工种 OpenSpec |
