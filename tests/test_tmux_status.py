from tmux_dashboard.tmux_manager import SessionRuntimeStatus, TmuxManager


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_runtime_status_running(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return _Result(stdout="0::0\n1::0\n")

    monkeypatch.setattr("tmux_dashboard.tmux_manager.subprocess.run", fake_run)
    status = TmuxManager().get_session_runtime_status("sess")
    assert status == SessionRuntimeStatus(exists=True, running=True, exit_code=0)


def test_runtime_status_completed(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return _Result(stdout="1::2\n1::0\n")

    monkeypatch.setattr("tmux_dashboard.tmux_manager.subprocess.run", fake_run)
    status = TmuxManager().get_session_runtime_status("sess")
    assert status == SessionRuntimeStatus(exists=True, running=False, exit_code=2)


def test_runtime_status_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return _Result(returncode=1, stderr="can't find session: sess")

    monkeypatch.setattr("tmux_dashboard.tmux_manager.subprocess.run", fake_run)
    status = TmuxManager().get_session_runtime_status("sess")
    assert status == SessionRuntimeStatus(exists=False, running=False, exit_code=None)
