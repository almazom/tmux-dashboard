import json

from tmux_dashboard.config import load_config
from tmux_dashboard.headless import HeadlessRegistry, build_headless_session
from tmux_dashboard.headless_state import (
    apply_headless_metadata,
    auto_cleanup_headless,
    read_last_raw_line,
    sync_headless_completion,
)
from tmux_dashboard.headless_view import HeadlessLogTail, is_waiting_input
from tmux_dashboard.input_handler import _delete_session
from tmux_dashboard.models import SessionInfo
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


def test_load_config_headless_codex_stream_toggle(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"headless_codex_stream_json": False}), encoding="utf-8")

    monkeypatch.delenv("TMUX_DASHBOARD_HEADLESS_CODEX_CMD", raising=False)
    monkeypatch.delenv("TMUX_DASHBOARD_HEADLESS_CODEX_STREAM_JSON", raising=False)

    config = load_config(path=str(config_path))
    assert "codex_wrapper" in config.headless_agents["codex"]

    monkeypatch.setenv("TMUX_DASHBOARD_HEADLESS_CODEX_STREAM_JSON", "1")
    config = load_config(path=str(config_path))
    assert "stream-json" in config.headless_agents["codex"]


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


def test_headless_log_tail_parses_sse_lines(tmp_path):
    output_path = tmp_path / "output.jsonl"
    tailer = HeadlessLogTail(str(output_path), max_events=5)

    line = json.dumps({"type": "output", "content": "hello"})
    output_path.write_text(f"data: {line}\n", encoding="utf-8")

    output_lines = tailer.poll()
    assert any("output: hello" in line for line in output_lines)


def test_headless_log_tail_parses_multiline_json(tmp_path):
    output_path = tmp_path / "output.jsonl"
    tailer = HeadlessLogTail(str(output_path), max_events=5)

    payload = json.dumps({"type": "output", "content": "hello"})
    split_at = payload.find(",") + 1
    first, second = payload[:split_at], payload[split_at:]
    output_path.write_text(f"{first}\n{second}\n", encoding="utf-8")

    output_lines = tailer.poll()
    assert any("output: hello" in line for line in output_lines)


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
    assert is_waiting_input(status, tailer, waiting_seconds=20, now=now)

    tailer.last_event_at = now
    assert not is_waiting_input(status, tailer, waiting_seconds=20, now=now + 5)


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

    cleaned = auto_cleanup_headless(
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
    assert read_last_raw_line(str(path)) == "two"


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

    updated = sync_headless_completion(
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


def test_apply_headless_metadata_includes_metadata_only(tmp_path):
    session = build_headless_session(
        session_name="headless-missing",
        agent="codex",
        model="gpt-5.2-codex medium",
        instruction="test",
        workdir=str(tmp_path),
        output_path=str(tmp_path / "out" / "headless-missing.jsonl"),
    )
    headless_map = {session.session_name: session}
    status_map = {
        session.session_name: SessionRuntimeStatus(exists=False, running=False, exit_code=None)
    }

    result = apply_headless_metadata([], headless_map, status_map)

    assert len(result) == 1
    entry = result[0]
    assert entry.name == session.session_name
    assert entry.is_headless
    assert entry.headless_status == "missing"
    assert entry.attached is False
    assert entry.windows == 0


def test_apply_headless_metadata_does_not_duplicate_sessions(tmp_path):
    headless_session = build_headless_session(
        session_name="headless-running",
        agent="codex",
        model="gpt-5.2-codex medium",
        instruction="test",
        workdir=str(tmp_path),
        output_path=str(tmp_path / "out" / "headless-running.jsonl"),
    )
    sessions = [SessionInfo(name=headless_session.session_name, attached=False, windows=1)]
    headless_map = {headless_session.session_name: headless_session}
    status_map = {
        headless_session.session_name: SessionRuntimeStatus(exists=True, running=True, exit_code=None)
    }

    result = apply_headless_metadata(sessions, headless_map, status_map)

    assert len(result) == 1
    assert result[0].is_headless
    assert result[0].headless_status == "running"


def test_delete_session_skips_tmux_for_missing_headless(tmp_path):
    deleted = []
    killed = []

    class _Tmux:
        def kill_session(self, name):
            killed.append(name)

    class _Registry:
        def forget(self, name):
            deleted.append(name)

    session = SessionInfo(
        name="headless-missing",
        attached=False,
        windows=0,
        is_headless=True,
        headless_status="missing",
    )

    _delete_session(_Tmux(), _Registry(), session)

    assert deleted == ["headless-missing"]
    assert killed == []


def test_delete_session_kills_tmux_for_headless_running(tmp_path):
    deleted = []
    killed = []

    class _Tmux:
        def kill_session(self, name):
            killed.append(name)

    class _Registry:
        def forget(self, name):
            deleted.append(name)

    session = SessionInfo(
        name="headless-running",
        attached=False,
        windows=1,
        is_headless=True,
        headless_status="running",
    )

    _delete_session(_Tmux(), _Registry(), session)

    assert deleted == ["headless-running"]
    assert killed == ["headless-running"]


def test_headless_registry_update_refuses_corrupt_without_base(tmp_path):
    registry = HeadlessRegistry(tmp_path / "meta", tmp_path / "out")
    path = registry.metadata_path("bad-session")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    ok = registry.update("bad-session", {"exit_code": 2})

    assert ok is False
    assert path.read_text(encoding="utf-8") == "{not json"


def test_headless_registry_update_uses_base_on_corrupt(tmp_path):
    registry = HeadlessRegistry(tmp_path / "meta", tmp_path / "out")
    session = build_headless_session(
        session_name="headless-recover",
        agent="codex",
        model="gpt-5.2-codex medium",
        instruction="test",
        workdir=str(tmp_path),
        output_path=str(tmp_path / "out" / "headless-recover.jsonl"),
    )
    path = registry.metadata_path(session.session_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    ok = registry.update(session.session_name, {"exit_code": 7}, base=session)

    assert ok is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["session_name"] == session.session_name
    assert data["agent"] == session.agent
    assert data["workdir"] == session.workdir
    assert data["output_path"] == session.output_path
    assert data["exit_code"] == 7


class _NullLogger:
    def info(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def warn(self, *_args, **_kwargs):
        return None
