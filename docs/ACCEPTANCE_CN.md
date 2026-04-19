# 验收标准（通用）

## 通用性
- 同一插件可在不同输入包目录运行。
- 不依赖项目专有常量或历史还原目录。

## 正确性
- baseline hash 与输入 manifest 一致。
- `build_origin_report.json` 每条记录包含：
  - `file`, `origin_label`, `confidence`, `signals[]`, `counter_evidence[]`, `status`
- `chain_graph.json` 链路记录包含：
  - `chain_id`, `trigger`, `state_ops[]`, `bridge_calls[]`, `ui_refs[]`, `confidence`
- `rename_plan_focus.json` 包含每个候选是否自动应用及原因。

## 可用性
- `restore_v1/readable/pages/index.html` 存在。
- `reconstructed_project/src/main.ts` 存在，且 `reconstructed_project/src/meta/chunk-map.json` 可追溯到业务文件映射。
- 若 run 配置 `emit_raw_runtime=true`，`restore_v1/raw_runtime/pages/index.html` 需存在。
- `mapping_index.json` 能反查 raw 与 readable 路径映射。
- `library_matches.json` 与 `business_symbol_pool.json` 存在，用于库剥离与业务聚焦。
- `compare-profiles` 可输出 profile 对比报告（json/md）。
- `compare-runs` 可对已存在 run 做对比（不重复执行流水线）。
- `final_summary.json/md` 存在，且包含风险与下一步建议。
- `final_summary.json` 建议包含 `suspicious_renames`（短符号高替换次数告警）。
- strict 档位下，`mapping_index.json` 应包含 `blocked_suspicious_renames` 且可追溯被阻断项。

## 安全边界
- 禁改白名单零违规。
- 低置信候选不自动落盘。
- `verify_report` 包含 `rename_plan_consistency` 检查且应为 `ok=true`。
