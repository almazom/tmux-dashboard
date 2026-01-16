"""Configuration loader for tmux-dashboard."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import SortMode

DEFAULT_CONFIG_PATH = Path("~/.config/tmux-dashboard/config.json").expanduser()
DEFAULT_LOG_PATH = Path("~/.local/state/tmux-dashboard/log.jsonl").expanduser()
DEFAULT_COLOR = "auto"
DEFAULT_PREVIEW_LINES = 10
DEFAULT_DRY_RUN = False
DEFAULT_SORT_MODE = SortMode.AI_FIRST
DEFAULT_AUTO_CREATE = True


@dataclass
class Config:
    config_path: Path
    log_path: Path
    color: str
    preview_lines: int
    dry_run: bool
    sort_mode: SortMode = field(default_factory=lambda: DEFAULT_SORT_MODE)
    auto_create: bool = field(default_factory=lambda: DEFAULT_AUTO_CREATE)

    def save_sort_mode(self, mode: SortMode) -> None:
        """Save sort mode to config file."""
        self.sort_mode = mode
        data: dict[str, Any] = {}
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        data["sort_mode"] = mode.value
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # Fail silently if we can't save


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

    # Load sort mode from config or environment
    sort_mode_value = os.environ.get("TMUX_DASHBOARD_SORT_MODE") or data.get("sort_mode")
    sort_mode = SortMode.from_string(sort_mode_value) if sort_mode_value else DEFAULT_SORT_MODE

    # Load auto_create from config or environment
    if "TMUX_DASHBOARD_AUTO_CREATE" in os.environ:
        auto_create = _parse_bool(os.environ["TMUX_DASHBOARD_AUTO_CREATE"])
    else:
        auto_create = bool(data.get("auto_create", DEFAULT_AUTO_CREATE))

    return Config(
        config_path=config_path,
        log_path=log_path,
        color=str(color).strip().lower(),
        preview_lines=preview_lines,
        dry_run=dry_run,
        sort_mode=sort_mode,
        auto_create=auto_create,
    )
