from typing import NamedTuple

from tools.base import RiskLevel, Tool


class Decision(NamedTuple):
    allowed: bool
    reason: str


class PermissionPolicy:
    """Decides whether a tool may run. Every tool call goes through here."""

    def __init__(self, allow_medium: bool = True) -> None:
        self._allow_medium = allow_medium

    def check(self, tool: Tool, args: dict) -> Decision:
        if tool.risk is RiskLevel.LOW:
            return Decision(True, "low risk: runs automatically")
        if tool.risk is RiskLevel.MEDIUM:
            if self._allow_medium:
                return Decision(True, "medium risk: allowed by settings")
            return Decision(False, "medium-risk tools are switched off in settings")
        # HIGH and CRITICAL: blocked until the confirmation flow exists.
        return Decision(False, f"{tool.risk.value}-risk tools need user confirmation, which is not available yet")