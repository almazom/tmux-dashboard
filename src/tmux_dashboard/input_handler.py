"""Keyboard input handling and dashboard loop."""

from __future__ import annotations

import curses
import json
import random
import re
import subprocess
import textwrap
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config
from .headless import (
    HeadlessRegistry,
    HeadlessSession,
    build_headless_session,
    build_headless_shell_command,
)
from .logger import Logger
from .models import SessionInfo, SortMode
from .tmux_manager import TmuxError, TmuxManager
from .ui import DashboardUI, UiState, UiStatus


@dataclass
class Action:
    kind: str
    session_name: str | None = None


def run_dashboard(
    tmux: TmuxManager,
    config: Config,
    logger: Logger,
    headless_registry: HeadlessRegistry,
    pending_status: object | None = None,
) -> Action | None:
    def _main(stdscr: curses._CursesWindow) -> Action | None:
        ui = DashboardUI(stdscr, config.color)
        ui.init()

        status = None
        if pending_status:
            message = getattr(pending_status, "message", "")
            level = getattr(pending_status, "level", "info")
            status = UiStatus(message=message, level=level)

        # Initialize sort mode from config
        sort_mode = config.sort_mode
        sessions, headless_map, list_status = _refresh_sessions(tmux, logger, sort_mode, headless_registry)
        if list_status:
            status = list_status
        selected_index = 0
        filter_text = ""
        in_search = False
        help_visible = False
        last_preview_session: str | None = None
        last_preview_at = 0.0
        cached_preview = None
        cached_pane_capture = None
        cached_preview_title = "Live Preview:"
        preview_interval = 0.5

        while True:
            # Reinitialize curses state after returning from attach
            stdscr.clear()
            stdscr.timeout(100)

            filtered = _filter_sessions(sessions, filter_text)
            ordered, headless_start_index, interactive_sessions = _group_headless_sessions(filtered)
            selected_index = _clamp_index(selected_index, len(ordered))

            preview = None
            pane_capture = None
            preview_title = "Live Preview:"
            if ordered and config.preview_lines > 0:
                selected_session = ordered[selected_index]
                current_session = selected_session.name
                now = time.monotonic()
                should_refresh = (
                    current_session != last_preview_session
                    or (now - last_preview_at) >= preview_interval
                )
                if should_refresh:
                    if selected_session.is_headless:
                        headless_session = headless_map.get(current_session)
                        pane_capture = _read_headless_output(
                            headless_session.output_path if headless_session else None,
                            config.headless_max_events,
                        )
                        preview_title = "Headless Output:"
                        cached_preview = None
                        cached_pane_capture = pane_capture
                        cached_preview_title = preview_title
                        last_preview_session = current_session
                        last_preview_at = now
                    else:
                        try:
                            preview = tmux.get_session_details(current_session)
                            # Also capture live pane content
                            pane_capture = tmux.capture_pane_text(current_session)
                            preview_title = "Live Preview:"
                            cached_preview = preview
                            cached_pane_capture = pane_capture
                            cached_preview_title = preview_title
                            last_preview_session = current_session
                            last_preview_at = now
                        except TmuxError as exc:
                            status = UiStatus(str(exc), level="error")
                            logger.error("preview", str(exc), current_session)
                            cached_preview = None
                            cached_pane_capture = None
                            cached_preview_title = "Live Preview:"
                            last_preview_session = current_session
                            last_preview_at = now
                else:
                    preview = cached_preview
                    pane_capture = cached_pane_capture
                    preview_title = cached_preview_title

            state = UiState(
                sessions=ordered,
                selected_index=selected_index,
                filter_text=filter_text,
                in_search=in_search,
                help_visible=help_visible,
                status=status,
                preview=preview.windows if preview else None,
                pane_capture=pane_capture,
                sort_mode=sort_mode,
                headless_start_index=headless_start_index,
                preview_title=preview_title,
            )
            ui.render(state, config.preview_lines)

            key = stdscr.getch()

            if in_search:
                if key == 27:  # ESC
                    in_search = False
                    filter_text = ""
                    continue
                if key in (ord("q"), 3):
                    return Action(kind="exit")
                if key in (10, 13):
                    if ordered:
                        target = ordered[selected_index]
                        if target.is_headless:
                            _view_headless_session(
                                stdscr,
                                target.name,
                                headless_registry,
                                config,
                                logger,
                            )
                            sessions, headless_map, list_status = _refresh_sessions(
                                tmux,
                                logger,
                                sort_mode,
                                headless_registry,
                            )
                            status = list_status or UiStatus(f"Returned from {target.name}", level="info")
                            continue
                        return Action(kind="attach", session_name=target.name)
                    status = UiStatus("No sessions match search", level="warning")
                    continue
                if key in (curses.KEY_BACKSPACE, 127, 8):
                    filter_text = filter_text[:-1]
                    continue
                if 32 <= key <= 126:
                    filter_text += chr(key)
                continue

            if key in (curses.KEY_F1, ord("?")):
                help_visible = not help_visible
                continue

            if key == ord("/"):
                in_search = True
                filter_text = ""
                continue

            # Quick numbered attach (keys 1-9)
            if 49 <= key <= 57:  # Keys 1-9
                num = key - 48  # Convert to 1-9
                if num <= len(interactive_sessions):
                    session_name = interactive_sessions[num - 1].name
                    sessions, headless_map, status, selected_index, _ = _attach_and_refresh(
                        stdscr,
                        tmux,
                        session_name,
                        logger,
                        sort_mode,
                        filter_text,
                        headless_registry,
                        auto_rename_on_detach=config.auto_rename_on_detach,
                    )
                    continue
                else:
                    status = UiStatus(f"No session #{num}", level="warning")
                    continue

            if key == curses.KEY_UP:
                selected_index = max(0, selected_index - 1)
                continue
            if key == curses.KEY_DOWN:
                selected_index = min(max(0, len(ordered) - 1), selected_index + 1)
                continue
            if key in (10, 13):
                if ordered:
                    # Handle attach/view within the curses context
                    selected_session = ordered[selected_index]
                    if selected_session.is_headless:
                        _view_headless_session(
                            stdscr,
                            selected_session.name,
                            headless_registry,
                            config,
                            logger,
                        )
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                        )
                        status = list_status or UiStatus(f"Returned from {selected_session.name}", level="info")
                        continue

                    sessions, headless_map, status, selected_index, _ = _attach_and_refresh(
                        stdscr,
                        tmux,
                        selected_session.name,
                        logger,
                        sort_mode,
                        filter_text,
                        headless_registry,
                        auto_rename_on_detach=config.auto_rename_on_detach,
                    )
                    continue
                status = UiStatus("No sessions to attach", level="warning")
                continue
            if key == ord("n"):
                # Prompt with empty default - user can type name or press Enter for random
                name = _prompt_input_popup(stdscr, "New tmux session", default="")
                if name is None:
                    status = UiStatus("Create canceled", level="warning")
                    continue
                # If empty, generate a funny random name
                if not name:
                    name = _generate_funny_name()
                # Ensure name is unique
                existing_names = {s.name for s in sessions}
                if name in existing_names:
                    base = name
                    counter = 2
                    while name in existing_names:
                        name = f"{base}-{counter}"
                        counter += 1
                return Action(kind="create", session_name=name)
            if key == ord("H"):
                request = _prompt_headless_request(stdscr, config)
                if request is None:
                    status = UiStatus("Headless create canceled", level="warning")
                    continue

                workdir_raw, agent_raw, instruction = request
                workdir_path = Path(workdir_raw).expanduser()
                if not workdir_path.exists() or not workdir_path.is_dir():
                    status = UiStatus(f"Invalid directory: {workdir_raw}", level="error")
                    continue

                agent = agent_raw.strip().lower()
                if not agent:
                    agent = config.headless_default_agent
                if agent not in config.headless_agents:
                    status = UiStatus(f"Unknown headless agent: {agent}", level="error")
                    continue

                existing_names = {s.name for s in sessions}
                session_name = _build_headless_session_name(
                    agent,
                    workdir_path.name or "headless",
                    existing_names,
                )
                output_path = headless_registry.output_path(session_name)
                command_template = config.headless_agents[agent]
                try:
                    command_list = build_headless_shell_command(
                        command_template,
                        instruction,
                        str(output_path),
                        str(workdir_path),
                        agent,
                    )
                except (KeyError, ValueError) as exc:
                    status = UiStatus(f"Headless command template error: {exc}", level="error")
                    continue
                command_preview = command_list[-1] if command_list else None

                try:
                    tmux.create_session_with_command(session_name, command_list, directory=str(workdir_path))
                    headless_session = build_headless_session(
                        session_name=session_name,
                        agent=agent,
                        instruction=instruction,
                        workdir=str(workdir_path),
                        output_path=str(output_path),
                        command=command_preview,
                    )
                    headless_registry.record(headless_session)
                    logger.info("headless_create", f"headless session created: {agent}", session_name)
                    _view_headless_session(
                        stdscr,
                        session_name,
                        headless_registry,
                        config,
                        logger,
                    )
                    sessions, headless_map, list_status = _refresh_sessions(
                        tmux,
                        logger,
                        sort_mode,
                        headless_registry,
                    )
                    status = list_status or UiStatus(f"Headless session created: {session_name}", level="info")
                except TmuxError as exc:
                    logger.error("headless_create", str(exc), session_name)
                    status = UiStatus(str(exc), level="error")
                continue
            if key == ord("d"):
                if not ordered:
                    status = UiStatus("No sessions to delete", level="warning")
                    continue
                target = ordered[selected_index]
                if config.dry_run:
                    status = UiStatus("Dry-run enabled. Delete blocked.", level="warning")
                    logger.warn("delete", "dry-run blocked delete", target.name)
                    continue
                warning = "Attached session" if target.attached else "Detached session"
                confirm = _confirm_dialog(
                    stdscr,
                    title="Delete session",
                    lines=[
                        f"{warning}: {target.name}",
                        "This will terminate running processes.",
                        "Enter=confirm  Esc=cancel",
                    ],
                )
                if confirm:
                    try:
                        tmux.kill_session(target.name)
                        if target.is_headless:
                            headless_registry.forget(target.name)
                        logger.info("delete", "session deleted", target.name)
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                        )
                        status = list_status or UiStatus("Session deleted", level="info")
                    except TmuxError as exc:
                        logger.error("delete", str(exc), target.name)
                        status = UiStatus(str(exc), level="error")
                else:
                    status = UiStatus("Delete canceled", level="warning")
                continue
            if key == ord("R"):  # Shift+r for rename
                if not ordered:
                    status = UiStatus("No sessions to rename", level="warning")
                    continue
                target = ordered[selected_index]
                if target.is_headless:
                    status = UiStatus("Headless sessions cannot be renamed yet", level="warning")
                    continue
                new_name = _prompt_input_popup(stdscr, "Rename session")
                if new_name and new_name != target.name:
                    try:
                        tmux.rename_session(target.name, new_name)
                        logger.info("rename", f"renamed {target.name} to {new_name}")
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                        )
                        status = list_status or UiStatus("Session renamed", level="info")
                    except TmuxError as exc:
                        logger.error("rename", str(exc), target.name)
                        status = UiStatus(str(exc), level="error")
                elif new_name == target.name:
                    status = UiStatus("Name unchanged", level="warning")
                else:
                    status = UiStatus("Rename canceled", level="warning")
                continue
            if key in (ord("q"), 3):
                return Action(kind="exit")

            if key == ord("r"):
                sessions, headless_map, list_status = _refresh_sessions(
                    tmux,
                    logger,
                    sort_mode,
                    headless_registry,
                )
                status = list_status or UiStatus("Session list refreshed", level="info")
                continue

            if key == ord("s"):
                # Cycle to next sort mode
                new_mode = sort_mode.next_mode()
                sort_mode = new_mode
                # Save to config
                config.save_sort_mode(new_mode)
                # Re-sort sessions
                sessions, headless_map, list_status = _refresh_sessions(
                    tmux,
                    logger,
                    sort_mode,
                    headless_registry,
                )
                status = list_status or UiStatus(f"Sort mode: {new_mode.label} ({new_mode.description})", level="info")
                selected_index = 0  # Reset to top after re-sort
                continue

        return None

    return curses.wrapper(_main)


