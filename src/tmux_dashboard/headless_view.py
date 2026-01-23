"""Headless session view and log tailing."""

from __future__ import annotations

import curses
import json
import textwrap
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .headless import HeadlessRegistry, HeadlessSession
from .headless_state import summarize_expected_outcome, summarize_prompt, sync_headless_completion
from .logger import Logger
from .prompts import confirm_dialog, prompt_input_popup, safe_addstr, show_message
from .session_actions import do_attach
from .tmux_manager import TmuxError, TmuxManager


def run_headless_view(
    stdscr: curses._CursesWindow,
    session_name: str,
    tmux: TmuxManager,
    headless_registry: HeadlessRegistry,
    config: Config,
    logger: Logger,
) -> None:
    session = headless_registry.get(session_name)
    if session is None:
        show_message(stdscr, f"Headless metadata not found for {session_name}")
        return

    tailer = HeadlessLogTail(session.output_path, config.headless_max_events)
    output_lines: list[str] = []
    last_refresh = 0.0
    base_refresh = max(1, config.headless_refresh_seconds)
    refresh_interval = base_refresh
    max_refresh = max(base_refresh, base_refresh * 2)
    runtime_status = None
    waiting_input = False
    show_full_prompt = True
    show_raw_output = False
    last_event_seen_at: float | None = None
    idle_for: float = 0.0

    while True:
        now = time.monotonic()
        if (now - last_refresh) >= refresh_interval:
            output_lines = tailer.poll()
            runtime_status = tmux.get_session_runtime_status(session_name)
            waiting_input = is_waiting_input(
                runtime_status,
                tailer,
                config.headless_waiting_seconds,
                now,
            )
            if runtime_status and not getattr(runtime_status, "running", False):
                updated = sync_headless_completion(
                    headless_registry,
                    logger,
                    {session_name: session},
                    {session_name: runtime_status},
                    config.headless_notify_on_complete,
                )
                session = updated.get(session_name, session)

            if tailer.last_event_at and tailer.last_event_at != last_event_seen_at:
                last_event_seen_at = tailer.last_event_at
                refresh_interval = base_refresh
            else:
                idle_for = now - (tailer.last_event_at or tailer.started_at)
                if idle_for >= base_refresh * 2:
                    refresh_interval = min(max_refresh, refresh_interval + base_refresh)
            last_refresh = now

        idle_for = now - (tailer.last_event_at or tailer.started_at)
        elapsed_seconds = compute_elapsed_seconds(session, runtime_status)
        spinner = status_spinner_frame(now) if runtime_status and getattr(runtime_status, "running", False) else ""
        status_line = format_headless_status_line(
            session,
            runtime_status,
            waiting_input,
            refresh_interval,
            spinner=spinner,
            idle_for=idle_for,
            elapsed_seconds=elapsed_seconds,
        )
        display_lines = tailer.raw_lines() if show_raw_output else output_lines
        output_label = "raw JSON" if show_raw_output else "parsed"
        render_headless_view(
            stdscr,
            session,
            display_lines,
            status_line,
            show_full_prompt,
            output_label,
        )

        stdscr.timeout(200)
        key = stdscr.getch()
        if key in (ord("q"), 27):
            return
        if key == ord("r"):
            last_refresh = 0.0
            logger.info("headless_view", "manual refresh", session_name)
        if key == ord("p"):
            show_full_prompt = not show_full_prompt
        if key == ord("o"):
            show_raw_output = not show_raw_output
        if key == ord("a"):
            attach_from_headless_view(stdscr, tmux, session_name, logger, config)
            last_refresh = 0.0
        if key == ord("i"):
            send_headless_input(stdscr, tmux, session_name, logger)
            last_refresh = 0.0
        if key == ord("k"):
            confirm = confirm_dialog(
                stdscr,
                title="Kill headless session",
                lines=[
                    f"Session: {session_name}",
                    "This will terminate running processes.",
                    "Enter=confirm  Esc=cancel",
                ],
            )
            if confirm:
                try:
                    tmux.kill_session(session_name)
                    headless_registry.forget(session_name)
                    logger.info("headless_kill", "session killed", session_name)
                except TmuxError as exc:
                    logger.error("headless_kill", str(exc), session_name)
                return


