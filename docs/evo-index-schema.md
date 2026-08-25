# Evo Enterprise Index Schema

`evo/index.json` 是企业知识仓给 Evo 自治学习主线提供的统一入口。

它的目标不是单纯“列文件”，而是告诉系统：

- 这里有哪些可复用知识
- 它们属于技能、经验、策略还是报告
- 命中问题时应该优先看哪一条

## Minimal Shape

```json
{
  "schema_version": "1.0",
  "tenant_id": "restore411",
  "generated_at": "2026-04-23T10:00:00",
  "description": "Starter enterprise knowledge index for Evo autonomous learning.",
  "entries": [
    {
      "id": "skill:javascript_dom_signature",
      "type": "skill",
      "title": "javascript_dom_signature",
      "summary": "识别 bundle 中的 DOM 框架签名与初始化模式。",
      "keywords": ["javascript", "reverse", "dom", "signature"],
      "path": "skills/javascript/javascript_dom_signature.json",
      "source": "tenant_local_skill"
    }
  ]
}
```

## Entry Types

- `skill`: 稳定可复用的解决能力
- `experience`: 真实案例中的观察、踩坑、验证结论
- `strategy`: 规则、决策偏好、评估约束
- `report`: 成长报告、学习任务、阶段性产物

## Recommended Fields

- `id`: 条目唯一标识，建议稳定不变
- `type`: `skill | experience | strategy | report`
- `title`: 条目标题
- `summary`: 简洁描述，给自治学习做第一轮召回
- `keywords`: 检索关键词数组
- `path`: 仓库内相对路径
- `source`: 条目来源，例如 `tenant_local_skill`、`tenant_growth_timeline`

## How Evo Uses It

扫描企业仓时，系统会优先查找这些路径：

1. `evo/index.json`
2. `catalog/index.json`
3. `catalog/skills.json`
4. `catalog/experiences.json`
5. `indexes/knowledge.json`
6. `.evo/index.json`

命中后会做两层消费：

1. 仓级候选：判断这个 repo 是否值得优先进入企业私有检索
2. 条目级候选：把匹配到的 `entries[*]` 直接作为自治学习候选方案的一部分

设置页现在支持一键把模板写入目标知识仓：

- 目标路径固定为 `evo/index.json`
- 写入后可直接触发一次扫描，刷新本地索引缓存

## Suggested Layout

```text
evo/index.json
skills/javascript/*.json
experiences/js-reverse/*.json
strategies/*.json
reports/*.json
```

## Notes

- `entries` 不宜过大，建议先保留高价值条目
- 大体积日志、原始样本不要直接塞进 `index.json`
- 大文件放仓库其他目录，`index.json` 只保留摘要和路径
