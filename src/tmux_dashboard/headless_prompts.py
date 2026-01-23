"""Headless creation prompts."""

from __future__ import annotations

import curses
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .prompts import confirm_dialog, draw_center_box, prompt_input_popup


def prompt_headless_request(
    stdscr: curses._CursesWindow,
    config: Config,
) -> tuple[str, str, str, str] | None:
    workdir_default = str(Path.cwd())
    workdir = prompt_input_popup(
        stdscr,
        "Headless mode",
        default=workdir_default,
        prompt="Workdir:",
        max_len=200,
    )
    if workdir is None:
        return None

    agent = prompt_input_popup(
        stdscr,
        "Headless mode",
        default=config.headless_default_agent,
        prompt="Agent (codex/cladcode):",
        max_len=32,
    )
    if agent is None:
        return None

    model = prompt_headless_model(stdscr, config, agent)
    if model is None:
        return None

    instruction = prompt_input_popup(
        stdscr,
        "Headless mode",
        default="",
        prompt="Instruction (optional):",
        max_len=240,
        allow_empty=True,
    )
    if instruction is None:
        return None

    return workdir, agent, model, instruction


def prompt_headless_model(stdscr: curses._CursesWindow, config: Config, agent_raw: str) -> str | None:
    agent = agent_raw.strip().lower() or config.headless_default_agent
    models, default_model = resolve_headless_models(config, agent)
    list_command = resolve_headless_model_list_command(config, agent)
    if not models:
        prompt = format_headless_model_prompt(models, list_command)
        allow_empty = not models and not default_model
        default_value = default_model or ""
        while True:
            model = prompt_input_popup(
                stdscr,
                "Headless mode",
                default=default_value,
                prompt=prompt,
                max_len=64,
                allow_empty=allow_empty,
            )
            if model is None:
                return None
            if model.strip().lower() in {"?", "list"}:
                show_model_list(stdscr, agent, models, list_command)
                continue
            return model

    return select_headless_model_dialog(
        stdscr,
        agent,
        models,
        default_model,
        list_command,
    )


def resolve_headless_models(config: Config, agent: str) -> tuple[list[str], str | None]:
    models = config.headless_models.get(agent) or config.headless_models.get("*") or []
    default_model = (
        config.headless_default_models.get(agent)
        or config.headless_default_models.get("*")
    )
    if not default_model and models:
        default_model = models[0]
    return models, default_model


def format_headless_model_prompt(models: list[str], list_command: str | None) -> str:
    if not models:
        if list_command:
            return "Model (optional, ?=list):"
        return "Model (optional):"
    max_items = 4
    display = ", ".join(models[:max_items])
    if len(models) > max_items:
        display = f"{display}, ..."
    suffix = " ?=list" if list_command else ""
    return f"Model ({display}){suffix}:"


def select_headless_model_dialog(
    stdscr: curses._CursesWindow,
    agent: str,
    models: list[str],
    default_model: str | None,
    list_command: str | None,
) -> str | None:
    height, width = stdscr.getmaxyx()
    stdscr.nodelay(False)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    while True:
        lines: list[str] = []
        lines.append(f"Select model for {agent}")
        for idx, model in enumerate(models[:9], start=1):
            suffix = " (default)" if default_model and model == default_model else ""
            lines.append(f"{idx}) {model}{suffix}")
        if len(models) > 9:
            lines.append("More models available. Use manual entry.")
        if list_command:
            lines.append("?: show list from CLI")
        lines.append("m: manual entry")
        if default_model:
            lines.append("Enter: use default")
        lines.append("Esc: cancel")

        draw_center_box(stdscr, "Headless model", lines, width, height)
        key = stdscr.getch()
        if key == 27:
            return None
        if key in (10, 13) and default_model:
            return default_model
        if key in (ord("?"), ord("l")):
            show_model_list(stdscr, agent, models, list_command)
            continue
        if key in (ord("m"), ord("M")):
            value = prompt_input_popup(
                stdscr,
                "Custom model",
                default="",
                prompt="Model name:",
                max_len=64,
                allow_empty=False,
            )
            if value is None:
                continue
            return value
        if 49 <= key <= 57:
            idx = key - 49
            if idx < len(models):
                return models[idx]


def resolve_headless_model_list_command(config: Config, agent: str) -> str | None:
    return config.headless_model_list_commands.get(agent) or config.headless_model_list_commands.get("*")


def show_model_list(
    stdscr: curses._CursesWindow,
    agent: str,
    models: list[str],
    list_command: str | None,
) -> None:
    lines: list[str] = []
    if models:
        lines.append("Configured models:")
        lines.extend(models)

    cli_models: list[str] = []
    if list_command:
        cli_models = fetch_models_from_cli(list_command, agent)
        if cli_models:
            if lines:
                lines.append("")
            lines.append("CLI models:")
            lines.extend(cli_models)

    if not lines:
        lines = ["No models configured.", "Set headless_models or list command in config."]
    else:
        lines.append("")
        lines.append("Enter=close  Esc=close")

    confirm_dialog(stdscr, title="Available models", lines=lines)


def fetch_models_from_cli(command: str, agent: str) -> list[str]:
    if not command.strip():
        return []

    try:
        args = shlex.split(command)
    except ValueError:
        return []
    if not args:
        return []
    if not shutil.which(args[0]):
        return []

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    lines: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[*\\-•]+\\s*", "", line)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= 30:
            break
    return lines
