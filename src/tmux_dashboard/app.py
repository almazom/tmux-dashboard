"""Application entrypoint and main loop."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from .config import Config, load_config
from .headless import HeadlessRegistry
from .input_handler import run_dashboard
from .instance_lock import InstanceLock, LockAcquisitionError, ensure_single_instance
from .logger import Logger
from .tmux_manager import TmuxError, TmuxManager

CONFLICT_ACTION_ENV = "TMUX_DASHBOARD_CONFLICT_ACTION"


@dataclass
class PendingStatus:
    message: str
    level: str = "info"


def _attach_and_rename(
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    auto_rename_on_detach: bool,
    event: str,
) -> str | None:
    try:
        subprocess.run(tmux.attach_command(session_name))
    except OSError as exc:
        logger.error(event, str(exc), session_name)
        return str(exc)

    if auto_rename_on_detach:
        tmux.rename_session_to_project(session_name)
    return None


def _read_lock_info() -> dict[str, str | None]:
    lock = InstanceLock()
    return lock.get_lock_info()


def _pid_args(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _pid_tty(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "tty="],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _prompt_conflict_action(lock_info: dict[str, str | None]) -> str:
    pid_value = lock_info.get("locking_pid") or "unknown"
    pid = int(pid_value) if pid_value.isdigit() else None
    tty = _pid_tty(pid) if pid else None
    tty_display = tty or "unknown"
    print("tmux-dashboard: another instance is running.", file=sys.stderr)
    print(f"PID: {pid_value}  TTY: {tty_display}", file=sys.stderr)
    print("Choose: [a] attach  [k] take over  [q] exit", file=sys.stderr)
    while True:
        choice = input("> ").strip().lower()
        if not choice or choice in {"a", "attach"}:
            return "attach"
        if choice in {"k", "kill", "takeover"}:
            return "takeover"
        if choice in {"q", "quit", "exit"}:
            return "exit"


def _resolve_conflict_action(lock_info: dict[str, str | None]) -> str:
    action = os.environ.get(CONFLICT_ACTION_ENV, "attach").strip().lower()
    if action == "prompt":
        return _prompt_conflict_action(lock_info)
    if action in {"attach", "exit", "takeover"}:
        return action
    return "attach"


def _terminate_lock_holder(lock_info: dict[str, str | None], logger: Logger) -> bool:
    pid_value = lock_info.get("locking_pid")
    if not pid_value or not pid_value.isdigit():
        lock = InstanceLock()
        if not lock.is_locked():
            _cleanup_stale_lock_files(lock, logger)
            return True
        logger.warn("lock_takeover", "no valid pid to terminate")
        return False
    pid = int(pid_value)
    args = _pid_args(pid)
    if not args or ("tmux-dashboard" not in args and "tmux_dashboard" not in args):
        logger.warn("lock_takeover", f"pid {pid} does not look like tmux-dashboard")
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        logger.error("lock_takeover", str(exc))
        return False

    lock = InstanceLock()
    start = time.monotonic()
    while (time.monotonic() - start) < 3.0:
        if not lock.is_locked():
            return True
        time.sleep(0.1)
    logger.warn("lock_takeover", "lock still held after termination attempt")
    return False


def _cleanup_stale_lock_files(lock: InstanceLock, logger: Logger) -> None:
    for path in (lock.lock_file, lock.pid_file):
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warn("lock_cleanup", f"failed to remove {path}: {exc}")


def _handle_lock_conflict(
    tmux: TmuxManager,
    config: Config,
    logger: Logger,
) -> str:
    lock_info = _read_lock_info()
    action = _resolve_conflict_action(lock_info)
    if action == "takeover":
        if _terminate_lock_holder(lock_info, logger):
            return "retry"
        action = "attach"

    if action == "exit":
        logger.info("exit", "dashboard locked, exiting")
        return "exit"

    try:
        target_session = tmux.most_recent_session()
        if target_session:
            logger.info("auto_attach", "another dashboard running, attaching to session")
            if _attach_and_rename(
                tmux,
                target_session.name,
                logger,
                config.auto_rename_on_detach,
                event="auto_attach",
            ):
                return "exit"
            return "exit"
        logger.info("exit", "another dashboard running, no sessions to attach")
        return "exit"
    except TmuxError as exc:
        logger.error("attach", f"failed to attach: {exc}")
        return "exit"


def run() -> None:
    # Load config first to get settings
    config = load_config()
    logger = Logger(config.log_path)
    tmux = TmuxManager()
    headless_registry = HeadlessRegistry(config.headless_state_dir, config.headless_output_dir)

    while True:
        try:
            lock = ensure_single_instance(exit_on_conflict=False, verbose=False)
            break
        except LockAcquisitionError:
            outcome = _handle_lock_conflict(tmux, config, logger)
            if outcome == "retry":
                continue
            return

    # We have the lock - this is the only dashboard instance
    pending_status: PendingStatus | None = None

    try:
        # Auto-create flow: Check if no sessions exist and auto_create is enabled
        if config.auto_create:
            try:
                sessions = tmux.list_sessions()
                if not sessions:
                    # No sessions exist - auto-create and attach using project name
                    session_name = tmux.generate_session_name(sessions)
                    logger.info("auto_create", f"auto-creating session: {session_name}")
                    try:
                        tmux.create_session_with_cd(session_name)
                        logger.info("auto_create", f"session created: {session_name}")
                        # Attach directly to the new session, bypassing dashboard
                        logger.info("auto_create", f"auto-attaching to session: {session_name}")
                        error = _attach_and_rename(
                            tmux,
                            session_name,
                            logger,
                            config.auto_rename_on_detach,
                            event="auto_create",
                        )
                        if error:
                            pending_status = PendingStatus(error, level="error")
                    except TmuxError as exc:
                        logger.error("auto_create", str(exc), session_name)
                        pending_status = PendingStatus(str(exc), level="error")
            except TmuxError as exc:
                logger.error("auto_create", f"failed to list sessions: {exc}")
                # Fall through to normal dashboard

        while True:
            action = run_dashboard(tmux, config, logger, headless_registry, pending_status)
            pending_status = None

            if action is None or action.kind == "refresh":
                continue
            if action.kind == "exit":
                logger.info("exit", "dashboard exit")
                break

            if action.kind in {"attach", "create"} and action.session_name:
                if action.kind == "create":
                    try:
                        tmux.create_session_with_cd(action.session_name)
                        logger.info("create", "session created", action.session_name)
                    except TmuxError as exc:
                        logger.error("create", str(exc), action.session_name)
                        pending_status = PendingStatus(str(exc), level="error")
                        continue

                logger.info("attach", "attaching session", action.session_name)
                error = _attach_and_rename(
                    tmux,
                    action.session_name,
                    logger,
                    config.auto_rename_on_detach,
                    event="attach",
                )
                if error:
                    pending_status = PendingStatus(error, level="error")
    finally:
        lock.release()

    return None


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="tmux-dashboard",
        description="A curses-based Tmux session manager with AI session detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tmux-dashboard              # Launch the dashboard
  tmux-dashboard --help        # Show this help message
  tmux-dashboard --version     # Show version

Environment Variables:
  TMUX_DASHBOARD_CONFIG       Path to config file (default: ~/.config/tmux-dashboard/config.json)
  TMUX_DASHBOARD_LOG          Path to log file (default: ~/.local/state/tmux-dashboard/log.jsonl)
  TMUX_DASHBOARD_COLOR        Color mode: auto/never/always (default: auto)
  TMUX_DASHBOARD_SORT_MODE    Sort mode: activity/name/ai_first/windows_count (default: ai_first)
  TMUX_DASHBOARD_DRY_RUN      Set to 1/true/yes to enable dry-run mode (blocks delete)
  TMUX_DASHBOARD_AUTO_RENAME_ON_DETACH  Set to 0/false to preserve manual session names (default: true)
  TMUX_DASHBOARD_CONFLICT_ACTION  attach|exit|prompt|takeover (default: attach)
  TMUX_DASHBOARD_LOCK_FILE    Override lock file path (default: ~/.local/state/tmux-dashboard/lock)
  TMUX_DASHBOARD_PID_FILE     Override PID file path (default: ~/.local/state/tmux-dashboard/pid)
  TMUX_DASHBOARD_HEADLESS_STATE_DIR     Headless metadata dir (default: ~/.local/state/tmux-dashboard/headless)
  TMUX_DASHBOARD_HEADLESS_OUTPUT_DIR    Headless output dir (default: ~/.local/state/tmux-dashboard/headless/output)
  TMUX_DASHBOARD_HEADLESS_REFRESH_SECONDS  Headless output refresh seconds (default: 5)
  TMUX_DASHBOARD_HEADLESS_MAX_EVENTS    Headless output events to display (default: 200)
  TMUX_DASHBOARD_HEADLESS_WAITING_SECONDS  Headless idle threshold seconds (default: 20)
  TMUX_DASHBOARD_HEADLESS_DEFAULT_AGENT Default headless agent (default: codex)
  TMUX_DASHBOARD_HEADLESS_CODEX_CMD     Override codex headless command template
  TMUX_DASHBOARD_HEADLESS_CODEX_STREAM_JSON  Force codex JSONL output (default: true)
  TMUX_DASHBOARD_HEADLESS_CLADCODE_CMD  Override cladcode headless command template
  TMUX_DASHBOARD_HEADLESS_MODELS        Comma-separated model list (applies to all agents)
  TMUX_DASHBOARD_HEADLESS_DEFAULT_MODEL Default model (applies to all agents)
  TMUX_DASHBOARD_HEADLESS_MODEL_LIST_COMMAND  CLI command to list models (applies to all agents)
  TMUX_DASHBOARD_HEADLESS_AUTO_CLEANUP  Auto-clean completed headless sessions (default: false)
  TMUX_DASHBOARD_HEADLESS_NOTIFY_ON_COMPLETE  Send t2me on completion (default: false)

Keybindings in Dashboard:
  Up/Down      Navigate sessions
  Enter        Attach/view session
  n            Create new session
  H            Create headless session
  d            Delete session
  R            Rename session
  r            Refresh list
  s            Cycle sort modes
  /            Search
  F1 or ?      Show help
  q or Ctrl+C  Exit
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0"
    )

    # Parse args - currently no runtime args, just help/version
    parser.parse_args()

    try:
        run()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
