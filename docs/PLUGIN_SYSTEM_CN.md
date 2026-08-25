# Evo 插件系统

## 目标

插件系统用于支持企业或第三方在不修改 `core` 和内置能力代码的前提下，扩展：

- capability providers
- strategy providers
- evaluator providers

## 默认插件目录

当前默认查找顺序：

1. 环境变量 `EVO_PLUGIN_DIRS`
2. `<workspace>/plugins`

`EVO_PLUGIN_DIRS` 支持多个目录，使用系统路径分隔符连接。

## 插件结构

每个插件建议使用独立目录，最小结构：

```text
plugins/
  your_plugin/
    manifest.json
    plugin.py
```

其中：

- `manifest.json` 为必需文件
- `plugin.py` 为插件入口文件

最小 manifest 示例：

```json
{
  "name": "your-plugin",
  "version": "0.1.0",
  "compatibility": {
    "evo": ">=0.1.0"
  }
}
```

## 插件入口

`plugin.py` 必须导出：

```python
def register():
    return {
        "capabilities": [...],
        "strategies": [...],
        "evaluators": [...],
    }
```

三个列表都可以为空，但 `register()` 必须存在，并返回字典。

## manifest 作用

当前 `manifest.json` 至少用于提供：

- 插件唯一名称
- 插件版本
- 与 Evo Core 的兼容性声明

后续可以继续扩展：

- 权限边界
- 签名与来源
- 企业发行渠道

## 示例

仓库内已提供一个最小示例：

- [plugins/example_js_extension/plugin.py](../plugins/example_js_extension/plugin.py)

它演示了：

- 为 `builtin.javascript` 注册一个企业策略
- 注册一个示例 evaluator

## 启动行为

`src/server.py` 与 `src/admin/server.py` 启动时都会：

1. 注册内置 capability/strategy/evaluator
2. 调用 `PluginLoader`
3. 把插件提供的扩展注册到全局 registry

## 设计原则

- `core` 负责协议和加载机制
- `builtin` 负责官方默认实现
- `plugins` 负责企业/第三方扩展

这意味着未来企业可以只替换策略和评估器，不一定要重写 capability。

## 租户级插件启停

插件现在支持按租户启用/禁用。

租户配置文件路径：

- `.tenants/<tenant_id>/tenant.json`

配置示例：

```json
{
  "config": {
    "plugins": {
      "enabled": ["example-js-extension"],
      "disabled": []
    }
  }
}
```

规则如下：

- 内置 builtin 能力不受插件策略影响，始终可用
- 如果 `disabled` 命中插件名，则该插件不可参与决策
- 如果 `enabled` 非空，则只有在 `enabled` 中的插件才允许参与
- capability、strategy、evaluator 都会经过同一套租户过滤逻辑

## 后续建议

- 增加 manifest 兼容性校验与版本拒绝策略
- 增加插件隔离和权限边界
- 支持从远程仓库同步插件
- 支持插件市场和企业私有分发
