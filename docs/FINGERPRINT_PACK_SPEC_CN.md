# 指纹包规范（插件化）

## 目标
- 将“框架/三方库识别知识”从核心代码中解耦。
- 新增识别能力时，仅新增或修改 `spec/fingerprint_packs/*.json`，不改主流程命令实现。

## 目录约定
- 指纹包目录：`spec/fingerprint_packs/components/`
- 注册表：`spec/fingerprint_registry.json`
- 每个 JSON 文件建议对应“一个组件/一类库”。
- 规则总站加载器：`src/engine/restorex_lib/fingerprint_registry.py`

## 加载与合并规则
- 优先读取注册表 `spec/fingerprint_registry.json` 的 `packs[]`。
- 加载顺序：`priority` 升序，再按 `id` 升序。
- 合并策略：
  - `library_match_rules`：深合并。
  - `third_party_fingerprints/signal_rules/framework_rules`：数组追加 + 去重。
- 无注册表时，回退到 `spec/fingerprint_packs/**/*.json` 递归加载。
- 结构约束：
  - `library_match_rules` 必须是对象
  - `third_party_fingerprints` 必须是数组
  - `signal_rules` 必须是数组
  - `framework_rules` 必须是数组

## pack 顶层结构
```json
{
  "library_match_rules": {
    "some-lib": {
      "filename_hints": [],
      "module_signature": [],
      "export_shape": [],
      "runtime_helper_pattern": [],
      "css_marker": [],
      "text_markers": []
    }
  },
  "third_party_fingerprints": [],
  "signal_rules": [],
  "framework_rules": []
}
```

## match 语法（通用）
- `path_contains`: 路径包含（数组，任一命中）
- `text_contains`: 文本包含（数组，全部命中）
- `compact_contains`: 去空白文本包含（数组，全部命中）
- `text_regex`: 原文本正则（数组，任一命中）
- `compact_regex`: 去空白文本正则（数组，任一命中）
- `ext_in`: 后缀限定（数组）
- `all`: 组合子规则（数组，全部命中）
- `any`: 组合子规则（数组，任一命中）

## 置信度建议
- `high`：至少 2 类结构证据，且冲突可裁决。
- `medium`：1 类结构证据 + 辅助文本证据。
- `low`：仅文本证据（默认不建议自动应用改写）。

## 设计建议
- 先放“结构特征”，后放“文本关键字”。
- 优先写“项目无关”信号，避免业务词。
- 同一库尽量拆成“命中规则 + 判定说明 + 证据字段”，保证可追溯。

## 注册表结构
```json
{
  "version": "1.0",
  "packs": [
    {
      "id": "state_pinia",
      "path": "spec/fingerprint_packs/components/state_pinia.json",
      "enabled": true,
      "priority": 30
    }
  ],
  "remote": {
    "enabled": false,
    "source": "",
    "branch": "main",
    "subdir": "spec/fingerprint_packs/components"
  }
}
```

## 最小流程
1. 新建组件 pack：`spec/fingerprint_packs/components/<name>.json`。
2. 注册到 `spec/fingerprint_registry.json`。
3. 通过 MCP 调用 `restorex_extract_fingerprints` 工具执行分析。
4. 检查输出：
   - `analysis/library_matches.json`
   - `analysis/library_match_quality.json`
   - `analysis/third_party_fingerprint.json`
5. 若误判，先调 pack 规则，不改核心引擎。

## MCP 调用方式
通过 `restorex_extract_fingerprints` Tool 执行指纹提取：
```json
{
  "tool": "restorex_extract_fingerprints",
  "params": {
    "run_id": "run_xxx",
    "min_confidence": 0.7
  }
}
```
