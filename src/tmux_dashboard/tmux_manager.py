"""tmux session management helpers."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from .models import PaneInfo, SessionInfo, WindowInfo


# Keywords to detect AI agent sessions
AI_KEYWORDS = [
    "claude",
    "ai",
    "agent",
    "llm",
    "gpt",
    "anthropic",
    "openai",
    "copilot",
    "cursor",
]

try:
    import libtmux  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    libtmux = None


class TmuxError(RuntimeError):
    pass


@dataclass
class SessionDetails:
    windows: list[WindowInfo]


class TmuxManager:
    def __init__(self) -> None:
        self._libtmux = libtmux

    def _server(self):
        if not self._libtmux:
            return None
        try:
            return self._libtmux.Server()
        except Exception as exc:  # pragma: no cover - defensive
            raise TmuxError(f"tmux server unavailable: {exc}") from exc

    def list_sessions(self) -> list[SessionInfo]:
        sessions = self._get_sessions_raw()

        # Detect AI sessions and sort them to the top
        sessions_with_ai = []
        for session in sessions:
            is_ai = self._is_ai_session(session.name)
            sessions_with_ai.append(
                SessionInfo(
                    name=session.name,
                    attached=session.attached,
                    windows=session.windows,
                    is_ai_session=is_ai,
                )
            )

        # Sort: AI sessions first, then by name
        return sorted(
            sessions_with_ai,
            key=lambda s: (not s.is_ai_session, s.name.lower()),
        )

    def _get_sessions_raw(self) -> list[SessionInfo]:
        if self._libtmux:
            try:
                server = self._server()
                sessions = list(server.sessions) if server else []
                return [
                    SessionInfo(
                        name=session.name,
                        attached=self._normalize_attached(getattr(session, "attached", False)),
                        windows=len(getattr(session, "windows", []) or []),
                    )
                    for session in sessions
                ]
            except Exception:
                return []

        return self._list_sessions_cli()

    def _is_ai_session(self, session_name: str) -> bool:
        """Check if a session contains an AI agent by checking pane commands."""
        # Try libtmux first
        if self._libtmux:
            try:
                details = self.get_session_details(session_name)
                if details:
                    for window in details.windows:
                        for pane in window.panes:
                            if pane.current_command:
                                cmd_lower = pane.current_command.lower()
                                if any(keyword in cmd_lower for keyword in AI_KEYWORDS):
                                    return True
            except Exception:
                pass  # Fall through to CLI method

        # CLI fallback: get pane commands directly from tmux
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_current_command}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if any(keyword in line.lower() for keyword in AI_KEYWORDS):
                        return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Last resort: check session name for AI keywords
        return any(keyword in session_name.lower() for keyword in AI_KEYWORDS)

    def _list_sessions_cli(self) -> list[SessionInfo]:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_attached}:#{session_windows}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if "no server running" in result.stderr.lower():
                return []
            raise TmuxError(result.stderr.strip() or "tmux list-sessions failed")

        sessions: list[SessionInfo] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            name, attached, windows = (line.split(":", 2) + ["", ""])[:3]
            sessions.append(
                SessionInfo(
                    name=name,
                    attached=self._normalize_attached(attached),
                    windows=int(windows) if windows.isdigit() else 0,
                )
            )
        return sessions

    def create_session(self, name: str) -> None:
        if self._libtmux:
            server = self._server()
            if server is None:
                raise TmuxError("tmux server unavailable")
            server.new_session(session_name=name, detach=True)
            return

        result = subprocess.run(["tmux", "new-session", "-d", "-s", name], capture_output=True, text=True)
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux new-session failed")

    def attach_command(self, name: str) -> list[str]:
        # Check if already inside tmux
        tmux_env = os.environ.get("TMUX")
        if tmux_env:
            # Already inside tmux - use switch-client
            return ["tmux", "switch-client", "-t", name]
        # Not inside tmux - use attach-session
        return ["tmux", "attach-session", "-t", name]

    def kill_session(self, name: str) -> None:
        if self._libtmux:
            server = self._server()
            if server is None:
                raise TmuxError("tmux server unavailable")
            server.cmd("kill-session", "-t", name)
            return

        result = subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True)
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux kill-session failed")

    def rename_session(self, old_name: str, new_name: str) -> None:
        if self._libtmux:
            server = self._server()
            if server is None:
                raise TmuxError("tmux server unavailable")
            server.cmd("rename-session", "-t", old_name, new_name)
            return

        result = subprocess.run(
            ["tmux", "rename-session", "-t", old_name, new_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux rename-session failed")

    def get_session_details(self, name: str) -> Optional[SessionDetails]:
        if not self._libtmux:
            return None

        server = self._server()
        if server is None:
            return None

        session = server.sessions.get(session_name=name)
        if not session:
            return None

        windows: list[WindowInfo] = []
        for window in session.windows:
            panes: list[PaneInfo] = []
            for pane in window.panes:
                panes.append(
                    PaneInfo(
                        pane_id=str(getattr(pane, "pane_id", "")),
                        current_command=str(getattr(pane, "pane_current_command", "")) or None,
                    )
                )
            windows.append(WindowInfo(name=window.window_name, panes=panes))
        return SessionDetails(windows=windows)

    @staticmethod
    def _normalize_attached(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        try:
            return int(str(value)) > 0
        except ValueError:
            return str(value).strip().lower() in {"true", "yes", "y"}
