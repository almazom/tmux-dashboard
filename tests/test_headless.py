import json

from tmux_dashboard.config import load_config
from tmux_dashboard.headless import HeadlessRegistry, build_headless_session
from tmux_dashboard.input_handler import (
    HeadlessLogTail,
    _auto_cleanup_headless,
    _is_waiting_input,
    _read_last_raw_line,
    _sync_headless_completion,
)
from tmux_dashboard.tmux_manager import SessionRuntimeStatus, TmuxManager


def test_load_config_headless_models(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "headless_models": {
                    "codex": ["gpt-4.1", "gpt-4.1-mini"],
                    "cladcode": "claude-3-5-sonnet",
                },
                "headless_default_model": {
                    "codex": "gpt-4.1",
                },
                "headless_model_list_commands": {
                    "codex": "codex --list-models",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("TMUX_DASHBOARD_HEADLESS_MODELS", raising=False)
    monkeypatch.delenv("TMUX_DASHBOARD_HEADLESS_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("TMUX_DASHBOARD_HEADLESS_MODEL_LIST_COMMAND", raising=False)

    config = load_config(path=str(config_path))

    assert config.headless_models["codex"] == ["gpt-4.1", "gpt-4.1-mini"]
    assert config.headless_models["cladcode"] == ["claude-3-5-sonnet"]
    assert config.headless_default_models["codex"] == "gpt-4.1"
    assert config.headless_model_list_commands["codex"] == "codex --list-models"


def test_load_config_headless_models_env_override(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"headless_models": {"codex": ["gpt-4.1"]}}), encoding="utf-8")

    monkeypatch.setenv("TMUX_DASHBOARD_HEADLESS_MODELS", "m1,m2")
    monkeypatch.setenv("TMUX_DASHBOARD_HEADLESS_DEFAULT_MODEL", "m2")

    config = load_config(path=str(config_path))

    assert config.headless_models["*"] == ["m1", "m2"]
    assert config.headless_default_models["*"] == "m2"


def test_headless_log_tail_handles_partial_lines(tmp_path):
    output_path = tmp_path / "output.jsonl"
    tailer = HeadlessLogTail(str(output_path), max_events=5)

    assert tailer.poll() == ["(waiting for output)"]

    line_one = json.dumps({"type": "output", "content": "hello"})
    line_two = json.dumps({"type": "output", "content": "world"})
    output_path.write_text(f"{line_one}\n{line_two[:8]}", encoding="utf-8")

    output_lines = tailer.poll()
    assert any("output: hello" in line for line in output_lines)
    assert not any("world" in line for line in output_lines)

    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line_two[8:]}\n")

    output_lines = tailer.poll()
    assert any("output: world" in line for line in output_lines)


def test_headless_log_tail_resets_on_truncate(tmp_path):
    output_path = tmp_path / "output.jsonl"
    tailer = HeadlessLogTail(str(output_path), max_events=5)

    line_one = json.dumps({"type": "output", "content": "first-longer"})
    output_path.write_text(f"{line_one}\n", encoding="utf-8")
    output_lines = tailer.poll()
    assert any("output: first" in line for line in output_lines)

    line_two = json.dumps({"type": "output", "content": "x"})
    output_path.write_text(f"{line_two}\n", encoding="utf-8")
    output_lines = tailer.poll()
    assert any("output: x" in line for line in output_lines)


def test_waiting_input_detection(tmp_path):
    output_path = tmp_path / "output.jsonl"
    tailer = HeadlessLogTail(str(output_path), max_events=5)

    status = SessionRuntimeStatus(exists=True, running=True, exit_code=None)
    now = tailer.started_at + 25
    assert _is_waiting_input(status, tailer, waiting_seconds=20, now=now)

    tailer.last_event_at = now
    assert not _is_waiting_input(status, tailer, waiting_seconds=20, now=now + 5)


def test_auto_cleanup_headless(tmp_path, monkeypatch):
    registry = HeadlessRegistry(tmp_path / "meta", tmp_path / "out")
    session = build_headless_session(
        session_name="headless-test",
        agent="codex",
        model="gpt-5.2-codex medium",
        instruction="test",
        workdir=str(tmp_path),
        output_path=str(tmp_path / "out" / "headless-test.jsonl"),
    )
    registry.record(session)
    headless_map = registry.load_all()

    manager = TmuxManager()

    def fake_status(_name):
        return SessionRuntimeStatus(exists=True, running=False, exit_code=0)

    def fake_kill(_name):
        return None

    monkeypatch.setattr(manager, "get_session_runtime_status", fake_status)
    monkeypatch.setattr(manager, "kill_session", fake_kill)

    cleaned = _auto_cleanup_headless(
        manager,
        registry,
        logger=_NullLogger(),
        headless_map=headless_map,
        status_map={"headless-test": SessionRuntimeStatus(exists=True, running=False, exit_code=0)},
    )
    assert "headless-test" not in cleaned


def test_read_last_raw_line(tmp_path):
    path = tmp_path / "output.jsonl"
    path.write_text("one\n\ntwo\n", encoding="utf-8")
    assert _read_last_raw_line(str(path)) == "two"


def test_sync_headless_completion_updates(tmp_path, monkeypatch):
    registry = HeadlessRegistry(tmp_path / "meta", tmp_path / "out")
    output_path = tmp_path / "out" / "headless-test.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("last line\n", encoding="utf-8")
    session = build_headless_session(
        session_name="headless-test",
        agent="codex",
        model="gpt-5.2-codex medium",
        instruction="test",
        workdir=str(tmp_path),
        output_path=str(output_path),
    )
    registry.record(session)
    headless_map = registry.load_all()
    status_map = {"headless-test": SessionRuntimeStatus(exists=True, running=False, exit_code=3)}

    updated = _sync_headless_completion(
        registry,
        logger=_NullLogger(),
        headless_map=headless_map,
        status_map=status_map,
        notify_on_complete=False,
    )
    completed = updated["headless-test"]
    assert completed.completed_at is not None
    assert completed.exit_code == 3
    assert completed.last_raw_line == "last line"


class _NullLogger:
    def info(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def warn(self, *_args, **_kwargs):
        return None