def _do_attach(
    stdscr: curses._CursesWindow,
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    auto_rename_on_detach: bool = True,
) -> str | None:
    """Attach to a tmux session within the curses context.

    Returns:
        The new session name if it was renamed, otherwise the original name.
    """
    # End curses mode temporarily
    curses.endwin()

    try:
        logger.info("attach", f"attaching to {session_name}")
        cmd = tmux.attach_command(session_name)
        result = subprocess.run(cmd)
        logger.info("attach", f"returned from {session_name}, exit code: {result.returncode}")
    except OSError as exc:
        logger.error("attach", str(exc), session_name)
    finally:
        new_name = None
        if auto_rename_on_detach:
            # Auto-rename session to project folder name on detach
            new_name = tmux.rename_session_to_project(session_name)
            if new_name:
                logger.info("rename", f"auto-renamed session from {session_name} to {new_name}")

        # Reinitialize curses after returning
        curses.doupdate()
        # Clear and refresh the screen
        stdscr.clear()
        stdscr.refresh()
        # Re-apply UI settings
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

    # Return the actual session name (new or original)
    return new_name or session_name


def _attach_and_refresh(
    stdscr: curses._CursesWindow,
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    sort_mode: SortMode,
    filter_text: str,
    headless_registry: HeadlessRegistry,
    auto_rename_on_detach: bool = True,
) -> tuple[list, dict[str, HeadlessSession], UiStatus | None, int, str]:
    actual_session_name = _do_attach(
        stdscr,
        tmux,
        session_name,
        logger,
        auto_rename_on_detach=auto_rename_on_detach,
    )
    if not actual_session_name:
        actual_session_name = session_name

    sessions, headless_map, list_status = _refresh_sessions(tmux, logger, sort_mode, headless_registry)
    status = list_status or UiStatus(f"Returned from {actual_session_name}", level="info")
    filtered = _filter_sessions(sessions, filter_text)
    ordered, _, _ = _group_headless_sessions(filtered)
    if ordered:
        selected_index = _find_session_index(ordered, actual_session_name)
        if selected_index == 0 and ordered[0].name != actual_session_name:
            session_names = [s.name for s in ordered]
            logger.warn(
                "cursor_restore",
                f"Session '{actual_session_name}' not found in filtered list: {session_names}",
            )
    else:
        selected_index = 0
    return sessions, headless_map, status, selected_index, actual_session_name


