"""Application entrypoint and main loop."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

from .config import load_config
from .headless import HeadlessRegistry
from .input_handler import run_dashboard
from .instance_lock import LockAcquisitionError, ensure_single_instance
from .logger import Logger
from .tmux_manager import TmuxError, TmuxManager


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


def run() -> None:
    # Load config first to get settings
    config = load_config()
    logger = Logger(config.log_path)
    tmux = TmuxManager()
    headless_registry = HeadlessRegistry(config.headless_state_dir, config.headless_output_dir)

    try:
        lock = ensure_single_instance(exit_on_conflict=False, verbose=False)
    except LockAcquisitionError:
        # Another dashboard instance is running
        # Check if tmux has sessions - if so, attach to the most recent one
        # This allows SSH sessions to work normally
        try:
            target_session = tmux.most_recent_session()
            if target_session:
                # Tmux has sessions - attach to the most recent one
                logger.info("auto_attach", "another dashboard running, attaching to session")
                if _attach_and_rename(
                    tmux,
                    target_session.name,
                    logger,
                    config.auto_rename_on_detach,
                    event="auto_attach",
                ):
                    return
                return  # Exit after attaching
            else:
                # No tmux sessions exist - just exit
                logger.info("exit", "another dashboard running, no sessions to attach")
                return  # Nothing to do, exit cleanly
        except TmuxError as exc:
            logger.error("attach", f"failed to attach: {exc}")
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
  TMUX_DASHBOARD_LOCK_FILE    Override lock file path (default: ~/.local/state/tmux-dashboard/lock)
  TMUX_DASHBOARD_PID_FILE     Override PID file path (default: ~/.local/state/tmux-dashboard/pid)
  TMUX_DASHBOARD_HEADLESS_STATE_DIR     Headless metadata dir (default: ~/.local/state/tmux-dashboard/headless)
  TMUX_DASHBOARD_HEADLESS_OUTPUT_DIR    Headless output dir (default: ~/.local/state/tmux-dashboard/headless/output)
  TMUX_DASHBOARD_HEADLESS_REFRESH_SECONDS  Headless output refresh seconds (default: 5)
  TMUX_DASHBOARD_HEADLESS_MAX_EVENTS    Headless output events to display (default: 200)
  TMUX_DASHBOARD_HEADLESS_WAITING_SECONDS  Headless idle threshold seconds (default: 20)
  TMUX_DASHBOARD_HEADLESS_DEFAULT_AGENT Default headless agent (default: codex)
  TMUX_DASHBOARD_HEADLESS_CODEX_CMD     Override codex headless command template
  TMUX_DASHBOARD_HEADLESS_CODEX_STREAM_JSON  Force codex stream-json output (default: true)
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
