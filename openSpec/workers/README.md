# External Workers（执行器插件）

**不是「已添加工种」列表。** 用户要在 Admin **添加工种**（`PUT /api/work-types` → `.admin/work_types.json`），再在公司空间启用与本目录 `worker_id` 对应的 Worker。

内置职能只有**育成师**与**财务**；本目录提供可挂载的**实现代码**（handler、Mission 模板等），`default_enabled: false`。

- 测试工种示例：`self_media_operations`（头条 executor，**默认关闭**）
- 模板工种：`crawler`、`android`

把项目级或企业级工种放到这里：

- `openSpec/workers/<worker_id>/definition.py`
- 或者 `workspace/.admin/workers/<worker_id>/definition.py`

系统会自动扫描 `WORKER_DEFINITION`，并把它并入工种注册表。

最小结构：

```python
WORKER_DEFINITION = {
    "manifest": {
        "worker_id": "crawler",
        "title": "Crawler",
        "capability_type": "automation",
        "work_type_ids": ["crawler"],
        "task_types": ["crawl_collect"],
        "owned_modules": ["runtime"],
        "default_enabled": False,
    },
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_worker_mission_node,
    "mission_summary_handler": build_worker_mission_summary,
}
```

建议：

- 先把 `default_enabled` 设为 `False`
- 先返回空 handlers 或最小 handlers，确认系统能识别
- 等工种 runtime 稳定后，再在后台把它启用

示例工种：

- `openSpec/workers/crawler/definition.py`
- `openSpec/workers/android/definition.py`
