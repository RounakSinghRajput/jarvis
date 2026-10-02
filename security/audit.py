import json
import threading
from datetime import datetime
from pathlib import Path


class AuditLog:
    """Append-only record of every tool call: what ran, who allowed it, how it ended."""

    def __init__(self, path: str = "logs/audit.log") -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def record(self, **fields) -> None:
        entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), **fields}
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")