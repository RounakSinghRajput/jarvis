import logging
import time

from security.audit import AuditLog
from security.permissions import PermissionPolicy
from tools.base import Tool, ToolError

logger = logging.getLogger("jarvis.tools")


class ToolRegistry:
    def __init__(self, policy: PermissionPolicy, audit: AuditLog) -> None:
        self._tools: dict[str, Tool] = {}
        self._policy = policy
        self._audit = audit

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def declarations(self) -> list[dict]:
        """What we tell the AI model: the name, purpose, and arguments of each tool."""
        result = []
        for tool in self._tools.values():
            declaration = {"name": tool.name, "description": tool.description}
            if tool.parameters:
                declaration["parameters"] = tool.parameters
            result.append(declaration)
        return result

    def execute(self, name: str, args: dict) -> dict:
        """Run a tool through every safety check. Always returns a dict, never raises."""
        started = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            self._log(name, args, "unknown", "denied", False, started, "no such tool")
            return {"error": f"There is no tool called '{name}'."}

        required = (tool.parameters or {}).get("required", [])
        missing = [key for key in required if key not in args]
        if missing:
            self._log(name, args, tool.risk.value, "denied", False, started, f"missing {missing}")
            return {"error": f"Missing arguments: {', '.join(missing)}"}

        decision = self._policy.check(tool, args)
        if not decision.allowed:
            self._log(name, args, tool.risk.value, "denied", False, started, decision.reason)
            return {"error": f"Not allowed: {decision.reason}"}

        try:
            output = tool.run(args)
            self._log(name, args, tool.risk.value, "allowed", True, started, output)
            return {"result": output}
        except ToolError as exc:
            self._log(name, args, tool.risk.value, "allowed", False, started, str(exc))
            return {"error": str(exc)}
        except Exception as exc:
            logger.exception("Tool %s crashed", name)
            self._log(name, args, tool.risk.value, "allowed", False, started, f"crashed: {exc}")
            return {"error": "The tool failed unexpectedly."}

    def _log(self, name, args, risk, decision, ok, started, detail) -> None:
        self._audit.record(
            tool=name,
            args=args,
            risk=risk,
            decision=decision,
            ok=ok,
            ms=int((time.perf_counter() - started) * 1000),
            detail=str(detail)[:200],
        )
        logger.info("Tool %s -> %s (%s)", name, decision, "ok" if ok else "failed")