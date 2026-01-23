"""Headless creation prompts."""

from __future__ import annotations

import curses
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import Config
from .prompts import confirm_dialog, draw_center_box, prompt_input_popup, show_message


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

    instruction = prompt_headless_instruction(stdscr)
    if instruction is None:
        return None

    return workdir, agent, model, instruction


def prompt_headless_instruction(stdscr: curses._CursesWindow) -> str | None:
    while True:
        method = prompt_instruction_source(stdscr)
        if method is None:
            return None
        if method == "popup":
            instruction = prompt_input_popup(
                stdscr,
                "Headless mode",
                default="",
                prompt="Instruction:",
                max_len=4000,
                allow_empty=True,
            )
        elif method == "editor":
            instruction = read_instruction_from_editor(stdscr)
        elif method == "tmux":
            instruction = read_instruction_from_tmux()
            if instruction is None:
                show_message(stdscr, "tmux buffer is empty or unavailable.")
                continue
        elif method == "file":
            instruction = read_instruction_from_file(stdscr)
        else:
            instruction = None

        if instruction is None:
            return None
        if instruction.strip():
            return instruction
        show_message(stdscr, "Instruction is required.")


def prompt_instruction_source(stdscr: curses._CursesWindow) -> str | None:
    height, width = stdscr.getmaxyx()
    stdscr.nodelay(False)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    lines = [
        "Instruction input",
        "1) Editor ($EDITOR) - long text",
        "2) Paste from tmux buffer",
        "3) Load from file",
        "4) Quick input (single line)",
        "Enter: editor  Esc: cancel",
    ]
    draw_center_box(stdscr, "Instruction", lines, width, height)
    while True:
        key = stdscr.getch()
        if key == 27:
            return None
        if key in (10, 13):
            return "editor"
        if key == ord("1"):
            return "editor"
        if key == ord("2"):
            return "tmux"
        if key == ord("3"):
            return "file"
        if key == ord("4"):
            return "popup"


def _resolve_editor_command() -> list[str] | None:
    env_editor = os.environ.get("EDITOR")
    if env_editor:
        try:
            args = shlex.split(env_editor)
        except ValueError:
            args = [env_editor]
        if args and shutil.which(args[0]):
            return args

    for candidate in ("nano", "vi"):
        if shutil.which(candidate):
            return [candidate]
    return None


def read_instruction_from_editor(stdscr: curses._CursesWindow) -> str:
    editor_cmd = _resolve_editor_command()
    if not editor_cmd:
        show_message(stdscr, "No editor found. Set $EDITOR.")
        return ""

    fd, path = tempfile.mkstemp(prefix="tmux-dashboard-", suffix=".txt")
    os.close(fd)
    try:
        _run_external_editor(stdscr, editor_cmd, path)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return handle.read().rstrip("\n")
        except OSError:
            show_message(stdscr, "Failed to read editor buffer.")
            return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _run_external_editor(stdscr: curses._CursesWindow, command: list[str], path: str) -> None:
    try:
        curses.def_prog_mode()
    except curses.error:
        pass
    try:
        curses.endwin()
    except curses.error:
        pass

    try:
        subprocess.run([*command, path], check=False)
    finally:
        try:
            curses.reset_prog_mode()
        except curses.error:
            pass
        try:
            curses.doupdate()
        except curses.error:
            pass
        try:
            stdscr.clear()
            stdscr.refresh()
        except curses.error:
            pass
        try:
            curses.noecho()
            curses.cbreak()
            stdscr.keypad(True)
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        except curses.error:
            pass
        try:
            curses.flushinp()
        except curses.error:
            pass


def read_instruction_from_tmux() -> str | None:
    if not shutil.which("tmux"):
        return None
    try:
        result = subprocess.run(
            ["tmux", "show-buffer"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.rstrip("\n")
    return text if text.strip() else None


def read_instruction_from_file(stdscr: curses._CursesWindow) -> str | None:
    path = prompt_input_popup(
        stdscr,
        "Instruction file",
        default="",
        prompt="Path:",
        max_len=200,
        allow_empty=False,
    )
    if path is None:
        return None
    value = path.strip()
    if not value:
        show_message(stdscr, "Path is required.")
        return ""
    try:
        with open(os.path.expanduser(value), encoding="utf-8", errors="replace") as handle:
            return handle.read().rstrip("\n")
    except OSError:
        show_message(stdscr, f"Failed to read file: {value}")
        return ""


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
