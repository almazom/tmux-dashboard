"""Headless session state helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone

from .headless import HeadlessRegistry, HeadlessSession
from .logger import Logger
from .models import SessionInfo
from .tmux_manager import TmuxError, TmuxManager


def apply_headless_metadata(
    sessions: list[SessionInfo],
    headless_map: dict[str, HeadlessSession],
    status_map: dict[str, object],
) -> list[SessionInfo]:
    if not headless_map:
        return sessions
    enriched: list[SessionInfo] = []
    known_names = {session.name for session in sessions}
    for session in sessions:
        headless = headless_map.get(session.name)
        if headless:
            status = status_map.get(session.name)
            status_text = status_to_label(status)
            exit_code = getattr(status, "exit_code", None) if status else None
            enriched.append(
                SessionInfo(
                    name=session.name,
                    attached=session.attached,
                    windows=session.windows,
                    is_ai_session=True,
                    ai_agent=headless.agent,
                    is_headless=True,
                    headless_agent=headless.agent,
                    headless_model=headless.model,
                    headless_status=status_text,
                    headless_exit_code=exit_code,
                )
            )
        else:
            enriched.append(session)
    missing = [name for name in headless_map.keys() if name not in known_names]
    for name in sorted(missing):
        headless = headless_map[name]
        status = status_map.get(name)
        status_text = status_to_label(status)
        exit_code = getattr(status, "exit_code", None) if status else None
        enriched.append(
            SessionInfo(
                name=headless.session_name,
                attached=False,
                windows=0,
                is_ai_session=True,
                ai_agent=headless.agent,
                is_headless=True,
                headless_agent=headless.agent,
                headless_model=headless.model,
                headless_status=status_text,
                headless_exit_code=exit_code,
            )
        )
    return enriched


def auto_cleanup_headless(
    tmux: TmuxManager,
    headless_registry: HeadlessRegistry,
    logger: Logger,
    headless_map: dict[str, HeadlessSession],
    status_map: dict[str, object],
) -> dict[str, HeadlessSession]:
    cleaned = dict(headless_map)
    for name, _meta in list(headless_map.items()):
        status = status_map.get(name) or tmux.get_session_runtime_status(name)
        if status.exists and status.running:
            continue
        if status.exists:
            try:
                tmux.kill_session(name)
            except TmuxError as exc:
                logger.error("headless_cleanup", str(exc), name)
                continue
        headless_registry.forget(name)
        cleaned.pop(name, None)
        logger.info("headless_cleanup", "headless session cleaned", name)
    return cleaned


def collect_headless_status(
    tmux: TmuxManager,
    headless_map: dict[str, HeadlessSession],
) -> dict[str, object]:
    status_map: dict[str, object] = {}
    for name in headless_map.keys():
        status_map[name] = tmux.get_session_runtime_status(name)
    return status_map


def status_to_label(status: object) -> str:
    if not status:
        return "unknown"
    exists = getattr(status, "exists", False)
    running = getattr(status, "running", False)
    if not exists:
        return "missing"
    if running:
        return "running"
    return "completed"


def sync_headless_completion(
    headless_registry: HeadlessRegistry,
    logger: Logger,
    headless_map: dict[str, HeadlessSession],
    status_map: dict[str, object],
    notify_on_complete: bool,
) -> dict[str, HeadlessSession]:
    updated = dict(headless_map)
    for name, meta in headless_map.items():
        status = status_map.get(name)
        if not status or getattr(status, "running", False):
            continue
        if meta.completed_at:
            continue

        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        exit_code = getattr(status, "exit_code", None)
        last_raw = read_last_raw_line(meta.output_path)
        updated_ok = headless_registry.update(
            name,
            {
                "completed_at": completed_at,
                "exit_code": exit_code,
                "last_raw_line": last_raw,
            },
            base=meta,
        )
        if not updated_ok:
            logger.warn("headless_update", "failed to update metadata", name)
            continue
        updated[name] = HeadlessSession(
            session_name=meta.session_name,
            agent=meta.agent,
            model=meta.model,
            flow=meta.flow,
            instruction=meta.instruction,
            workdir=meta.workdir,
            output_path=meta.output_path,
            created_at=meta.created_at,
            completed_at=completed_at,
            exit_code=exit_code,
            last_raw_line=last_raw,
            command=meta.command,
        )
        if notify_on_complete:
            notify_headless_complete(logger, updated[name])

    return updated


def read_last_raw_line(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size == 0:
                return None
            offset = min(size, 4096)
            handle.seek(-offset, 2)
            chunk = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    lines = [line for line in chunk.splitlines() if line.strip()]
    return lines[-1].strip() if lines else None


def notify_headless_complete(logger: Logger, session: HeadlessSession) -> None:
    if not shutil.which("t2me"):
        logger.warn("headless_notify", "t2me not found", session.session_name)
        return
    summary = summarize_prompt(session.instruction or "")
    summary_text = "\n".join(f"- {line}" for line in summary)
    raw_line = session.last_raw_line or "(no output)"
    message = (
        f"✅ Headless done: {session.session_name}\n"
        f"Agent: {session.agent}\n"
        f"Model: {session.model or 'default'}\n"
        f"Flow: {session.flow or '-'}\n"
        f"Path: {session.workdir}\n"
        f"Exit: {session.exit_code}\n"
        f"Output: {session.output_path}\n"
        f"Prompt:\n{summary_text}\n"
        f"Last raw:\n{raw_line}"
    )
    try:
        subprocess.run(["t2me", message], check=False)
    except OSError as exc:
        logger.error("headless_notify", str(exc), session.session_name)


def summarize_prompt(text: str, bullets: int = 3) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return [
            "🧭Суть: пустой запрос",
            "🧪Проверить: нет данных",
            "🎯Итог: нет ожиданий",
        ]

    keywords = _extract_keywords(normalized)
    if not _contains_cyrillic(normalized):
        keywords = []
    fallback = [
        "задача", "сессия", "тест",
        "лог", "модель", "вывод",
        "ошибка", "стабильность", "результат",
    ]
    merged = keywords + [word for word in fallback if word not in keywords]
    while len(merged) < 9:
        merged.append("деталь")

    parts = merged[:9]
    return [
        f"🧭Суть: {parts[0]} {parts[1]} {parts[2]}",
        f"🧪Проверить: {parts[3]} {parts[4]} {parts[5]}",
        f"🎯Итог: {parts[6]} {parts[7]} {parts[8]}",
    ]


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zА-Яа-я0-9_]+", text)
    stopwords = {
        "and", "the", "this", "that", "with", "from", "into", "only", "without",
        "для", "что", "это", "как", "без", "или", "его", "ее", "ещё", "еще",
        "так", "там", "тут", "чтобы", "если", "при", "над", "под",
        "про", "все", "всё", "можно", "нужно",
    }
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        lower = word.lower()
        if lower in stopwords:
            continue
        if len(lower) < 3:
            continue
        if lower in seen:
            continue
        seen.add(lower)
        result.append(lower)
        if len(result) >= 9:
            break
    return result


def _contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-я]", text))


def summarize_expected_outcome(text: str, max_words: int = 12) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "(не задано)"

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\\s+", normalized) if s.strip()]
    candidate = sentences[0] if sentences else normalized
    words = candidate.split()
    if len(words) > max_words:
        candidate = " ".join(words[:max_words]) + "…"
    return candidate