def is_waiting_input(
    runtime_status: object,
    tailer: HeadlessLogTail,
    waiting_seconds: int,
    now: float,
) -> bool:
    if waiting_seconds <= 0:
        return False
    if not runtime_status or not getattr(runtime_status, "running", False):
        return False
    last_event_at = tailer.last_event_at or tailer.started_at
    return (now - last_event_at) >= waiting_seconds


def attach_from_headless_view(
    stdscr: curses._CursesWindow,
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
    config: Config,
) -> None:
    do_attach(
        stdscr,
        tmux,
        session_name,
        logger,
        auto_rename_on_detach=False,
    )
    if config.auto_rename_on_detach:
        logger.info("attach", "returned from headless session", session_name)


def send_headless_input(
    stdscr: curses._CursesWindow,
    tmux: TmuxManager,
    session_name: str,
    logger: Logger,
) -> None:
    value = prompt_input_popup(
        stdscr,
        "Send input",
        default="",
        prompt="Input to send:",
        max_len=200,
    )
    if value is None:
        return
    try:
        tmux.send_keys(session_name, [value], enter=True)
        logger.info("headless_input", "input sent", session_name)
    except TmuxError as exc:
        logger.error("headless_input", str(exc), session_name)
        show_message(stdscr, f"Send failed: {exc}")


def render_headless_view(
    stdscr: curses._CursesWindow,
    session: HeadlessSession,
    output_lines: list[str],
    status_line: str,
    show_full_prompt: bool,
    output_label: str,
) -> None:
    stdscr.erase()
    ensure_headless_colors()
    height, width = stdscr.getmaxyx()
    left = 2
    max_width = max(1, width - left - 1)

    row = 1
    model_suffix = f":{session.model}" if session.model else ""
    title = f"Headless Session: {session.session_name} [{session.agent}{model_suffix}]"
    safe_addstr(stdscr, row, left, title[:max_width])
    row += 2

    safe_addstr(stdscr, row, left, f"Path: {session.workdir}"[:max_width])
    row += 1

    model = session.model or "default"
    flow = session.flow or "-"
    safe_addstr(stdscr, row, left, f"Model: {model}  Flow: {flow}"[:max_width])
    row += 1

    safe_addstr(stdscr, row, left, "Prompt summary:"[:max_width])
    row += 1
    row = render_bullets(
        stdscr,
        row,
        left,
        max_width,
        summarize_prompt(session.instruction or ""),
        height - 4,
    )

    if row < height - 6:
        row += 1
        safe_addstr(stdscr, row, left, "Ожидаемый итог:"[:max_width])
        row += 1
        outcome = summarize_expected_outcome(session.instruction or "")
        for line in wrap_lines(outcome, max_width):
            if row >= height - 6:
                break
            safe_addstr(stdscr, row, left, line[:max_width])
            row += 1

    if session.last_raw_line and row < height - 6:
        row += 1
        safe_addstr(stdscr, row, left, "Last raw line:"[:max_width])
        row += 1
        for line in wrap_lines(session.last_raw_line, max_width):
            if row >= height - 6:
                break
            safe_addstr(stdscr, row, left, line[:max_width])
            row += 1

    if show_full_prompt and row < height - 6:
        row += 1
        safe_addstr(stdscr, row, left, "Full prompt:"[:max_width])
        row += 1
        full_prompt = session.instruction or "(empty)"
        for line in wrap_lines(full_prompt, max_width):
            if row >= height - 6:
                break
            safe_addstr(stdscr, row, left, line[:max_width])
            row += 1

    if row < height - 4:
        row += 1

    safe_addstr(stdscr, row, left, f"Output ({output_label}):"[:max_width])
    row += 1

    available = max(0, height - row - 2)
    wrapped_output: list[str] = []
    for line in output_lines:
        wrapped_output.extend(wrap_lines(line, max_width))
    if not wrapped_output:
        wrapped_output = ["(waiting for output)"]
    for line in wrapped_output[-available:]:
        attr = 0
        if output_label == "parsed":
            attr = headless_event_attr(line)
        safe_addstr(stdscr, row, left, line[:max_width], attr)
        row += 1

    footer = "q/Esc back  r refresh  p prompt  o output  a attach  i input  k kill"
    safe_addstr(stdscr, height - 2, left, footer[:max_width])
    safe_addstr(stdscr, height - 1, left, status_line[:max_width])
    stdscr.refresh()


