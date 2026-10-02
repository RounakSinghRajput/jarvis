from config.settings import settings
from security.audit import AuditLog
from security.permissions import PermissionPolicy
from tools.builtin import BUILTIN_TOOLS
from tools.registry import ToolRegistry


def build_registry() -> ToolRegistry:
    registry = ToolRegistry(
        policy=PermissionPolicy(allow_medium=settings.allow_medium_risk),
        audit=AuditLog(),
    )
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
    return registry