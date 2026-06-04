"""
In-memory log buffer — captures log records for display in the web UI.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any

MAX_ENTRIES = 300

_buffer: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)

LEVEL_COLORS = {
    "DEBUG":    "text-gray-400",
    "INFO":     "text-blue-300",
    "WARNING":  "text-yellow-300",
    "ERROR":    "text-red-400",
    "CRITICAL": "text-red-600",
}


class MemoryLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            _buffer.append({
                "time": datetime.fromtimestamp(record.created).strftime("%I:%M:%S %p").lstrip("0"),
                "level": record.levelname,
                "color": LEVEL_COLORS.get(record.levelname, "text-gray-300"),
                "name": record.name.replace("src.", ""),
                "message": self.format(record),
            })
        except Exception:
            pass


def get_logs(limit: int = 100) -> list[dict]:
    """Return the most recent `limit` log entries."""
    entries = list(_buffer)
    return entries[-limit:]


def clear_logs():
    _buffer.clear()


def setup(level=logging.INFO):
    """Install the memory handler on the root logger."""
    handler = MemoryLogHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
