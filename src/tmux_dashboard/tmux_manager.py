"""tmux session management helpers."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import PaneInfo, SessionInfo, SortMode, WindowInfo

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
    "codex",
    "cladcode",
]
AI_AGENT_KEYWORDS = {
    "codex": ["codex"],
    "cladcode": ["cladcode"],
}


def _contains_ai_keyword(value: str) -> bool:
    lowered = value.lower()
    return any(keyword in lowered for keyword in AI_KEYWORDS)


def _match_ai_agent(value: str) -> str | None:
    lowered = value.lower()
    for agent, keywords in AI_AGENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return agent
    return None

try:
    import libtmux  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    libtmux = None


class TmuxError(RuntimeError):
    pass


@dataclass
class SessionDetails:
    windows: list[WindowInfo]


@dataclass(frozen=True)
class SessionRuntimeStatus:
    exists: bool
    running: bool
    exit_code: int | None = None


class TmuxManager:
    def __init__(self) -> None:
        self._libtmux = libtmux
        self._cached_project_name: str | None = None

    def detect_project_name(self) -> str:
        """Detect project name from current working directory.

        Strategy:
        1. Use the basename of the current working directory
        2. If no basename (root), use 'default'
        """
        if self._cached_project_name:
            return self._cached_project_name

        cwd = Path.cwd()

        name = cwd.name or "default"
        self._cached_project_name = name
        return self._cached_project_name

    @staticmethod
    def _project_name_from_path(path: str | None) -> str | None:
        if not path:
            return None
        try:
            name = Path(path).name
        except (TypeError, ValueError):
            return None
        return name or None

    def _get_session_active_path(self, session_name: str) -> str | None:
        if self._libtmux:
            try:
                server = self._server()
                if server:
                    session = server.sessions.get(session_name=session_name)
                    if session:
                        window = getattr(session, "attached_window", None) or getattr(session, "active_window", None)
                        if window is None:
                            windows = list(session.windows)
                            window = windows[0] if windows else None
                        if window:
                            pane = getattr(window, "attached_pane", None) or getattr(window, "active_pane", None)
                            if pane is None:
                                panes = list(window.panes)
                                pane = panes[0] if panes else None
                            if pane:
                                path = getattr(pane, "pane_current_path", None)
                                if path:
                                    return str(path)
            except Exception:
                pass

        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-t", session_name, "-F", "#{window_active}::#{pane_active}::#{pane_current_path}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode != 0:
                return None
            fallback_path = None
            for line in result.stdout.splitlines():
                if not line.strip():
                    continue
                window_active, pane_active, path = (line.split("::", 2) + ["", "", ""])[:3]
                if not path:
                    continue
                if window_active.strip() == "1" and pane_active.strip() == "1":
                    return path
                if fallback_path is None:
                    fallback_path = path
            return fallback_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _rename_window(self, session_name: str, new_name: str) -> bool:
        try:
            result = subprocess.run(
                ["tmux", "rename-window", "-t", session_name, new_name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def generate_session_name(self, existing_sessions: list[SessionInfo]) -> str:
        """Generate a unique session name based on project folder.

        Rules:
        1. Use project folder name as base
        2. If exists, append incrementing number
        3. Handle edge cases gracefully
        """
        base_name = self.detect_project_name()
        existing_names = {s.name for s in existing_sessions}

        # If base name is available, use it
        if base_name not in existing_names:
            return base_name

        # Try incrementing numbers
        for i in range(2, 100):
            candidate = f"{base_name}-{i}"
            if candidate not in existing_names:
                return candidate

        # Fallback: use timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{base_name}-{timestamp}"

    def _server(self):
        if not self._libtmux:
            return None
        try:
            return self._libtmux.Server()
        except Exception as exc:  # pragma: no cover - defensive
            raise TmuxError(f"tmux server unavailable: {exc}") from exc

    def list_sessions(self, sort_mode: SortMode = SortMode.DEFAULT) -> list[SessionInfo]:
        sessions = self._get_sessions_raw()

        # Detect AI sessions and enrich session info
        sessions_with_ai = []
        for session in sessions:
            is_ai, agent = self._detect_ai_session(session.name)
            sessions_with_ai.append(
                SessionInfo(
                    name=session.name,
                    attached=session.attached,
                    windows=session.windows,
                    is_ai_session=is_ai,
                    ai_agent=agent,
                )
            )

        # Sort based on the selected mode
        return self._sort_sessions(sessions_with_ai, sort_mode)

    def most_recent_session(self) -> SessionInfo | None:
        """Return the most recently active tmux session if available."""
        sessions_with_activity = self._list_sessions_activity_cli()
        if sessions_with_activity:
            return max(sessions_with_activity, key=lambda item: item[1])[0]

        sessions = self.list_sessions(sort_mode=SortMode.ACTIVITY)
        return sessions[0] if sessions else None

    def _sort_sessions(self, sessions: list[SessionInfo], mode: SortMode) -> list[SessionInfo]:
        """Sort sessions according to the specified mode."""
        if mode == SortMode.NAME:
            # Alphabetical A→Z
            return sorted(sessions, key=lambda s: s.name.lower())
        elif mode == SortMode.ACTIVITY:
            # Active/attached first, then by name
            return sorted(sessions, key=lambda s: (not s.attached, s.name.lower()))
        elif mode == SortMode.AI_FIRST:
            # AI sessions first, then by name
            return sorted(sessions, key=lambda s: (not s.is_ai_session, s.name.lower()))
        elif mode == SortMode.WINDOWS_COUNT:
            # Most windows first, then by name
            return sorted(sessions, key=lambda s: (-s.windows, s.name.lower()))
        else:
            # Default to AI_FIRST
            return sorted(sessions, key=lambda s: (not s.is_ai_session, s.name.lower()))

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

    def _list_sessions_activity_cli(self) -> list[tuple[SessionInfo, int]]:
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "list-sessions",
                    "-F",
                    "#{session_name}::#{session_attached}::#{session_windows}::#{session_activity}::#{session_last_attached}",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return []
        if result.returncode != 0:
            if "no server running" in result.stderr.lower():
                return []
            return []

        sessions: list[tuple[SessionInfo, int]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = (line.split("::", 4) + ["", "", "", "", ""])[:5]
            name, attached, windows, activity, last_attached = parts
            activity_ts = int(activity) if activity.isdigit() else 0
            last_attached_ts = int(last_attached) if last_attached.isdigit() else 0
            score = max(activity_ts, last_attached_ts)
            sessions.append(
                (
                    SessionInfo(
                        name=name,
                        attached=self._normalize_attached(attached),
                        windows=int(windows) if windows.isdigit() else 0,
                    ),
                    score,
                )
            )

        return sessions

    def _detect_ai_session(self, session_name: str) -> tuple[bool, str | None]:
        """Detect whether a session is AI-related and, if possible, which agent."""
        for command in self._iter_pane_commands(session_name):
            agent = _match_ai_agent(command)
            if agent:
                return True, agent
            if _contains_ai_keyword(command):
                return True, None

        agent = _match_ai_agent(session_name)
        if agent:
            return True, agent
        if _contains_ai_keyword(session_name):
            return True, None
        return False, None

    def _iter_pane_commands(self, session_name: str) -> list[str]:
        commands: list[str] = []
        if self._libtmux:
            try:
                details = self.get_session_details(session_name)
                if details:
                    for window in details.windows:
                        for pane in window.panes:
                            if pane.current_command:
                                commands.append(pane.current_command)
                    if commands:
                        return commands
            except Exception:
                commands = []

        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_current_command}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                commands = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            commands = []
        return commands

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

    def create_session_with_cd(self, name: str, directory: str | None = None) -> None:
        """Create a new tmux session and automatically cd to the specified directory.

        Args:
            name: The session name
            directory: Directory to cd into (defaults to current working directory project)

        If directory is None, it will use the detected project directory.
        """
        # Determine the directory to cd into
        if directory is None:
            target_dir = str(Path.cwd())
        else:
            target_dir = directory

        if self._libtmux:
            server = self._server()
            if server is None:
                raise TmuxError("tmux server unavailable")
            # Create session with cd command
            server.new_session(
                session_name=name,
                detach=True,
                start_directory=target_dir,
            )
            self._rename_window(name, name)
            return

        # Use tmux CLI with -c to set the start directory
        result = subprocess.run([
            "tmux", "new-session", "-d", "-s", name, "-c", target_dir
        ], capture_output=True, text=True)

        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux new-session failed")

        self._rename_window(name, name)
        # Send the clear command to the first window
        subprocess.run([
            "tmux", "send-keys", "-t", f"{name}:0", "clear", "Enter"
        ], capture_output=True)

    def create_session_with_command(self, name: str, command: list[str], directory: str | None = None) -> None:
        """Create a new tmux session and run a command in its first window."""
        target_dir = str(Path.cwd()) if directory is None else directory
        if not command:
            raise TmuxError("tmux command missing")

        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", target_dir, *command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux new-session failed")
        self._rename_window(name, name)

    def attach_command(self, name: str) -> list[str]:
        # Check if already inside tmux
        tmux_env = os.environ.get("TMUX")
        if tmux_env:
            # Already inside tmux - use switch-client
            return ["tmux", "switch-client", "-t", name]
        # Not inside tmux - use attach-session
        return ["tmux", "attach-session", "-t", name]

    def rename_session_to_project(self, session_name: str) -> str | None:
        """Rename a session to match the session's active pane directory basename.

        Returns:
            The new name if renamed, None if failed or no change needed.
        """
        try:
            session_path = self._get_session_active_path(session_name)
            new_name = self._project_name_from_path(session_path)
            if not new_name:
                return None

            # Don't rename if already has this name
            if session_name == new_name:
                self._rename_window(session_name, new_name)
                return None

            # Use libtmux if available
            if self._libtmux:
                server = self._server()
                if server:
                    session = server.sessions.get(session_name=session_name)
                    if session:
                        session.rename_session(new_name)
                        self._rename_window(new_name, new_name)
                        return new_name

            # CLI fallback
            result = subprocess.run(
                ["tmux", "rename-session", "-t", session_name, new_name],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self._rename_window(new_name, new_name)
                return new_name

        except Exception:
            pass

        return None

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
            self._rename_window(new_name, new_name)
            return

        result = subprocess.run(
            ["tmux", "rename-session", "-t", old_name, new_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux rename-session failed")
        self._rename_window(new_name, new_name)

    def send_keys(self, session_name: str, keys: list[str], enter: bool = True) -> None:
        if not keys and not enter:
            return
        command = ["tmux", "send-keys", "-t", f"{session_name}:0", *keys]
        if enter:
            command.append("Enter")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "tmux send-keys failed")

    def get_session_details(self, name: str) -> SessionDetails | None:
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

    def capture_pane_text(self, session_name: str, pane_id: str = ".") -> list[str] | None:
        """Capture the text content of a pane for live preview.

        Args:
            session_name: The tmux session name
            pane_id: The pane index or id (defaults to current pane)

        Returns:
            List of text lines from the pane, or None if failed
        """
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", f"{session_name}:{pane_id}", "-p"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                # Take last N lines for preview
                return lines[-15:] if len(lines) > 15 else lines
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def get_session_runtime_status(self, session_name: str) -> SessionRuntimeStatus:
        """Check whether a tmux session is still running or completed."""
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_dead}::#{pane_exit_status}"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return SessionRuntimeStatus(exists=False, running=False)

        if result.returncode != 0:
            if "can't find session" in result.stderr.lower():
                return SessionRuntimeStatus(exists=False, running=False)
            return SessionRuntimeStatus(exists=True, running=False)

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return SessionRuntimeStatus(exists=True, running=False)

        running = False
        exit_codes: list[int] = []
        for line in lines:
            dead_str, exit_str = (line.split("::", 1) + ["", ""])[:2]
            if dead_str.strip() == "0":
                running = True
            if exit_str.strip().isdigit():
                exit_codes.append(int(exit_str.strip()))

        exit_code = max(exit_codes) if exit_codes else None
        return SessionRuntimeStatus(exists=True, running=running, exit_code=exit_code)

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