def _safe_list_sessions(tmux: TmuxManager, logger: Logger, sort_mode: SortMode = SortMode.DEFAULT) -> tuple[list, UiStatus | None]:
    try:
        return tmux.list_sessions(sort_mode), None
    except TmuxError as exc:
        logger.error("session_list", str(exc))
        return [], UiStatus(str(exc), level="error")


def _refresh_sessions(
    tmux: TmuxManager,
    logger: Logger,
    sort_mode: SortMode,
    headless_registry: HeadlessRegistry,
) -> tuple[list[SessionInfo], dict[str, HeadlessSession], UiStatus | None]:
    sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
    headless_map = headless_registry.load_all()
    sessions = _apply_headless_metadata(sessions, headless_map)
    return sessions, headless_map, list_status


def _apply_headless_metadata(
    sessions: list[SessionInfo],
    headless_map: dict[str, HeadlessSession],
) -> list[SessionInfo]:
    if not headless_map:
        return sessions
    enriched: list[SessionInfo] = []
    for session in sessions:
        headless = headless_map.get(session.name)
        if headless:
            enriched.append(
                SessionInfo(
                    name=session.name,
                    attached=session.attached,
                    windows=session.windows,
                    is_ai_session=True,
                    is_headless=True,
                    headless_agent=headless.agent,
                )
            )
        else:
            enriched.append(session)
    return enriched


