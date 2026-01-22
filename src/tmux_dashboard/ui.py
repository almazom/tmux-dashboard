"""Curses UI rendering utilities."""

from __future__ import annotations

import curses
from dataclasses import dataclass

from .models import SessionInfo, SortMode, WindowInfo


@dataclass
class UiStatus:
    message: str
    level: str = "info"


@dataclass
class UiState:
    sessions: list[SessionInfo]
    selected_index: int
    filter_text: str
    in_search: bool
    help_visible: bool
    status: UiStatus | None
    preview: list[WindowInfo] | None
    pane_capture: list[str] | None = None
    sort_mode: SortMode = SortMode.DEFAULT


# Margin settings (top, left) - in terminal cells
MARGIN_TOP = 2
MARGIN_LEFT = 4

# Line spacing (0 = compact, 1 = normal spacing, 2 = double spacing)
LINE_SPACING = 0


class DashboardUI:
    def __init__(self, stdscr: curses._CursesWindow, color_mode: str) -> None:
        self.stdscr = stdscr
        self.color_mode = color_mode
        self.colors_enabled = False
        self.color_pairs: dict[str, int] = {}

    def init(self) -> None:
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        if self.color_mode != "never" and curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                self.colors_enabled = True
            except curses.error:
                self.colors_enabled = False

        if self.colors_enabled:
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(3, curses.COLOR_GREEN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
            curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(6, curses.COLOR_RED, -1)
            curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(8, curses.COLOR_GREEN, curses.COLOR_BLACK)
            self.color_pairs = {
                "title": 1,
                "selected": 2,
                "attached": 3,
                "detached": 4,
                "status": 5,
                "warning": 6,
                "help": 7,
                "ai_session": 8,
            }

    def render(self, state: UiState, preview_lines: int) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        # Apply margins
        content_top = MARGIN_TOP
        content_left = MARGIN_LEFT
        content_width = max(1, width - MARGIN_LEFT * 2)
        content_height = max(1, height - MARGIN_TOP * 2)

        self._draw_title(state, content_top, content_left, content_width)
        list_top = content_top + 2
        list_bottom = max(content_top + 3, content_top + content_height - 3)
        list_height = list_bottom - list_top + 1
        list_width = max(30, int(content_width * 0.55))
        preview_left = content_left + list_width + 2

        self._draw_sessions(state, list_top, list_height, list_width, content_left)
        self._draw_preview(state, list_top, list_height, preview_left, width, preview_lines)
        self._draw_footer(state, height, width, content_left)

        if state.help_visible:
            self._draw_help_overlay(width, height)

        self.stdscr.refresh()

    def _draw_title(self, state: UiState, top: int, left: int, width: int) -> None:
        title = "Tmux Dashboard"
        # Show current sort mode in title
        sort_indicator = f"[Sort: {state.sort_mode.label}]"
        hint = "[F1 Help] [s Sort] [q Exit]"
        line = f"{title} {sort_indicator} {' ' * max(1, width - len(title) - len(sort_indicator) - len(hint) - 4)}{hint}"
        self._addstr(top, left, line[: width - 1], self._attr("title"))

    def _draw_sessions(self, state: UiState, top: int, height: int, width: int, left: int) -> None:
        sessions = state.sessions
        if not sessions:
            self._addstr(top, left, "No sessions found. Press 'n' to create one.")
            return

        start = max(0, state.selected_index - height + 1)
        end = min(len(sessions), start + height)

        for idx, session in enumerate(sessions[start:end], start=start):
            row = top + (idx - start) * (1 + LINE_SPACING)

            # Number prefix for quick attach (only show for first 9)
            if idx < 9:
                num_prefix = f"{idx + 1}. "
            else:
                num_prefix = "  "
            # AI indicator
            ai_prefix = "🤖 " if session.is_ai_session else ""
            name = ai_prefix + session.name
            status = "attached" if session.attached else "detached"
            windows = f"windows: {session.windows}"
            label = f"{num_prefix}{name:<18} [{status:<8}] {windows}"

            attr = 0
            if idx == state.selected_index:
                attr = self._attr("selected")
            elif session.is_ai_session:
                attr = self._attr("ai_session")
            elif session.attached:
                attr = self._attr("attached")
            else:
                attr = self._attr("detached")

            self._addstr(row, left, label[: width - 1], attr)

    def _draw_preview(
        self,
        state: UiState,
        top: int,
        height: int,
        left: int,
        width: int,
        preview_lines: int,
    ) -> None:
        if left >= width - 2:
            return

        self._addstr(top, left, "Live Preview:", self._attr("title"))

        # Show captured pane content if available
        if state.pane_capture:
            lines = state.pane_capture
            max_lines = min(preview_lines - 1, height - 2)
            for idx, line in enumerate(lines[:max_lines], start=1):
                # Truncate long lines for preview
                display_line = line[: max(0, width - left - 3)]
                self._addstr(top + idx, left, display_line)
            return

        # Fallback to window info preview
        lines: list[str] = []
        if state.preview:
            for window in state.preview:
                lines.append(f"window: {window.name}")
                for pane in window.panes:
                    cmd = pane.current_command or "(empty)"
                    lines.append(f"  {cmd}")
        else:
            lines.append("(no preview)")

        max_lines = min(preview_lines, height - 2)
        for idx, line in enumerate(lines[:max_lines], start=1):
            self._addstr(top + idx, left, line[: max(1, width - left - 1)])

    def _draw_footer(self, state: UiState, height: int, width: int, left: int) -> None:
        footer = f"Keys: 1-9 quick attach  Up/Down move  Enter attach  n new  d delete  R rename  / search  r refresh  s sort [{state.sort_mode.label}]"
        if state.in_search:
            footer = f"Search: {state.filter_text} (Esc to clear)"
        elif state.help_visible:
            footer = "Help: F1/? to close"

        status_msg = state.status.message if state.status else ""
        status_line = status_msg[: max(0, width - left - 1)]

        footer_line = footer[: max(0, width - left - 1)]
        self._addstr(height - 2, left, footer_line)

        attr = self._attr("status") if state.status else 0
        self._addstr(height - 1, left, status_line, attr)

    def _draw_help_overlay(self, width: int, height: int) -> None:
        lines = [
            "Help",
            "1-9: quick attach to session",
            "Enter: attach",
            "n: create new session",
            "d: delete session",
            "/: search",
            "r: refresh",
            "s: cycle sort mode",
            "F1 or ?: help",
            "q / Ctrl+C: exit",
        ]
        box_width = max(len(line) for line in lines) + 4
        box_height = len(lines) + 2
        top = max(1, (height - box_height) // 2)
        left = max(1, (width - box_width) // 2)

        for y in range(box_height):
            self._addstr(top + y, left, " " * box_width, self._attr("help"))

        for idx, line in enumerate(lines, start=1):
            self._addstr(top + idx, left + 2, line, self._attr("help"))

    def _attr(self, name: str) -> int:
        if not self.colors_enabled:
            if name == "selected":
                return curses.A_REVERSE
            return 0
        pair = self.color_pairs.get(name, 0)
        return curses.color_pair(pair)

    def _addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = self.stdscr.getmaxyx()
        if y < 0 or y >= height or x < 0 or x >= width:
            return
        if x + len(text) >= width:
            text = text[: max(0, width - x - 1)]
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass
