# Restore Workbench 分层边界说明

## 核心原则

1. **核心引擎层（`src/engine/`）禁止写入任何项目特定信息**
2. **`spec/` 目录用于指纹规范，`config/` 用于流程配置，运行时数据在 `cache/`**
3. **画像层持久化，不随 `output/` 清空丢失**
4. **还原产物层可随时清空重建**
5. **所有通用配置来自文件，引擎不写代码兜底**

---

## 目录结构

```
restorex-mcp/                      ← MCP 服务项目（本仓库）
├── src/
│   ├── mcp/                      ← MCP 服务层
│   └── engine/                   ← 核心引擎（通用，不跟项目走）
├── input/                         ← 输入包（唯一输入源）
├── cache/                         ← 所有缓存（分四类）
│   ├── remote/                    ← 服务器拉取的通用配置（首次运行时拉取）
│   │   ├── rename_rules.json      ← 通用改名规则（必须存在）
│   │   ├── chain_rules.json       ← 通用链路规则（必须存在）
│   │   ├── library_match_rules.json
│   │   ├── module_rules.json
│   │   ├── portrait_rules.json
│   │   ├── reconstruct_rules.json
│   │   ├── origin_labels.json
│   │   ├── pipeline_contract.json
│   │   ├── fingerprint_registry.json
│   │   ├── fingerprint_packs/     ← 通用指纹包
│   │   └── profiles/              ← 通用档位配置（strict/balanced/aggressive）
│   ├── project/                   ← 扫描项目生成的配置（每个项目一份）
│   │   ├── semantic_rules.json    ← 扫描项目代码生成的语义规则
│   │   └── project_hints.json     ← 扫描项目生成的模块名/hotspot等
│   ├── portraits/                 ← 画像产物（扫描 input/ 生成，持久化）
│   │   ├── file_portraits.json
│   │   ├── class_portraits.json
│   │   ├── method_portraits.json
│   │   ├── constant_portraits.json
│   │   └── */（子目录）
│   └── fingerprints/              ← 指纹匹配产物（持久化）
└── output/                        ← 每次 run 的还原产物（可清空重建）
    └── run_<id>/
        ├── baseline/              ← 输入快照
        ├── analysis/              ← 基于画像推导的证据/映射（可重建）
        ├── restore_v1/            ← 还原代码
        ├── reconstructed_project/ ← 测试/重建代码
        └── reports/               ← 报告
```

---

## 四类缓存说明

### `cache/remote/` — 服务器拉取的通用配置
- **来源**：首次运行时从服务器拉取，或随引擎版本更新
- **特点**：适用所有项目，不含项目特定信息
- **清空策略**：版本升级时更新，不随项目切换清空

### `cache/project/` — 扫描项目生成的配置
- **来源**：引擎扫描 `input/` 后自动生成
- **特点**：每个项目一份，包含该项目的语义规则和模块提示
- **清空策略**：切换项目时清空，重新扫描生成

### `cache/portraits/` — 画像产物
- **来源**：引擎扫描 `input/` 后生成的文件/类/方法/常量画像
- **特点**：跨 run 复用，不随 `output/` 清空
- **清空策略**：`input/` 更新时重新生成

### `cache/fingerprints/` — 指纹匹配产物
- **来源**：引擎对 `input/` 做指纹匹配后生成
- **特点**：跨 run 复用
- **清空策略**：`input/` 更新时重新生成

---

## 分层隔离规则

| 操作 | 允许 | 禁止 |
|---|---|---|
| 核心引擎读取 `cache/remote/` | ✅ | |
| 核心引擎读取 `cache/project/` | ✅ | |
| 核心引擎硬编码项目信息 | | ❌ |
| 核心引擎硬编码配置兜底值 | | ❌ |
| 画像写入 `cache/portraits/` | ✅ | |
| 画像写入 `output/run_xxx/` | | ❌ |
| 清空 `output/` | ✅ | |
| 清空 `cache/project/` + `cache/portraits/` | 切换项目时 | |
| 清空 `cache/remote/` | 版本升级时 | |
| `spec/` 目录 | 指纹规范 | ✅ |
