# Evo Toutiao Executor

这是 `evo` 自己的最小头条执行器骨架。

目标不是一步把所有真实执行能力都补齐，而是先把执行器接口、账号档案、
草稿产物和后续扩展权掌握在 `evo` 自己手里，再逐步补真实能力。

当前支持的命令骨架：

- `account status`
- `publish weitoutiao --draft`
- `analytics fans|works|income`
- `comment list`
- `comment reply`

默认不会自动接管现有流程。

如果你想显式切到这个执行器，可以：

1. 给 mission/context 传 `executor_dir`
2. 或设置环境变量 `EVO_TOUTIAO_EXECUTOR_DIR`

状态文件：

- `executors/toutiao/data/accounts/<account>.json`

示例：

```json
{
  "account_id": "default",
  "logged_in": false,
  "display_name": "Evo Toutiao",
  "profile_url": "",
  "notes": "set logged_in=true after real login integration"
}
```
