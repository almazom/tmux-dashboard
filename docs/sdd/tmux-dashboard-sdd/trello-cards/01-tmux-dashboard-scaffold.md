# Card 01: Tmux Dashboard - Scaffold app + config/logging

| Field | Value |
|-------|-------|
| **ID** | TMUXD-01 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 1 |

## User Story

> As a single user, I want a clean app skeleton with config and logging so that future features are maintainable.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Sections 4, 6, 7
- [ui-flow.md](../ui-flow.md) - Screen templates for naming
- No existing patterns (greenfield repo)

## Instructions

### Step 1: Create project skeleton

```bash
mkdir -p src/tmux_dashboard
```

### Step 2: Add base modules

Create files:
- `src/tmux_dashboard/__init__.py`
- `src/tmux_dashboard/__main__.py` (entrypoint)
- `src/tmux_dashboard/config.py`
- `src/tmux_dashboard/logger.py`

Notes:
- `config.py` loads JSON config and env overrides (`TMUX_DASHBOARD_*`).
- `logger.py` writes JSONL with fields `ts/level/event/session_name/message`.
- `__main__.py` should call `app.run()` (to be implemented in later cards).

### Step 3: Add minimal README or usage note

Add usage note in `src/tmux_dashboard/__main__.py` docstring or module comment:
- How to run: `python -m tmux_dashboard`
- Where config lives: `~/.config/tmux-dashboard/config.json`

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] Project skeleton exists under `src/tmux_dashboard/`
- [ ] Config loader reads JSON file and env overrides (no crashes on missing file)
- [ ] Logger writes JSONL lines with required fields
- [ ] `python -m compileall src/tmux_dashboard` succeeds
- [ ] Git status clean (changes committed)

## Next Steps

After completing this card:
1. Update state.json: set card 01 to "completed"
2. Read next card: [02-tmux-dashboard-tmux-manager.md](./02-tmux-dashboard-tmux-manager.md)
3. Continue execution
