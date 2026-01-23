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
DEFAULT_AUTO_RENAME_ON_DETACH = True
DEFAULT_HEADLESS_STATE_DIR = Path("~/.local/state/tmux-dashboard/headless").expanduser()
DEFAULT_HEADLESS_OUTPUT_DIR = Path("~/.local/state/tmux-dashboard/headless/output").expanduser()
DEFAULT_HEADLESS_REFRESH_SECONDS = 5
DEFAULT_HEADLESS_MAX_EVENTS = 200
DEFAULT_HEADLESS_WAITING_SECONDS = 20
DEFAULT_HEADLESS_DEFAULT_AGENT = "codex"
DEFAULT_HEADLESS_AGENTS = {
    "codex": "codex --model {model} --headless --prompt {instruction} 2>&1 | tee -a {output}",
    "cladcode": "cladcode -p {instruction} --output-format stream-json --non-interactive 2>&1 | tee -a {output}",
}
DEFAULT_HEADLESS_MODELS: dict[str, list[str]] = {
    "codex": [
        "gpt-5.2-codex xhigh",
        "gpt-5.2-codex high",
        "gpt-5.2-codex medium",
    ],
}
DEFAULT_HEADLESS_DEFAULT_MODELS: dict[str, str] = {
    "codex": "gpt-5.2-codex medium",
}
DEFAULT_HEADLESS_MODEL_LIST_COMMANDS: dict[str, str] = {}
DEFAULT_HEADLESS_AUTO_CLEANUP = False
DEFAULT_HEADLESS_NOTIFY_ON_COMPLETE = False


@dataclass
class Config:
    config_path: Path
    log_path: Path
    color: str
    preview_lines: int
    dry_run: bool
    sort_mode: SortMode = field(default_factory=lambda: DEFAULT_SORT_MODE)
    auto_create: bool = field(default_factory=lambda: DEFAULT_AUTO_CREATE)
    auto_rename_on_detach: bool = field(default_factory=lambda: DEFAULT_AUTO_RENAME_ON_DETACH)
    headless_state_dir: Path = field(default_factory=lambda: DEFAULT_HEADLESS_STATE_DIR)
    headless_output_dir: Path = field(default_factory=lambda: DEFAULT_HEADLESS_OUTPUT_DIR)
    headless_refresh_seconds: int = field(default_factory=lambda: DEFAULT_HEADLESS_REFRESH_SECONDS)
    headless_max_events: int = field(default_factory=lambda: DEFAULT_HEADLESS_MAX_EVENTS)
    headless_waiting_seconds: int = field(default_factory=lambda: DEFAULT_HEADLESS_WAITING_SECONDS)
    headless_default_agent: str = field(default_factory=lambda: DEFAULT_HEADLESS_DEFAULT_AGENT)
    headless_agents: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADLESS_AGENTS))
    headless_models: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_HEADLESS_MODELS))
    headless_default_models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADLESS_DEFAULT_MODELS))
    headless_model_list_commands: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_HEADLESS_MODEL_LIST_COMMANDS)
    )
    headless_auto_cleanup: bool = field(default_factory=lambda: DEFAULT_HEADLESS_AUTO_CLEANUP)
    headless_notify_on_complete: bool = field(default_factory=lambda: DEFAULT_HEADLESS_NOTIFY_ON_COMPLETE)

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

    if "TMUX_DASHBOARD_AUTO_RENAME_ON_DETACH" in os.environ:
        auto_rename_on_detach = _parse_bool(os.environ["TMUX_DASHBOARD_AUTO_RENAME_ON_DETACH"])
    else:
        auto_rename_on_detach = bool(data.get("auto_rename_on_detach", DEFAULT_AUTO_RENAME_ON_DETACH))

    headless_state_dir = Path(
        os.environ.get("TMUX_DASHBOARD_HEADLESS_STATE_DIR")
        or data.get("headless_state_dir")
        or str(DEFAULT_HEADLESS_STATE_DIR)
    ).expanduser()

    headless_output_dir = Path(
        os.environ.get("TMUX_DASHBOARD_HEADLESS_OUTPUT_DIR")
        or data.get("headless_output_dir")
        or str(DEFAULT_HEADLESS_OUTPUT_DIR)
    ).expanduser()

    headless_refresh_seconds = _safe_int(
        os.environ.get("TMUX_DASHBOARD_HEADLESS_REFRESH_SECONDS") or data.get("headless_refresh_seconds"),
        DEFAULT_HEADLESS_REFRESH_SECONDS,
    )

    headless_max_events = _safe_int(
        os.environ.get("TMUX_DASHBOARD_HEADLESS_MAX_EVENTS") or data.get("headless_max_events"),
        DEFAULT_HEADLESS_MAX_EVENTS,
    )

    headless_waiting_seconds = _safe_int(
        os.environ.get("TMUX_DASHBOARD_HEADLESS_WAITING_SECONDS") or data.get("headless_waiting_seconds"),
        DEFAULT_HEADLESS_WAITING_SECONDS,
    )

    headless_agents = dict(DEFAULT_HEADLESS_AGENTS)
    agents_from_config = data.get("headless_agents")
    if isinstance(agents_from_config, dict):
        for key, value in agents_from_config.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            cleaned_key = key.strip().lower()
            cleaned_value = value.strip()
            if cleaned_key and cleaned_value:
                headless_agents[cleaned_key] = cleaned_value

    env_codex = os.environ.get("TMUX_DASHBOARD_HEADLESS_CODEX_CMD")
    if env_codex:
        headless_agents["codex"] = env_codex.strip()

    env_cladcode = os.environ.get("TMUX_DASHBOARD_HEADLESS_CLADCODE_CMD")
    if env_cladcode:
        headless_agents["cladcode"] = env_cladcode.strip()

    headless_default_agent = (
        os.environ.get("TMUX_DASHBOARD_HEADLESS_DEFAULT_AGENT")
        or data.get("headless_default_agent")
        or DEFAULT_HEADLESS_DEFAULT_AGENT
    ).strip().lower()
    if headless_default_agent not in headless_agents:
        headless_default_agent = DEFAULT_HEADLESS_DEFAULT_AGENT
        if headless_default_agent not in headless_agents and headless_agents:
            headless_default_agent = next(iter(headless_agents))

    env_headless_models = os.environ.get("TMUX_DASHBOARD_HEADLESS_MODELS")
    loaded_models = _load_headless_models(data.get("headless_models"), env_headless_models)
    if env_headless_models:
        headless_models = loaded_models
    else:
        headless_models = dict(DEFAULT_HEADLESS_MODELS)
        headless_models.update(loaded_models)

    env_headless_default_model = os.environ.get("TMUX_DASHBOARD_HEADLESS_DEFAULT_MODEL")
    loaded_default_models = _load_headless_default_models(
        data.get("headless_default_model"),
        env_headless_default_model,
    )
    if env_headless_default_model:
        headless_default_models = loaded_default_models
    else:
        headless_default_models = dict(DEFAULT_HEADLESS_DEFAULT_MODELS)
        headless_default_models.update(loaded_default_models)

    headless_model_list_commands = _load_headless_model_list_commands(
        data.get("headless_model_list_commands"),
        os.environ.get("TMUX_DASHBOARD_HEADLESS_MODEL_LIST_COMMAND"),
    )

    if "TMUX_DASHBOARD_HEADLESS_AUTO_CLEANUP" in os.environ:
        headless_auto_cleanup = _parse_bool(os.environ["TMUX_DASHBOARD_HEADLESS_AUTO_CLEANUP"])
    else:
        headless_auto_cleanup = bool(data.get("headless_auto_cleanup", DEFAULT_HEADLESS_AUTO_CLEANUP))

    if "TMUX_DASHBOARD_HEADLESS_NOTIFY_ON_COMPLETE" in os.environ:
        headless_notify_on_complete = _parse_bool(os.environ["TMUX_DASHBOARD_HEADLESS_NOTIFY_ON_COMPLETE"])
    else:
        headless_notify_on_complete = bool(
            data.get("headless_notify_on_complete", DEFAULT_HEADLESS_NOTIFY_ON_COMPLETE)
        )

    return Config(
        config_path=config_path,
        log_path=log_path,
        color=str(color).strip().lower(),
        preview_lines=preview_lines,
        dry_run=dry_run,
        sort_mode=sort_mode,
        auto_create=auto_create,
        auto_rename_on_detach=auto_rename_on_detach,
        headless_state_dir=headless_state_dir,
        headless_output_dir=headless_output_dir,
        headless_refresh_seconds=headless_refresh_seconds,
        headless_max_events=headless_max_events,
        headless_waiting_seconds=headless_waiting_seconds,
        headless_default_agent=headless_default_agent,
        headless_agents=headless_agents,
        headless_models=headless_models,
        headless_default_models=headless_default_models,
        headless_model_list_commands=headless_model_list_commands,
        headless_auto_cleanup=headless_auto_cleanup,
        headless_notify_on_complete=headless_notify_on_complete,
    )