def format_headless_status_line(
    session: HeadlessSession,
    runtime_status: object,
    waiting_input: bool,
    refresh_interval: int,
    spinner: str = "",
    idle_for: float | None = None,
    elapsed_seconds: float | None = None,
) -> str:
    output_name = Path(session.output_path).name
    status_text = "unknown"
    status_kind = "unknown"
    exit_code = None
    if runtime_status:
        exists = getattr(runtime_status, "exists", False)
        running = getattr(runtime_status, "running", False)
        exit_code = getattr(runtime_status, "exit_code", None)
        if not exists:
            status_text = "missing"
            status_kind = "missing"
        elif running:
            status_text = "waiting input" if waiting_input else "running"
            status_kind = "waiting_input" if waiting_input else "running"
        else:
            status_text = "completed"
            status_kind = "completed"

    if status_text == "completed" and exit_code is not None:
        status_text = f"completed (exit {exit_code})"

    icon = status_icon(status_kind)
    if spinner and status_kind in {"running", "waiting_input"}:
        status_text = f"{spinner} {status_text}"
    if icon:
        status_text = f"{icon} {status_text}"
    if idle_for is not None and status_kind in {"running", "waiting_input"}:
        status_text = f"{status_text}  idle {int(idle_for)}s"
    if elapsed_seconds is not None:
        status_text = f"{status_text}  elapsed {format_duration(elapsed_seconds)}"

    return f"Status: {status_text}  Output: {output_name}  Refresh: {refresh_interval}s"


def normalize_stream_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("event:"):
        return None
    if stripped.startswith("data:"):
        stripped = stripped[5:].strip()
        if not stripped:
            return None
    return stripped


def looks_like_json(line: str) -> bool:
    return line.lstrip().startswith(("{", "["))


class HeadlessLogTail:
    MAX_JSON_BUFFER = 20000

    def __init__(self, output_path: str, max_events: int) -> None:
        self.path = Path(output_path)
        self.max_events = max_events
        self.offset = 0
        self.buffer = ""
        self.json_buffer = ""
        self.decoder = json.JSONDecoder()
        self.events: deque[list[str]] = deque(maxlen=max_events)
        self.raw_events: deque[list[str]] = deque(maxlen=max_events)
        self.started_at = time.monotonic()
        self.last_event_at: float | None = None

    def poll(self) -> list[str]:
        if not self.path.exists():
            return ["(waiting for output)"]
        try:
            size = self.path.stat().st_size
        except OSError:
            return ["(failed to read output)"]

        if size < self.offset:
            self.offset = 0
            self.buffer = ""
            self.events.clear()
            self.raw_events.clear()
            self.started_at = time.monotonic()
            self.last_event_at = None

        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.offset)
                data = handle.read()
                if not data:
                    return self._flatten_events()
                self.offset = handle.tell()
        except OSError:
            return ["(failed to read output)"]

        self.buffer += data
        lines = self.buffer.split("\n")
        if self.buffer and not self.buffer.endswith("\n"):
            self.buffer = lines.pop()
        else:
            self.buffer = ""

        for line in lines:
            normalized = normalize_stream_line(line)
            if normalized is None:
                continue
            self._ingest_line(normalized)

        return self._flatten_events()

    def _flatten_events(self) -> list[str]:
        if not self.events:
            return ["(waiting for output)"]
        output_lines: list[str] = []
        for event_lines in self.events:
            if output_lines:
                output_lines.append("│")
            output_lines.extend(event_lines)
        return output_lines

    def _ingest_line(self, line: str) -> None:
        if line in {"[DONE]", "DONE"}:
            self._append_event({"type": "done", "message": "completed"}, raw_text=line)
            return

        if self.json_buffer:
            candidate = f"{self.json_buffer}\n{line}"
            remaining = self._drain_json_buffer(candidate)
            if remaining is None:
                self.json_buffer = candidate
                self._trim_json_buffer()
            else:
                self.json_buffer = remaining
            return

        if looks_like_json(line):
            remaining = self._drain_json_buffer(line)
            if remaining is None:
                self.json_buffer = line
                self._trim_json_buffer()
            else:
                self.json_buffer = remaining
            return

        self._append_raw(line)

    def raw_lines(self) -> list[str]:
        if not self.raw_events:
            return ["(waiting for output)"]
        output_lines: list[str] = []
        for event_lines in self.raw_events:
            output_lines.extend(event_lines)
        return output_lines

    def _append_event(self, payload: Any, raw_text: str | None = None) -> None:
        self.events.append(summarize_headless_event(payload))
        if raw_text is None:
            try:
                raw_text = json.dumps(payload, ensure_ascii=True)
            except (TypeError, ValueError):
                raw_text = str(payload)
        self.raw_events.append([raw_text])
        self.last_event_at = time.monotonic()

    def _append_raw(self, line: str) -> None:
        self.events.append([f"raw: {line}"])
        self.raw_events.append([line])
        self.last_event_at = time.monotonic()

    def _drain_json_buffer(self, buffer: str) -> str | None:
        data = buffer.lstrip()
        if not data:
            return ""
        parsed_any = False
        while data:
            try:
                payload, index = self.decoder.raw_decode(data)
            except json.JSONDecodeError:
                return None if not parsed_any else data
            parsed_any = True
            self._append_event(payload)
            data = data[index:].lstrip()
        return data

    def _trim_json_buffer(self) -> None:
        if len(self.json_buffer) > self.MAX_JSON_BUFFER:
            self._append_raw(self.json_buffer)
            self.json_buffer = ""


