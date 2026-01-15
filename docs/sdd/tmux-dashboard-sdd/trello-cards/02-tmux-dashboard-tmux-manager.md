# Card 02: Tmux Dashboard - Tmux manager core

| Field | Value |
|-------|-------|
| **ID** | TMUXD-02 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 1 |

## User Story

> As a user, I want reliable tmux session operations so that the dashboard can list, create, attach, preview, and delete sessions.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Sections 2, 3.3
- [ui-flow.md](../ui-flow.md) - Main dashboard and preview

## Instructions

### Step 1: Implement tmux manager module

Create `src/tmux_dashboard/tmux_manager.py` with:
- `list_sessions()` → list of sessions (name, attached flag, window count)
- `create_session(name)` → creates detached session
- `attach_command(name)` → returns `['tmux', 'attach-session', '-t', name]`
- `kill_session(name)` → kills session
- `get_session_details(name)` → windows/panes + `pane_current_command`

Use `libtmux` when available for metadata. Use tmux CLI fallback for `list-sessions` if needed.

### Step 2: Handle empty/no server

- If no tmux server exists, return empty list (no crash).
- Provide clear error messages for UI (exception type or error string).

### Step 3: Wire models

Add lightweight data models in `src/tmux_dashboard/models.py` (if not present):
- `SessionInfo`
- `WindowInfo`
- `PaneInfo`

### Step 4: Verification

```bash
python - << 'PY'
from tmux_dashboard.tmux_manager import TmuxManager
m = TmuxManager()
print(m.list_sessions())
PY
```

## Acceptance Criteria

- [ ] `list_sessions()` returns structured session data
- [ ] No tmux server → empty list + no crash
- [ ] `create_session`, `kill_session`, `get_session_details` behave as expected
- [ ] `attach_command()` returns correct tmux CLI args
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 02 to "completed"
2. Read next card: [03-tmux-dashboard-ui-layout.md](./03-tmux-dashboard-ui-layout.md)
3. Continue execution
