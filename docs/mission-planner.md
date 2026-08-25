# Mission Planner

Mission Planner 是 Evo 从“固定流水线”升级到“目标驱动自治”的第一层。

## New Mainline

不是：

- 用户提一个目标
- 人工指定走哪条流水线

而是：

1. 用户提交目标
2. 系统自动识别 mission kind
3. 自动拆成 task nodes
4. 逐节点盘点：
   - 有没有现成能力
   - 有没有已有经验
   - 哪些节点需要补学习
5. 形成建议动作
6. 再进入执行、验证、沉淀

## Current Mission Kinds

- `javascript_reverse`
- `automation_operation`

后续可以继续扩：

- `crawler_operation`
- `document_parse_delivery`
- `android_reverse`

## Node Status

- `reuse_existing`
  现成能力和经验都比较充分，优先直接执行

- `ready`
  有能力入口，但经验还不厚，适合先做小实验

- `needs_learning`
  当前没有直接覆盖的能力或经验，需要先补缺口

## Value

这样系统的成长不再依赖提前写死所有规则，而是围绕真实目标自己判断：

- 哪些能直接做
- 哪些要先学
- 学完后如何回写为经验、技能、策略

这才是后续“做一个案例，就让系统更强一次”的核心飞轮。
