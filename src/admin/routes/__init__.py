from .auth import register_auth_routes
from .evolution_strategy import register_evolution_strategy_routes
from .catalog import register_catalog_routes
from .finance import register_finance_routes
from .git_knowledge import register_git_knowledge_routes
from .missions import register_mission_routes
from .self_media import register_self_media_routes
from .system_runtime import register_system_runtime_routes
from .task_tools import register_task_tool_routes
from .tenant_policies import register_tenant_policy_routes

__all__ = [
    "register_auth_routes",
    "register_evolution_strategy_routes",
    "register_catalog_routes",
    "register_finance_routes",
    "register_git_knowledge_routes",
    "register_mission_routes",
    "register_self_media_routes",
    "register_system_runtime_routes",
    "register_task_tool_routes",
    "register_tenant_policy_routes",
]
