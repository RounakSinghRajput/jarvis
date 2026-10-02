import datetime
import re
import subprocess

from tools.base import RiskLevel, Tool, ToolError

# Letters, digits, spaces and a few symbols. No slashes or quotes, so nothing can be sneaked in.
APP_NAME = re.compile(r"^\w[\w .&+\-]{0,59}$")


def _get_current_time(_args: dict) -> str:
    now = datetime.datetime.now().astimezone()
    return now.strftime("%A, %d %B %Y, %I:%M %p (%Z)")


def _get_battery_status(_args: dict) -> str:
    try:
        output = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5
        ).stdout
    except (subprocess.TimeoutExpired, OSError):
        raise ToolError("I couldn't read the battery status.")
    match = re.search(r"(\d+)%;\s*([^;]+)", output)
    if not match:
        return "No battery information is available."
    return f"Battery is at {match.group(1)} percent, {match.group(2).strip()}."


def _open_application(args: dict) -> str:
    name = str(args["name"]).strip()
    if not APP_NAME.match(name):
        raise ToolError("That doesn't look like a valid application name.")
    try:
        # A list of arguments (no shell), so the name can never run as a command.
        proc = subprocess.run(["open", "-a", name], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise ToolError(f"Opening {name} took too long.")
    if proc.returncode != 0:
        raise ToolError(f"I couldn't find an application called {name}.")
    return f"Opened {name}."


def _set_volume(args: dict) -> str:
    try:
        level = int(args["level"])
    except (TypeError, ValueError):
        raise ToolError("The volume must be a number from 0 to 100.")
    if not 0 <= level <= 100:
        raise ToolError("The volume must be between 0 and 100.")
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {level}"],
            capture_output=True, timeout=5, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        raise ToolError("I couldn't change the volume.")
    return f"Volume set to {level} percent."


BUILTIN_TOOLS = [
    Tool(
        name="get_current_time",
        description="Get the current date and time on this Mac.",
        parameters=None,
        risk=RiskLevel.LOW,
        run=_get_current_time,
    ),
    Tool(
        name="get_battery_status",
        description="Get the battery percentage and charging state of this Mac.",
        parameters=None,
        risk=RiskLevel.LOW,
        run=_get_battery_status,
    ),
    Tool(
        name="open_application",
        description="Open an application on this Mac by its name, for example Safari, Calculator or Visual Studio Code.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The application name, e.g. 'Safari'."}
            },
            "required": ["name"],
        },
        risk=RiskLevel.LOW,
        run=_open_application,
    ),
    Tool(
        name="set_volume",
        description="Set the speaker volume of this Mac, from 0 (mute) to 100 (maximum).",
        parameters={
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Volume from 0 to 100."}
            },
            "required": ["level"],
        },
        risk=RiskLevel.MEDIUM,
        run=_set_volume,
    ),
]