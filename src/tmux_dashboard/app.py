"""Application entrypoint and main loop."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional

from .config import load_config
from .input_handler import run_dashboard
from .logger import Logger
from .tmux_manager import TmuxError, TmuxManager


@dataclass
class PendingStatus:
    message: str
    level: str = "info"


def run() -> None:
    config = load_config()
    logger = Logger(config.log_path)
    tmux = TmuxManager()

    pending_status: Optional[PendingStatus] = None

    while True:
        action = run_dashboard(tmux, config, logger, pending_status)
        pending_status = None

        if action is None or action.kind == "refresh":
            continue
        if action.kind == "exit":
            logger.info("exit", "dashboard exit")
            break

        if action.kind in {"attach", "create"} and action.session_name:
            if action.kind == "create":
                try:
                    tmux.create_session(action.session_name)
                    logger.info("create", "session created", action.session_name)
                except TmuxError as exc:
                    logger.error("create", str(exc), action.session_name)
                    pending_status = PendingStatus(str(exc), level="error")
                    continue

            try:
                logger.info("attach", "attaching session", action.session_name)
                subprocess.run(tmux.attach_command(action.session_name))
            except OSError as exc:
                pending_status = PendingStatus(str(exc), level="error")
                logger.error("attach", str(exc), action.session_name)

    return None
