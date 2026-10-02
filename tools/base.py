from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"            # read-only or harmless: runs automatically
    MEDIUM = "medium"      # changes something small: allowed by default, configurable
    HIGH = "high"          # needs confirmation (confirmation flow comes later)
    CRITICAL = "critical"  # payments, destructive actions: confirmation + authentication


class ToolError(Exception):
    """An expected failure. The message is safe to show the AI and the user."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str                 # the AI reads this to decide when to use the tool
    parameters: dict | None          # JSON schema for the arguments (None = no arguments)
    risk: RiskLevel
    run: Callable[[dict], str]       # does the work and returns a short text result