"""
Evo 平台自检入口

加载配置、注册能力包与插件，并对 JavaScript 能力做冒烟测试（不启动 HTTP）。
生产入口为 src/admin/server.py。
"""

import sys
from pathlib import Path

# 添加源码路径
sys.path.insert(0, str(Path(__file__).parent))

from core import get_distributed_config, get_capability_registry, DecisionEngine, PluginLoader
from project_caps import (
    load_project_packages,
    register_project_capabilities,
    register_project_orchestration,
)


def main():
    """主入口"""
    print("=" * 50)
    print("Evo 平台自检")
    print("=" * 50)
    print()
    print("核心能力:")
    print("  - 分布式存储 (Gitee)")
    print("  - AI 学习进化")
    print("  - 多租户隔离")
    print("  - 可插拔能力协议")
    print()
    print("配置文件: .config/evo.json")
    print("=" * 50)
    
    # 加载配置验证
    config = get_distributed_config(Path.cwd())
    print(f"✅ 配置加载成功")
    print(f"   Platform: {config.platform} v{config.version}")
    print(f"   Registry: {config.registry.full_name}")
    print()

    registry = register_project_capabilities(Path.cwd(), get_capability_registry())
    register_project_orchestration(Path.cwd())
    project_packages = load_project_packages(Path.cwd())
    plugin_summary = PluginLoader(capability_registry=registry).load_default(Path.cwd())
    decision_engine = DecisionEngine(Path.cwd(), registry)
    descriptors = registry.list_descriptors()
    print("已注册能力:")
    for descriptor in descriptors:
        print(f"  - {descriptor.id} ({descriptor.provider_kind}) -> tasks={descriptor.supported_tasks}")
    print()
    print("项目能力包:")
    for item in project_packages.get("packages", []):
        if not isinstance(item, dict):
            continue
        print(f"  - {item.get('package_id')} enabled={item.get('enabled', True)} adapter={item.get('adapter')}")
    print()
    print("插件加载:")
    if plugin_summary.loaded:
        for item in plugin_summary.loaded:
            print(f"  - {item.plugin_name}: strategies={item.strategies}, evaluators={item.evaluators}, capabilities={item.capabilities}")
    else:
        print("  - 无已加载插件")
    if plugin_summary.skipped:
        for item in plugin_summary.skipped:
            print(f"  - skipped: {item}")
    print()

    # 测试 JavaScript 项目能力包
    print("测试 JavaScript 项目能力包...")
    test_workspace = Path.cwd() / ".test_workspace"
    test_workspace.mkdir(exist_ok=True)

    js_provider = registry.get("builtin.javascript")

    # 初始化
    result = js_provider.init_workspace(test_workspace, "test")
    print(f"   ✅ 初始化: {result['status']}")
    
    # 创建测试文件
    test_bundle = test_workspace / "input" / "test.js"
    test_bundle.parent.mkdir(exist_ok=True)
    test_bundle.write_text("""
import { createApp } from 'vue';
import { Button } from 'antd';
const app = createApp({});
app.use(Button);
""")
    
    # 分析
    result = decision_engine.execute(
        task_type="analyze",
        workspace=test_workspace,
        tenant_id="test",
        input_path=test_bundle,
        parameters={"preferred_tags": ["javascript"]},
    ).to_dict()
    print(f"   ✅ 分析完成:")
    print(f"      Frameworks: {result['frameworks']}")
    print(f"      Libraries: {[lib['name'] for lib in result['libraries']]}")
    print(f"      Confidence: {result['confidence']}")
    print(f"      Selected Capability: {result['feedback']['decision']['selected_capability_id']}")
    if result["feedback"]["decision"].get("strategy"):
        print(f"      Strategy: {result['feedback']['decision']['strategy']['strategy_id']}")
    if result["feedback"].get("evaluation"):
        print(f"      Evaluation: {result['feedback']['evaluation']['verdict']} ({result['feedback']['evaluation']['score']:.2f})")

    reconstruct_result = decision_engine.execute(
        task_type="reconstruct",
        workspace=test_workspace,
        tenant_id="test",
        input_path=test_bundle,
        source_dir=test_workspace / "input",
        parameters={
            "preferred_tags": ["javascript"],
            "analysis_result": result,
        },
    ).to_dict()
    print(f"   ✅ 重构完成:")
    print(f"      Target Dir: {reconstruct_result['target_dir']}")
    print(f"      Selected Capability: {reconstruct_result['feedback']['decision']['selected_capability_id']}")
    if reconstruct_result["feedback"]["decision"].get("strategy"):
        print(f"      Strategy: {reconstruct_result['feedback']['decision']['strategy']['strategy_id']}")
    if reconstruct_result["feedback"].get("evaluation"):
        print(f"      Evaluation: {reconstruct_result['feedback']['evaluation']['verdict']} ({reconstruct_result['feedback']['evaluation']['score']:.2f})")
    
    print()
    print("=" * 50)
    print("Evo 平台自检完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
