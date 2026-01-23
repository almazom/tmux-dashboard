"""Keyboard input handling and dashboard loop."""

from __future__ import annotations

import curses
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .headless import (
    HeadlessRegistry,
    HeadlessSession,
    build_headless_session,
    build_headless_shell_command,
)
from .headless_prompts import prompt_headless_request
from .headless_state import (
    apply_headless_metadata,
    auto_cleanup_headless,
    collect_headless_status,
    sync_headless_completion,
)
from .headless_view import HeadlessLogTail, run_headless_view
from .logger import Logger
from .models import SessionInfo, SortMode
from .prompts import confirm_dialog, prompt_input_popup
from .session_actions import do_attach
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
        sessions, headless_map, list_status = _refresh_sessions(
            tmux,
            logger,
            sort_mode,
            headless_registry,
            config,
        )
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
        headless_tailers: dict[str, HeadlessLogTail] = {}
        preview_interval = 0.5

        while True:
            # Reinitialize curses state after returning from attach
            stdscr.clear()
            stdscr.timeout(100)

            filtered = _filter_sessions(sessions, filter_text)
            ordered, headless_start_index, interactive_sessions = _group_headless_sessions(filtered)
            selected_index = _clamp_index(selected_index, len(ordered))
            if headless_tailers:
                active = set(headless_map.keys())
                headless_tailers = {
                    name: tailer for name, tailer in headless_tailers.items() if name in active
                }

            preview = None
            pane_capture = None
            preview_title = "Live Preview:"
            if ordered and config.preview_lines > 0:
                selected_session = ordered[selected_index]
                current_session = selected_session.name
                now = time.monotonic()
                refresh_interval = preview_interval
                if selected_session.is_headless:
                    refresh_interval = max(preview_interval, config.headless_refresh_seconds)
                should_refresh = (
                    current_session != last_preview_session
                    or (now - last_preview_at) >= refresh_interval
                )
                if should_refresh:
                    if selected_session.is_headless:
                        headless_session = headless_map.get(current_session)
                        if headless_session is None:
                            pane_capture = ["(headless output unavailable)"]
                        else:
                            tailer = headless_tailers.get(current_session)
                            if tailer is None or str(tailer.path) != headless_session.output_path:
                                tailer = HeadlessLogTail(
                                    headless_session.output_path,
                                    config.headless_max_events,
                                )
                                headless_tailers[current_session] = tailer
                            pane_capture = tailer.poll()
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
                            run_headless_view(
                                stdscr,
                                target.name,
                                tmux,
                                headless_registry,
                                config,
                                logger,
                            )
                            sessions, headless_map, list_status = _refresh_sessions(
                                tmux,
                                logger,
                                sort_mode,
                                headless_registry,
                                config,
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
                        config,
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
                        run_headless_view(
                            stdscr,
                            selected_session.name,
                            tmux,
                            headless_registry,
                            config,
                            logger,
                        )
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                            config,
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
                        config,
                        auto_rename_on_detach=config.auto_rename_on_detach,
                    )
                    continue
                status = UiStatus("No sessions to attach", level="warning")
                continue
            if key == ord("n"):
                # Prompt with empty default - user can type name or press Enter for random
                name = prompt_input_popup(stdscr, "New tmux session", default="")
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
                request = prompt_headless_request(stdscr, config)
                if request is None:
                    status = UiStatus("Headless create canceled", level="warning")
                    continue

                workdir_raw, agent_raw, model, instruction = request
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

                selected_model = model.strip()

                existing_names = {s.name for s in sessions}
                session_name = _build_headless_session_name(
                    agent,
                    workdir_path.name or "headless",
                    existing_names,
                )
                output_path = headless_registry.output_path(session_name)
                command_template = config.headless_agents[agent]
                if "{model}" in command_template and not selected_model:
                    status = UiStatus("Model is required for this headless agent", level="error")
                    continue
                try:
                    command_list = build_headless_shell_command(
                        command_template,
                        instruction,
                        str(output_path),
                        str(workdir_path),
                        agent,
                        selected_model,
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
                        model=selected_model or None,
                        instruction=instruction,
                        workdir=str(workdir_path),
                        output_path=str(output_path),
                        flow=None,
                        command=command_preview,
                    )
                    headless_registry.record(headless_session)
                    logger.info("headless_create", f"headless session created: {agent}", session_name)
                    run_headless_view(
                        stdscr,
                        session_name,
                        tmux,
                        headless_registry,
                        config,
                        logger,
                    )
                    sessions, headless_map, list_status = _refresh_sessions(
                        tmux,
                        logger,
                        sort_mode,
                        headless_registry,
                        config,
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
                confirm = confirm_dialog(
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
                        _delete_session(tmux, headless_registry, target)
                        logger.info("delete", "session deleted", target.name)
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                            config,
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
                new_name = prompt_input_popup(stdscr, "Rename session")
                if new_name and new_name != target.name:
                    try:
                        tmux.rename_session(target.name, new_name)
                        logger.info("rename", f"renamed {target.name} to {new_name}")
                        sessions, headless_map, list_status = _refresh_sessions(
                            tmux,
                            logger,
                            sort_mode,
                            headless_registry,
                            config,
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
                    config,
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
                    config,
                )
                status = list_status or UiStatus(f"Sort mode: {new_mode.label} ({new_mode.description})", level="info")
                selected_index = 0  # Reset to top after re-sort
                continue

        return None

    return curses.wrapper(_main)


def _attach_and_refresh(
    stdscr: curses._CursesWindow,
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    sort_mode: SortMode,
    filter_text: str,
    headless_registry: HeadlessRegistry,
    config: Config,
    auto_rename_on_detach: bool = True,
) -> tuple[list, dict[str, HeadlessSession], UiStatus | None, int, str]:
    actual_session_name = do_attach(
        stdscr,
        tmux,
        session_name,
        logger,
        auto_rename_on_detach=auto_rename_on_detach,
    )
    if not actual_session_name:
        actual_session_name = session_name

    sessions, headless_map, list_status = _refresh_sessions(
        tmux,
        logger,
        sort_mode,
        headless_registry,
        config,
    )
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


def _delete_session(
    tmux: TmuxManager,
    headless_registry: HeadlessRegistry,
    session: SessionInfo,
) -> None:
    if session.is_headless and session.headless_status == "missing":
        headless_registry.forget(session.name)
        return
    tmux.kill_session(session.name)
    if session.is_headless:
        headless_registry.forget(session.name)


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
    config: Config,
) -> tuple[list[SessionInfo], dict[str, HeadlessSession], UiStatus | None]:
    sessions, list_status = _safe_list_sessions(tmux, logger, sort_mode)
    headless_map = headless_registry.load_all()
    status_map = collect_headless_status(tmux, headless_map)
    if headless_map:
        headless_map = sync_headless_completion(
            headless_registry,
            logger,
            headless_map,
            status_map,
            config.headless_notify_on_complete,
        )
    if headless_map and config.headless_auto_cleanup:
        headless_map = auto_cleanup_headless(
            tmux,
            headless_registry,
            logger,
            headless_map,
            status_map,
        )
    sessions = apply_headless_metadata(sessions, headless_map, status_map)
    return sessions, headless_map, list_status


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


def _build_headless_session_name(agent: str, project: str, existing_names: set[str]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_agent = _sanitize_session_component(agent)
    safe_project = _sanitize_session_component(project)
    base = f"hl_{safe_agent}_{safe_project}_{timestamp}"
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
