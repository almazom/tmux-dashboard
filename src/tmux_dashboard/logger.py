"""JSONL logger for tmux-dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]

if ZoneInfo is not None:
    MSK_TZ = ZoneInfo("Europe/Moscow")
else:
    MSK_TZ = timezone(timedelta(hours=3))


@dataclass
class Logger:
    log_path: Path

    def _write(self, record: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def log(self, level: str, event: str, message: str, session_name: str | None = None) -> None:
        ts = datetime.now(tz=MSK_TZ).isoformat()
        record = {
            "ts": ts,
            "level": level.upper(),
            "event": event,
            "session_name": session_name,
            "message": message,
        }
        self._write(record)

    def info(self, event: str, message: str, session_name: str | None = None) -> None:
        self.log("INFO", event, message, session_name=session_name)

    def warn(self, event: str, message: str, session_name: str | None = None) -> None:
        self.log("WARN", event, message, session_name=session_name)

    def error(self, event: str, message: str, session_name: str | None = None) -> None:
        self.log("ERROR", event, message, session_name=session_name)