def summarize_headless_event(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        event_type = stringify_event_value(payload.get("type") or payload.get("event") or payload.get("kind"))
        codex_lines = summarize_codex_event(payload, event_type)
        if codex_lines is not None:
            return codex_lines

        message = extract_event_message(payload)
        if message:
            lines = message.splitlines() or [message]
        else:
            try:
                lines = [json.dumps(payload, ensure_ascii=True)]
            except (TypeError, ValueError):
                lines = [str(payload)]
        if event_type:
            lines[0] = format_event_line(event_type, lines[0])
        return lines
    return [str(payload)]


def summarize_codex_event(payload: dict[str, Any], event_type: str | None) -> list[str] | None:
    if not event_type:
        return None
    normalized = event_type.strip().lower()
    if normalized == "thread.started":
        return [format_event_line("thread.started")]
    if normalized == "turn.started":
        return [format_event_line("turn.started")]
    if normalized == "turn.completed":
        usage = payload.get("usage")
        summary = summarize_usage(usage)
        return [format_event_line("turn.completed", summary, separator="  ")] if summary else [
            format_event_line("turn.completed")
        ]
    if normalized != "item.completed":
        return None

    item = payload.get("item")
    if not isinstance(item, dict):
        return None
    item_type = stringify_event_value(item.get("type") or item.get("kind") or item.get("role"))
    message = stringify_event_value(item.get("text") or item.get("content") or item.get("message"))
    if not message:
        message = extract_event_message(item) or None

    label = (item_type or "item").strip().lower()
    if label in {"assistant", "assistant_message", "agent_message", "message", "output_text"}:
        label = "message"
    elif label in {"reasoning", "thought"}:
        label = "reasoning"
    elif label in {"tool", "tool_call", "tool_use"}:
        label = "tool"

    return [format_event_line(label, message)] if message else [format_event_line(label)]


def format_event_line(label: str, message: str | None = None, separator: str = ": ") -> str:
    emoji = event_emoji(label)
    title = f"{emoji} {label}" if emoji else label
    if not message:
        return title
    return f"{title}{separator}{message}"


def summarize_usage(usage: Any) -> str | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = _as_int(usage.get("input_tokens"))
    cached_tokens = _as_int(usage.get("cached_input_tokens") or usage.get("cache_input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    parts: list[str] = []
    if input_tokens is not None:
        parts.append(f"in {input_tokens}")
    if cached_tokens is not None:
        parts.append(f"cached {cached_tokens}")
    if output_tokens is not None:
        parts.append(f"out {output_tokens}")
    if not parts:
        return None
    return "📊 " + " / ".join(parts)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def extract_event_message(payload: dict[str, Any]) -> str | None:
    for key in ("message", "content", "text", "delta", "output", "data"):
        candidate = stringify_event_value(payload.get(key))
        if candidate:
            return candidate

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for path in (("delta", "content"), ("message", "content"), ("message",), ("delta",), ("text",)):
                candidate = stringify_event_path(choice, path)
                if candidate:
                    return candidate
    return None


def stringify_event_path(payload: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return stringify_event_value(current)


def stringify_event_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            rendered = stringify_event_value(item)
            if rendered:
                parts.append(rendered)
        return " ".join(parts) if parts else None
    if isinstance(value, dict):
        for key in ("text", "content", "message"):
            rendered = stringify_event_value(value.get(key))
            if rendered:
                return rendered
        try:
            return json.dumps(value, ensure_ascii=True)
        except (TypeError, ValueError):
            return str(value)
    try:
        return str(value)
    except Exception:
        return None


def wrap_lines(text: str, width: int) -> list[str]:
    if width <= 0:
        return [text]
    return textwrap.wrap(text, width=width) or [""]


_HEADLESS_COLORS_READY = False


def ensure_headless_colors() -> None:
    global _HEADLESS_COLORS_READY
    if _HEADLESS_COLORS_READY:
        return
    if not curses.has_colors():
        return
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(6, curses.COLOR_RED, -1)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(8, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(9, curses.COLOR_BLUE, -1)
        _HEADLESS_COLORS_READY = True
    except curses.error:
        return


def headless_event_attr(line: str) -> int:
    if not curses.has_colors():
        return 0
    label = extract_event_label(line)
    if not label:
        return 0
    if label in {"thinking", "thought", "reasoning"}:
        return curses.color_pair(1)
    if label in {"tool", "tool_use", "tool_call"}:
        return curses.color_pair(4)
    if label in {"command", "cmd", "input"}:
        return curses.color_pair(3)
    if label in {"output", "text", "message", "content"}:
        return curses.color_pair(8)
    if label in {"error", "warning"}:
        return curses.color_pair(6)
    if label in {"system"}:
        return curses.color_pair(9)
    return 0


def extract_event_label(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("raw:"):
        return "raw"
    head = stripped.split(":", 1)[0].strip()
    parts = head.split()
    label = parts[-1] if parts else head
    return label.lower() if label else None


def render_bullets(
    stdscr: curses._CursesWindow,
    row: int,
    left: int,
    width: int,
    bullets: list[str],
    max_row: int,
) -> int:
    for bullet in bullets:
        wrapped = wrap_lines(bullet, max(1, width - 2))
        for idx, line in enumerate(wrapped):
            if row >= max_row:
                return row
            prefix = "- " if idx == 0 else "  "
            safe_addstr(stdscr, row, left, f"{prefix}{line}"[:width])
            row += 1
    return row


def event_emoji(event_type: str) -> str:
    key = event_type.strip().lower()
    mapping = {
        "thread.started": "🧵",
        "turn.started": "▶️",
        "turn.completed": "✅",
        "thinking": "🧠",
        "thought": "🧠",
        "reasoning": "🧠",
        "tool": "🛠",
        "tool_use": "🛠",
        "tool_call": "🛠",
        "command": "⌨️",
        "cmd": "⌨️",
        "input": "⌨️",
        "output": "💬",
        "text": "💬",
        "message": "💬",
        "agent_message": "💬",
        "content": "💬",
        "error": "⚠️",
        "warning": "⚠️",
        "system": "📌",
    }
    return mapping.get(key, "")


def status_icon(status_kind: str) -> str:
    return {
        "running": "⏳",
        "waiting_input": "⌛",
        "completed": "✅",
        "missing": "⚠️",
    }.get(status_kind, "")


def status_spinner_frame(now: float) -> str:
    frames = "|/-\\"
    return frames[int(now * 6) % len(frames)]


def compute_elapsed_seconds(session: HeadlessSession, runtime_status: object) -> float | None:
    start_dt = parse_iso8601(session.created_at)
    if not start_dt:
        return None
    running = runtime_status and getattr(runtime_status, "running", False)
    if not running and session.completed_at:
        end_dt = parse_iso8601(session.completed_at) or datetime.now(timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)
    elapsed = (end_dt - start_dt).total_seconds()
    return max(0.0, elapsed)


def parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def format_duration(seconds: float) -> str:
    total = int(max(0, seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{sec:02d}s"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"