def _group_headless_sessions(
    sessions: list[SessionInfo],
) -> tuple[list[SessionInfo], int | None, list[SessionInfo]]:
    interactive = [session for session in sessions if not session.is_headless]
    headless = [session for session in sessions if session.is_headless]
    ordered = interactive + headless
    headless_start_index = len(interactive) if headless else None
    return ordered, headless_start_index, interactive


def _filter_sessions(sessions: list, filter_text: str) -> list:
    if not filter_text:
        return sessions
    lowered = filter_text.lower()
    return [session for session in sessions if lowered in session.name.lower()]


def _clamp_index(index: int, length: int) -> int:
    if length <= 0:
        return 0
    return max(0, min(index, length - 1))


def _find_session_index(sessions: list, session_name: str) -> int:
    """Find the index of a session by name in the session list."""
    for idx, session in enumerate(sessions):
        if session.name == session_name:
            return idx
    return 0  # Default to first session if not found


def _prompt_input_popup(
    stdscr: curses._CursesWindow,
    title: str,
    default: str = "",
    prompt: str = "Enter session name:",
    help_text: str = "Enter=confirm  Esc=cancel",
    max_len: int = 50,
    allow_empty: bool = False,
) -> str | None:
    height, width = stdscr.getmaxyx()
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    stdscr.nodelay(False)

    # Initialize buffer with default value
    buffer: list[str] = list(default)

    while True:
        # Clear center area
        center_y = height // 2
        for row in range(center_y - 2, center_y + 3):
            _safe_addstr(stdscr, row, 0, " " * width)

        # Center the text
        title_x = max(0, (width - len(title)) // 2)
        prompt_x = max(0, (width - len(prompt)) // 2)
        help_x = max(0, (width - len(help_text)) // 2)

        _safe_addstr(stdscr, center_y - 1, title_x, title)
        _safe_addstr(stdscr, center_y, prompt_x, prompt)

        # Draw input
        input_display = "".join(buffer)
        max_input_width = width - 4
        if len(input_display) > max_input_width:
            input_display = "~" + input_display[-(max_input_width - 1):]
        input_x = max(2, (width - len(input_display)) // 2)
        _safe_addstr(stdscr, center_y + 1, input_x, input_display)
        try:
            stdscr.move(center_y + 1, input_x + min(len(input_display), max_input_width))
        except curses.error:
            pass

        _safe_addstr(stdscr, center_y + 2, help_x, help_text)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (10, 13):
            break
        if key == 27:  # ESC
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            return None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if buffer:
                buffer.pop()
            continue
        if 32 <= key <= 126:
            if len(buffer) < max_len:
                buffer.append(chr(key))

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    value = "".join(buffer).strip()
    if value:
        return value
    return "" if allow_empty else None


def _prompt_headless_request(stdscr: curses._CursesWindow, config: Config) -> tuple[str, str, str] | None:
    workdir_default = str(Path.cwd())
    workdir = _prompt_input_popup(
        stdscr,
        "Headless mode",
        default=workdir_default,
        prompt="Workdir:",
        max_len=200,
    )
    if workdir is None:
        return None

    agent = _prompt_input_popup(
        stdscr,
        "Headless mode",
        default=config.headless_default_agent,
        prompt="Agent (codex/cladcode):",
        max_len=32,
    )
    if agent is None:
        return None

    instruction = _prompt_input_popup(
        stdscr,
        "Headless mode",
        default="",
        prompt="Instruction (optional):",
        max_len=240,
        allow_empty=True,
    )
    if instruction is None:
        return None

    return workdir, agent, instruction


def _build_headless_session_name(agent: str, project: str, existing_names: set[str]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_agent = _sanitize_session_component(agent)
    safe_project = _sanitize_session_component(project)
    base = f"headless-{safe_agent}-{safe_project}-{timestamp}"
    return _unique_session_name(base, existing_names)


def _sanitize_session_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower())
    return cleaned.strip("-") or "headless"


def _unique_session_name(base: str, existing_names: set[str]) -> str:
    if base not in existing_names:
        return base
    counter = 2
    candidate = f"{base}-{counter}"
    while candidate in existing_names:
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


def _view_headless_session(
    stdscr: curses._CursesWindow,
    session_name: str,
    headless_registry: HeadlessRegistry,
    config: Config,
    logger: Logger,
) -> None:
    session = headless_registry.get(session_name)
    if session is None:
        _show_message(stdscr, f"Headless metadata not found for {session_name}")
        return

    output_lines: list[str] = []
    last_refresh = 0.0
    refresh_interval = max(1, config.headless_refresh_seconds)

    while True:
        now = time.monotonic()
        if (now - last_refresh) >= refresh_interval:
            output_lines = _read_headless_output(session.output_path, config.headless_max_events)
            last_refresh = now

        status_line = f"Output: {Path(session.output_path).name}  Refresh: {refresh_interval}s"
        _render_headless_view(stdscr, session, output_lines, status_line)

        stdscr.timeout(200)
        key = stdscr.getch()
        if key in (ord("q"), 27):
            return
        if key == ord("r"):
            last_refresh = 0.0
            logger.info("headless_view", "manual refresh", session_name)


def _render_headless_view(
    stdscr: curses._CursesWindow,
    session: HeadlessSession,
    output_lines: list[str],
    status_line: str,
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    left = 2
    max_width = max(1, width - left - 1)

    row = 1
    title = f"Headless Session: {session.session_name} [{session.agent}]"
    _safe_addstr(stdscr, row, left, title[:max_width])
    row += 2

    _safe_addstr(stdscr, row, left, f"Path: {session.workdir}"[:max_width])
    row += 1

    _safe_addstr(stdscr, row, left, "Instruction:"[:max_width])
    row += 1

    instruction = session.instruction or "(empty)"
    for line in _wrap_lines(instruction, max_width):
        if row >= height - 4:
            break
        _safe_addstr(stdscr, row, left, line[:max_width])
        row += 1

    if row < height - 4:
        row += 1

    _safe_addstr(stdscr, row, left, "Output:"[:max_width])
    row += 1

    available = max(0, height - row - 2)
    wrapped_output: list[str] = []
    for line in output_lines:
        wrapped_output.extend(_wrap_lines(line, max_width))
    if not wrapped_output:
        wrapped_output = ["(waiting for output)"]
    for line in wrapped_output[-available:]:
        _safe_addstr(stdscr, row, left, line[:max_width])
        row += 1

    footer = "q/Esc back  r refresh"
    _safe_addstr(stdscr, height - 2, left, footer[:max_width])
    _safe_addstr(stdscr, height - 1, left, status_line[:max_width])
    stdscr.refresh()


def _read_headless_output(output_path: str | None, max_events: int) -> list[str]:
    if not output_path:
        return ["(headless output unavailable)"]
    path = Path(output_path)
    if not path.exists():
        return ["(waiting for output)"]

    events: deque[list[str]] = deque(maxlen=max_events)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    events.append([line])
                    continue
                events.append(_summarize_headless_event(payload))
    except OSError:
        return ["(failed to read output)"]

    if not events:
        return ["(waiting for output)"]

    output_lines: list[str] = []
    for event_lines in events:
        output_lines.extend(event_lines)
    return output_lines


def _summarize_headless_event(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        event_type = _stringify_event_value(payload.get("type") or payload.get("event") or payload.get("kind"))
        message = _extract_event_message(payload)
        if message:
            lines = message.splitlines() or [message]
        else:
            try:
                lines = [json.dumps(payload, ensure_ascii=True)]
            except (TypeError, ValueError):
                lines = [str(payload)]
        if event_type:
            lines[0] = f"{event_type}: {lines[0]}"
        return lines
    return [str(payload)]


def _extract_event_message(payload: dict[str, Any]) -> str | None:
    for key in ("message", "content", "text", "delta", "output", "data"):
        candidate = _stringify_event_value(payload.get(key))
        if candidate:
            return candidate

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for path in (("delta", "content"), ("message", "content"), ("message",), ("delta",), ("text",)):
                candidate = _stringify_event_path(choice, path)
                if candidate:
                    return candidate
    return None


def _stringify_event_path(payload: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _stringify_event_value(current)


def _stringify_event_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            rendered = _stringify_event_value(item)
            if rendered:
                parts.append(rendered)
        return " ".join(parts) if parts else None
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            rendered = _stringify_event_value(value.get(key))
            if rendered:
                return rendered
        try:
            return json.dumps(value, ensure_ascii=True)
        except (TypeError, ValueError):
            return str(value)
    try:
        return str(value)
    except Exception:
        return None


def _wrap_lines(text: str, width: int) -> list[str]:
    if width <= 0:
        return [text]
    return textwrap.wrap(text, width=width) or [""]


def _show_message(stdscr: curses._CursesWindow, message: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    line = message[: max(0, width - 1)]
    y = max(0, height // 2)
    x = max(0, (width - len(line)) // 2)
    _safe_addstr(stdscr, y, x, line)
    _safe_addstr(stdscr, y + 1, x, "Press any key to return"[: max(0, width - x - 1)])
    stdscr.refresh()
    stdscr.timeout(-1)
    stdscr.getch()


FUNNY_NAMES = [
    "chaos-monkey", "coffee-otter", "hamster-wheel", "noodle-inc",
    "wizard-mode", "sneaky-panda", "turbo-snail", "quantum-unicorn",
    "pixel-quest", "glitch-wizard", "banana-hammock", "retro-burrito",
    "neon-ninja", "space-cactus", "lucky-lobster", "cosmic-donut",
    "zombie-penguin", "jellyfish-jazz", "electric-lemur", "spooky-ghost",
    "grumpy-cat", "fancy-pants", "bubbles-mcgee", "twitchy-turtle",
    "mysterious-otter", "dancing-potato", "sleepy-koala", "hyper-hedgehog",
    "silky-salamander", "jolly-jellyfish", "bouncy-badger", "wiggly-worm",
]


def _generate_funny_name() -> str:
    """Generate a random funny name for unnamed sessions."""
    return random.choice(FUNNY_NAMES)


def _confirm_dialog(
    stdscr: curses._CursesWindow,
    title: str,
    lines: list[str],
) -> bool:
    height, width = stdscr.getmaxyx()
    content_width = max([len(title), *[len(line) for line in lines]])
    box_width = min(width - 4, content_width + 4)
    box_height = min(height - 2, len(lines) + 4)
    top = max(1, (height - box_height) // 2)
    left = max(1, (width - box_width) // 2)

    for row in range(box_height):
        _safe_addstr(stdscr, top + row, left, " " * box_width)

    _safe_addstr(stdscr, top + 1, left + 2, title[: box_width - 4])
    for idx, line in enumerate(lines, start=2):
        if idx >= box_height - 1:
            break
        _safe_addstr(stdscr, top + idx, left + 2, line[: box_width - 4])

    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key in (10, 13):
            return True
        if key == 27:
            return False


def _safe_addstr(stdscr: curses._CursesWindow, y: int, x: int, text: str) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    if x + len(text) >= width:
        text = text[: max(0, width - x - 1)]
    try:
        stdscr.addstr(y, x, text)
    except curses.error:
        pass
