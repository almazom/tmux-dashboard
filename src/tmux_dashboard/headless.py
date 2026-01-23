"""Headless session metadata and command helpers."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class HeadlessSession:
    session_name: str
    agent: str
    model: str | None
    flow: str | None
    instruction: str
    workdir: str
    output_path: str
    created_at: str
    completed_at: str | None = None
    exit_code: int | None = None
    last_raw_line: str | None = None
    command: str | None = None


class HeadlessRegistry:
    def __init__(self, state_dir: Path, output_dir: Path) -> None:
        self.state_dir = state_dir
        self.output_dir = output_dir

    def metadata_path(self, session_name: str) -> Path:
        safe_name = _safe_filename(session_name)
        return self.state_dir / f"{safe_name}.json"

    def output_path(self, session_name: str) -> Path:
        safe_name = _safe_filename(session_name)
        return self.output_dir / f"{safe_name}.jsonl"

    def record(self, session: HeadlessSession) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_name": session.session_name,
            "agent": session.agent,
            "model": session.model,
            "flow": session.flow,
            "instruction": session.instruction,
            "workdir": session.workdir,
            "output_path": session.output_path,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
            "exit_code": session.exit_code,
            "last_raw_line": session.last_raw_line,
            "command": session.command,
        }
        path = self.metadata_path(session.session_name)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        Path(session.output_path).touch(exist_ok=True)

    def update(self, session_name: str, updates: dict[str, Any]) -> None:
        path = self.metadata_path(session_name)
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        data.update(updates)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")

    def load_all(self) -> dict[str, HeadlessSession]:
        sessions: dict[str, HeadlessSession] = {}
        if not self.state_dir.exists():
            return sessions
        for path in self.state_dir.glob("*.json"):
            session = self._read_session(path)
            if session:
                sessions[session.session_name] = session
        return sessions

    def get(self, session_name: str) -> HeadlessSession | None:
        path = self.metadata_path(session_name)
        return self._read_session(path)

    def forget(self, session_name: str) -> None:
        path = self.metadata_path(session_name)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _read_session(self, path: Path) -> HeadlessSession | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return _parse_session_payload(data)


def build_headless_session(
    session_name: str,
    agent: str,
    model: str | None,
    instruction: str,
    workdir: str,
    output_path: str,
    flow: str | None = None,
    command: str | None = None,
) -> HeadlessSession:
    return HeadlessSession(
        session_name=session_name,
        agent=agent,
        model=model,
        flow=flow,
        instruction=instruction,
        workdir=workdir,
        output_path=output_path,
        created_at=_utc_now_iso(),
        command=command,
    )


def build_headless_shell_command(
    template: str,
    instruction: str,
    output_path: str,
    workdir: str,
    agent: str,
    model: str | None,
) -> list[str]:
    safe_instruction = shlex.quote(instruction)
    safe_output = shlex.quote(output_path)
    safe_workdir = shlex.quote(workdir)
    safe_agent = shlex.quote(agent)
    safe_model = shlex.quote(model) if model else ""
    rendered = template.format(
        instruction=safe_instruction,
        output=safe_output,
        cwd=safe_workdir,
        agent=safe_agent,
        model=safe_model,
    )
    env_vars = {
        "TMUX_DASHBOARD_HEADLESS_INSTRUCTION": instruction,
        "TMUX_DASHBOARD_HEADLESS_OUTPUT": output_path,
        "TMUX_DASHBOARD_HEADLESS_CWD": workdir,
        "TMUX_DASHBOARD_HEADLESS_AGENT": agent,
        "TMUX_DASHBOARD_HEADLESS_MODEL": model or "",
    }
    env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env_vars.items())
    command = f"{env_prefix} {rendered}".strip()
    return ["/bin/sh", "-lc", command]


def _parse_session_payload(payload: Any) -> HeadlessSession | None:
    if not isinstance(payload, dict):
        return None
    session_name = _as_str(payload.get("session_name"))
    agent = _as_str(payload.get("agent"))
    model = _as_str(payload.get("model"))
    flow = _as_str(payload.get("flow"))
    instruction = _as_str(payload.get("instruction")) or ""
    workdir = _as_str(payload.get("workdir"))
    output_path = _as_str(payload.get("output_path"))
    created_at = _as_str(payload.get("created_at")) or _utc_now_iso()
    completed_at = _as_str(payload.get("completed_at"))
    exit_code = _as_int(payload.get("exit_code"))
    last_raw_line = _as_str(payload.get("last_raw_line"))
    command = _as_str(payload.get("command"))
    if not session_name or not agent or not workdir or not output_path:
        return None
    return HeadlessSession(
        session_name=session_name,
        agent=agent,
        model=model,
        flow=flow,
        instruction=instruction,
        workdir=workdir,
        output_path=output_path,
        created_at=created_at,
        completed_at=completed_at,
        exit_code=exit_code,
        last_raw_line=last_raw_line,
        command=command,
    )


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None
