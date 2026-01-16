"""Data models for tmux-dashboard UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SortMode(Enum):
    """Sorting modes for sessions/windows."""

    ACTIVITY = "activity"
    NAME = "name"
    AI_FIRST = "ai_first"
    WINDOWS_COUNT = "windows_count"

    @property
    def label(self) -> str:
        """Human-readable label for the sort mode."""
        labels = {
            SortMode.ACTIVITY: "activity",
            SortMode.NAME: "name",
            SortMode.AI_FIRST: "ai_first",
            SortMode.WINDOWS_COUNT: "count",
        }
        return labels[self]

    @property
    def description(self) -> str:
        """Description of what this sort mode does."""
        descriptions = {
            SortMode.ACTIVITY: "active → recent → name",
            SortMode.NAME: "alphabetical A→Z",
            SortMode.AI_FIRST: "AI sessions → name",
            SortMode.WINDOWS_COUNT: "most windows first",
        }
        return descriptions[self]

    def next_mode(self) -> "SortMode":
        """Get the next sort mode in cycle."""
        modes = list(SortMode)
        current_index = modes.index(self)
        return modes[(current_index + 1) % len(modes)]

    @classmethod
    def from_string(cls, value: str) -> "SortMode":
        """Parse SortMode from string."""
        for mode in cls:
            if mode.value == value.lower():
                return mode
        return cls.DEFAULT

    # Default sort mode
    DEFAULT: "SortMode" = AI_FIRST


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
