"""Session action helpers that interact with tmux and curses."""

from __future__ import annotations

import curses
import subprocess

from .logger import Logger
from .tmux_manager import TmuxManager


def do_attach(
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
            new_name = tmux.rename_session_to_project(session_name)
            if new_name:
                logger.info("rename", f"auto-renamed session from {session_name} to {new_name}")

        curses.doupdate()
        stdscr.clear()
        stdscr.refresh()
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

    return new_name or session_name
