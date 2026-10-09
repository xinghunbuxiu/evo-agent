# Evo 个人公司智脑 - 架构文档

> **产品主线**见 [README.md](README.md) 与 [docs/PRODUCT_M1_CHECKLIST_CN.md](docs/PRODUCT_M1_CHECKLIST_CN.md)：个人公司 · 育成师 + 财务 + 工种。  
> 本文档描述**技术分层**，供开发参考。

## 项目概述

**Evo** — 个人公司智脑（仓库 `evo-os`）的技术实现：Admin 编排、任务队列、经验与 Git 知识容器；首条工种为头条自媒体（`self_media_operations`）。内置 `domains/javascript` 等能力包默认关闭，仅作研发扩展。

## 分层架构

```
evo-os/
├── src/
│   ├── core/                    # 核心平台层（跨领域通用）
│   │   ├── config.py           # 分层配置管理
│   │   ├── storage.py          # 分布式存储
│   │   ├── learning.py         # AI 学习引擎
│   │   └── tenant.py           # 多租户管理
│   │
│   └── domains/                 # 领域专用层
│       ├── javascript/         # JS 代码分析 ✅
│       │   ├── analyzer.py
│       │   ├── fingerprint.py
│       │   ├── reconstructor.py
│       │   └── commands.py
│       │
│       ├── android/            # APK 逆向 ⏳
│       ├── pc/                 # 二进制分析 ⏳
│       └── dev/                # 开发辅助 ⏳
│
├── .config/
│   └── evo.json               # 核心配置
└── src/server.py              # 平台自检（冒烟，非 HTTP 服务）
```

## 核心层 (Core)

### 1. 配置管理 (`config.py`)

**分层配置架构：**
- 核心配置 (`evo.json`) - 所有领域共享
- 领域配置 (`{domain}.json`) - 继承核心并扩展

**配置优先级：**
```
代码默认值 < 配置文件 < 环境变量
```

**环境变量：**
```bash
EVO_CONFIG_PATH=/path/to/config.json
EVO_REGISTRY_OWNER=custom-org
EVO_GITEE_API=https://gitee.com/api/v5
```

### 2. 分布式存储 (`storage.py`)

**统一存储接口：**
- 经验存储 (experiences) - 跨领域共享学习经验
- 知识存储 (knowledge) - 通用技能/策略
- 领域存储 (domains/{name}/) - 各领域的专用数据

**分片支持：**
```python
from core import ShardedStore, ShardConfig

store = ShardedStore(
    base_path=workspace / "shards",
    config=ShardConfig(shard_count=4)
)
```

### 3. AI 学习引擎 (`learning.py`)

**核心组件：**
- `Experience` / `ExperienceStore` - 经验记录
- `Strategy` / `StrategyEngine` - 策略管理
- `SkillGenerator` / `SkillExecutor` - 技能系统

### 4. 多租户 (`tenant.py`)

```python
from core import TenantManager

mgr = TenantManager(workspace)
tenant = mgr.create_tenant(
    tenant_id="team-a",
    name="Team A",
    domains=["javascript", "android"]
)
```

## 领域层 (Domains)

### JavaScript 领域 (`domains/javascript/`)

**已完整实现：**

```python
from domains import javascript as js

# 1. 初始化
js.init_workspace(Path("./workspace"), "tenant-1")

# 2. 分析
result = js.analyze_bundle(
    workspace=Path("./workspace"),
    bundle_path=Path("./app.js"),
    tenant_id="tenant-1"
)
# 返回: frameworks, libraries, patterns, fingerprints

# 3. 重构
js.reconstruct_project(
    workspace=Path("./workspace"),
    analysis_result=result,
    source_dir=Path("./input"),
    tenant_id="tenant-1"
)
```

**特点：**
- AI 生成指纹（非预定义）
- 分布式指纹库存储
- 经验自动记录到 evo-experiences

## 配置文件

### 核心配置 (`.config/evo.json`)

```json
{
  "version": "2.0",
  "platform": "evo",
  "gitee_api_base": "https://gitee.com/api/v5",
  "repos": {
    "registry": "evo-project/evo-registry",
    "experiences": "evo-project/evo-experiences",
    "knowledge": "evo-project/evo-knowledge"
  },
  "domains": {
    "javascript": {
      "enabled": true,
      "repos": {
        "fingerprints": "evo-javascript-fingerprints"
      }
    },
    "android": {
      "enabled": false,
      "repos": {
        "fingerprints": "evo-android-fingerprints"
      }
    }
  }
}
```

## 与 Hermes Agent 的关系

| 特性 | Hermes Agent | Evo Platform |
|------|-------------|--------------|
| 定位 | 通用 AI 助手 | 专业分析平台 |
| 场景 | 对话/任务 | 代码/二进制分析 |
| 架构 | 单机 SQLite | 分布式 Gitee |
| 扩展 | 插件技能 | 领域模块 |
| 关系 | 可选前端 | 核心后端 |

**集成方式：**
```python
# Hermes Agent 调用 Evo 作为技能
@hermes.skill("analyze_javascript")
def analyze_js(code: str) -> dict:
    return evo.domains.javascript.analyze(code)
```

## 未来扩展

### 添加新领域

1. 创建目录 `src/domains/{name}/`
2. 实现 `__init__.py`, `analyzer.py`, `commands.py`
3. 在 `evo.json` 添加领域配置
4. 领域自动继承核心层的存储和学习能力

### 领域复用核心能力

```python
# 自动获得的能力
from core import (
    get_distributed_config,  # 统一配置
    UnifiedDistributedStore,  # 分布式存储
    ExperienceStore,         # 经验记录
    SkillGenerator,          # AI 技能生成
    TenantManager,           # 多租户
)
```

## 运行测试

```bash
cd evo-os
PYTHONPATH=src python3 src/server.py
```

会打印配置、已注册能力包，并在 `.test_workspace/` 下对 JavaScript 分析/重构做冒烟。

生产 HTTP 服务：

```bash
cd src
python3 -m uvicorn admin.server:create_app --port 8000 --factory
```
