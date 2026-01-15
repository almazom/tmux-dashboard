"""Data models for tmux-dashboard UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaneInfo:
    pane_id: str
    current_command: str | None


@dataclass(frozen=True)
class WindowInfo:
    name: str
    panes: list[PaneInfo]


@dataclass(frozen=True)
class SessionInfo:
    name: str
    attached: bool
    windows: int
    is_ai_session: bool = False
