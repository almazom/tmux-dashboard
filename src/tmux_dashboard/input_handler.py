"""Keyboard input handling and dashboard loop."""

from __future__ import annotations

import curses
import random
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from .config import Config
from .logger import Logger
from .models import SortMode
from .tmux_manager import TmuxError, TmuxManager
from .ui import DashboardUI, UiState, UiStatus


@dataclass
class Action:
    kind: str
    session_name: Optional[str] = None


def run_dashboard(
    tmux: TmuxManager,
    config: Config,
    logger: Logger,
    pending_status: Optional[object] = None,
) -> Optional[Action]:
    def _main(stdscr: "curses._CursesWindow") -> Optional[Action]:
        ui = DashboardUI(stdscr, config.color)
        ui.init()

        status = None
        if pending_status:
            message = getattr(pending_status, "message", "")
            level = getattr(pending_status, "level", "info")
            status = UiStatus(message=message, level=level)

        # Initialize sort mode from config
        sort_mode = config.sort_mode
        sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
        if list_status:
            status = list_status
        selected_index = 0
        last_attached_session: str | None = None  # Track last attached session
        filter_text = ""
        in_search = False
        help_visible = False
        last_preview_session: str | None = None
        last_preview_at = 0.0
        cached_preview = None
        cached_pane_capture = None
        preview_interval = 0.5

        while True:
            # Reinitialize curses state after returning from attach
            stdscr.clear()
            stdscr.timeout(100)

            filtered = _filter_sessions(sessions, filter_text)
            selected_index = _clamp_index(selected_index, len(filtered))

            preview = None
            pane_capture = None
            if filtered and config.preview_lines > 0:
                current_session = filtered[selected_index].name
                now = time.monotonic()
                should_refresh = (
                    current_session != last_preview_session
                    or (now - last_preview_at) >= preview_interval
                )
                if should_refresh:
                    try:
                        preview = tmux.get_session_details(current_session)
                        # Also capture live pane content
                        pane_capture = tmux.capture_pane_text(current_session)
                        cached_preview = preview
                        cached_pane_capture = pane_capture
                        last_preview_session = current_session
                        last_preview_at = now
                    except TmuxError as exc:
                        status = UiStatus(str(exc), level="error")
                        logger.error("preview", str(exc), current_session)
                        cached_preview = None
                        cached_pane_capture = None
                        last_preview_session = current_session
                        last_preview_at = now
                else:
                    preview = cached_preview
                    pane_capture = cached_pane_capture

            state = UiState(
                sessions=filtered,
                selected_index=selected_index,
                filter_text=filter_text,
                in_search=in_search,
                help_visible=help_visible,
                status=status,
                preview=preview.windows if preview else None,
                pane_capture=pane_capture,
                sort_mode=sort_mode,
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
                    if filtered:
                        return Action(kind="attach", session_name=filtered[selected_index].name)
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
                if num <= len(filtered):
                    session_name = filtered[num - 1].name
                    last_attached_session = session_name
                    actual_session_name = _do_attach(
                        stdscr,
                        tmux,
                        session_name,
                        logger,
                        auto_rename_on_detach=config.auto_rename_on_detach,
                    )
                    last_attached_session = actual_session_name or session_name
                    sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
                    status = list_status or UiStatus(f"Returned from {last_attached_session}", level="info")
                    filtered = _filter_sessions(sessions, filter_text)
                    if last_attached_session:
                        new_index = _find_session_index(filtered, last_attached_session)
                        selected_index = new_index
                    continue
                else:
                    status = UiStatus(f"No session #{num}", level="warning")
                    continue

            if key == curses.KEY_UP:
                selected_index = max(0, selected_index - 1)
                continue
            if key == curses.KEY_DOWN:
                selected_index = min(max(0, len(filtered) - 1), selected_index + 1)
                continue
            if key in (10, 13):
                if filtered:
                    # Handle attach within the curses context
                    session_name = filtered[selected_index].name
                    last_attached_session = session_name  # Remember which session we attached to
                    actual_session_name = _do_attach(
                        stdscr,
                        tmux,
                        session_name,
                        logger,
                        auto_rename_on_detach=config.auto_rename_on_detach,
                    )
                    # Update last_attached_session with the new name if it was renamed
                    last_attached_session = actual_session_name or session_name
                    # Refresh session list after returning from attach
                    sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
                    status = list_status or UiStatus(f"Returned from {last_attached_session}", level="info")
                    # Re-apply filter and restore cursor to the session we just detached from
                    filtered = _filter_sessions(sessions, filter_text)
                    if last_attached_session:
                        new_index = _find_session_index(filtered, last_attached_session)
                        # Debug: log if we couldn't find the session
                        session_names = [s.name for s in filtered]
                        if new_index == 0 and filtered and filtered[0].name != last_attached_session:
                            # Session not found, log for debugging
                            logger.warn("cursor_restore", f"Session '{last_attached_session}' not found in filtered list: {session_names}")
                        selected_index = new_index
                    else:
                        selected_index = 0
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
            if key == ord("d"):
                if not filtered:
                    status = UiStatus("No sessions to delete", level="warning")
                    continue
                target = filtered[selected_index]
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
                        logger.info("delete", "session deleted", target.name)
                        sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
                        status = list_status or UiStatus("Session deleted", level="info")
                    except TmuxError as exc:
                        logger.error("delete", str(exc), target.name)
                        status = UiStatus(str(exc), level="error")
                else:
                    status = UiStatus("Delete canceled", level="warning")
                continue
            if key == ord("R"):  # Shift+r for rename
                if not filtered:
                    status = UiStatus("No sessions to rename", level="warning")
                    continue
                target = filtered[selected_index]
                new_name = _prompt_input_popup(stdscr, "Rename session")
                if new_name and new_name != target.name:
                    try:
                        tmux.rename_session(target.name, new_name)
                        logger.info("rename", f"renamed {target.name} to {new_name}")
                        sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
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
                sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
                status = list_status or UiStatus("Session list refreshed", level="info")
                continue

            if key == ord("s"):
                # Cycle to next sort mode
                new_mode = sort_mode.next_mode()
                sort_mode = new_mode
                # Save to config
                config.save_sort_mode(new_mode)
                # Re-sort sessions
                sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
                status = list_status or UiStatus(f"Sort mode: {new_mode.label} ({new_mode.description})", level="info")
                selected_index = 0  # Reset to top after re-sort
                continue

        return None

    return curses.wrapper(_main)


def _do_attach(
    stdscr: "curses._CursesWindow",
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    auto_rename_on_detach: bool = True,
) -> Optional[str]:
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


def _safe_list_sessions(tmux: TmuxManager, logger: Logger, sort_mode: SortMode = SortMode.DEFAULT) -> tuple[list, Optional[UiStatus]]:
    try:
        return tmux.list_sessions(sort_mode), None
    except TmuxError as exc:
        logger.error("session_list", str(exc))
        return [], UiStatus(str(exc), level="error")


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


def _prompt_input(stdscr: "curses._CursesWindow", prompt: str) -> Optional[str]:
    height, width = stdscr.getmaxyx()
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    stdscr.nodelay(False)

    buffer: list[str] = []
    while True:
        try:
            stdscr.move(height - 1, 0)
            stdscr.clrtoeol()
        except curses.error:
            pass
        display = f"{prompt}{''.join(buffer)}"
        _safe_addstr(stdscr, height - 1, 0, display[: max(0, width - 1)])
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
            buffer.append(chr(key))

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    value = "".join(buffer).strip()
    return value or None


def _prompt_input_popup(stdscr: "curses._CursesWindow", title: str, default: str = "") -> Optional[str]:
    height, width = stdscr.getmaxyx()
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    stdscr.nodelay(False)

    prompt = "Enter session name:"
    help_text = "Enter=confirm  Esc=cancel"

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
            if len(buffer) < 50:
                buffer.append(chr(key))

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    value = "".join(buffer).strip()
    return value or None


FUNNY_NAMES = [
    "chaos-monkey", "coffee-otter", "hamster-wheel", "noodle-inc",
    "wizard-mode", "sneaky-panda", " turbo-snail", "quantum-unicorn",
    "pixel-quest", "glitch-wizard", " banana-hammock", "retro-burrito",
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
    stdscr: "curses._CursesWindow",
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


def _safe_addstr(stdscr: "curses._CursesWindow", y: int, x: int, text: str) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    if x + len(text) >= width:
        text = text[: max(0, width - x - 1)]
    try:
        stdscr.addstr(y, x, text)
    except curses.error:
        pass
