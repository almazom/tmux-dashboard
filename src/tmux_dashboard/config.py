"""Configuration loader for tmux-dashboard."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/.config/tmux-dashboard/config.json").expanduser()
DEFAULT_LOG_PATH = Path("~/.local/state/tmux-dashboard/log.jsonl").expanduser()
DEFAULT_COLOR = "auto"
DEFAULT_PREVIEW_LINES = 10
DEFAULT_DRY_RUN = False


@dataclass(frozen=True)
class Config:
    config_path: Path
    log_path: Path
    color: str
    preview_lines: int
    dry_run: bool


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (ValueError, TypeError):
        return default
    return parsed if parsed > 0 else default


def load_config(path: str | None = None) -> Config:
    env_path = os.environ.get("TMUX_DASHBOARD_CONFIG")
    config_path = Path(path or env_path or DEFAULT_CONFIG_PATH).expanduser()

    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

    log_path = Path(
        os.environ.get("TMUX_DASHBOARD_LOG")
        or data.get("log_path")
        or str(DEFAULT_LOG_PATH)
    ).expanduser()

    color = (
        os.environ.get("TMUX_DASHBOARD_COLOR")
        or data.get("color")
        or DEFAULT_COLOR
    )

    preview_lines = _safe_int(
        os.environ.get("TMUX_DASHBOARD_PREVIEW_LINES") or data.get("preview_lines"),
        DEFAULT_PREVIEW_LINES,
    )

    if "TMUX_DASHBOARD_DRY_RUN" in os.environ:
        dry_run = _parse_bool(os.environ["TMUX_DASHBOARD_DRY_RUN"])
    else:
        dry_run = bool(data.get("dry_run", DEFAULT_DRY_RUN))

    return Config(
        config_path=config_path,
        log_path=log_path,
        color=str(color).strip().lower(),
        preview_lines=preview_lines,
        dry_run=dry_run,
    )
