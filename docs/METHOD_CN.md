# RestoreX 方法说明（通用）

## 目标
把编译产物还原成“可追溯、可复跑、可阅读”的标本工程，且不依赖任何项目历史产物。

## 方法主线
1. 输入冻结：`input` 是唯一数据源，先冻结 baseline。
2. 规范化副本：格式化在 `normalized_working_copy` 内进行，原始快照只读。
3. 编译成因判定：先判断是构建器、框架编译、第三方库还是业务层。
4. 结构扫描：入口、依赖、模块边界与引用图。
5. 链路抽取：触发点 -> 状态点 -> 桥接点 -> UI 点。
6. 证据矩阵：每条结论都具备“猜测 -> 证据 -> 验证”。
7. 双轨输出：`raw_runtime` 保真，`readable` 可读。
8. 运行时补证（可选）：导入 runtime evidence 提升链路置信度。
9. 验证与冻结：校验后生成交接包。

## 重命名策略
- 仅 `app_business + high confidence` 自动改名，且短名必须为 `a~z` 1~2 字符。
- `medium/low` 只出候选映射，不自动改。
- 禁改：协议字段、命令名、事件名、用户可见文案。
- finalize 阶段会输出 `suspicious_renames`：短符号却出现高替换次数，作为“过拟合改名”风险提示。
- 可通过 `suspicious_rename_constraints` 开启硬闸门：命中可疑条件时直接阻断落盘改名。

## 运行时策略
默认静态优先。运行时证据只补强置信度，不直接改写源码。
推荐输入格式：
- 顶层为对象，包含 `items` 数组。
- 每个条目建议包含：`chain_id`、`source`、`file`、`line`、`detail`。
- 最低要求仅 `chain_id`，其余字段可选。

## 规则配置
- `spec/rename_rules.json` 控制候选过滤、自动改名门槛与禁改词。
- `spec/chain_rules.json` 控制链路抽取前缀、层过滤与桥接 scheme。
- `spec/chain_rules.json` 的 `extract_constraints` 可配置链路最小置信度、是否必须桥接调用、最小 UI 引用数。
- `spec/profiles/*.json` 控制档位覆盖（strict / balanced / aggressive）。
