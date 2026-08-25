# 指纹包规范（插件化）

## 目标

- 将「框架/三方库识别知识」从核心代码中解耦
- 新增识别能力时，优先新增或修改指纹包 JSON，少改 `domains/javascript` 主流程

## 目录约定

- 指纹包目录：`spec/fingerprint_packs/components/`（工作区内，或由分布式存储同步）
- 注册表：`spec/fingerprint_registry.json`
- 加载与生成逻辑：`src/domains/javascript/fingerprint.py`（`FingerprintManager`）
- 租户缓存：`<workspace>/.cache/fingerprints/<tenant_id>/`

## 加载与合并规则

- 优先读取注册表 `spec/fingerprint_registry.json` 的 `packs[]`
- 加载顺序：`priority` 升序，再按 `id` 升序
- 合并策略：
  - `library_match_rules`：深合并
  - `third_party_fingerprints` / `signal_rules` / `framework_rules`：数组追加 + 去重
- 无注册表时，回退到 `spec/fingerprint_packs/**/*.json` 递归加载

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

## 最小流程

1. 新建组件 pack：`spec/fingerprint_packs/components/<name>.json`
2. 注册到 `spec/fingerprint_registry.json`
3. 先完成 JS **analyze**（决策引擎或 Admin 任务）
4. 调用 Admin API 生成指纹：

```http
POST /api/fingerprint/generate
Content-Type: application/json

{
  "tenant_id": "default",
  "analysis_result": { ... }
}
```

5. 列出指纹：`GET /api/fingerprint/list?tenant_id=default`
6. 若误判，先调 pack 规则，再考虑改 `analyzer.py`

## 置信度建议

- `high`：至少 2 类结构证据，且冲突可裁决
- `medium`：1 类结构证据 + 辅助文本证据
- `low`：仅文本证据（默认不建议自动应用改写）