def _load_headless_models(config_value: Any, env_value: str | None) -> dict[str, list[str]]:
    models: dict[str, list[str]] = {}

    if env_value:
        parsed = _parse_model_list(env_value)
        if parsed:
            models["*"] = parsed
            return models

    if isinstance(config_value, dict):
        for key, value in config_value.items():
            if not isinstance(key, str):
                continue
            parsed = _parse_model_list(value)
            if parsed:
                models[key.strip().lower()] = parsed
    elif config_value is not None:
        parsed = _parse_model_list(config_value)
        if parsed:
            models["*"] = parsed

    return models


def _load_headless_default_models(config_value: Any, env_value: str | None) -> dict[str, str]:
    defaults: dict[str, str] = {}

    if env_value:
        cleaned = env_value.strip()
        if cleaned:
            defaults["*"] = cleaned
            return defaults

    if isinstance(config_value, dict):
        for key, value in config_value.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            if cleaned:
                defaults[key.strip().lower()] = cleaned
    elif isinstance(config_value, str):
        cleaned = config_value.strip()
        if cleaned:
            defaults["*"] = cleaned

    return defaults


def _parse_model_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.split(",")
    else:
        return []

    parsed: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            parsed.append(cleaned)
    return parsed


def _load_headless_model_list_commands(config_value: Any, env_value: str | None) -> dict[str, str]:
    commands: dict[str, str] = {}

    if env_value:
        cleaned = env_value.strip()
        if cleaned:
            commands["*"] = cleaned
            return commands

    if isinstance(config_value, dict):
        for key, value in config_value.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            cleaned_key = key.strip().lower()
            cleaned_value = value.strip()
            if cleaned_key and cleaned_value:
                commands[cleaned_key] = cleaned_value
    elif isinstance(config_value, str):
        cleaned = config_value.strip()
        if cleaned:
            commands["*"] = cleaned

    return commands
