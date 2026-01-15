# Card 04: Tmux Dashboard - Input handling and core actions

| Field | Value |
|-------|-------|
| **ID** | TMUXD-04 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 2 |

## User Story

> As a user, I want keyboard controls to navigate, attach, create, and exit.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Sections 2.2, 2.3, 3.1
- [keyword-detection.md](../keyword-detection.md) - Keybindings

## Instructions

### Step 1: Implement input handler

Create `src/tmux_dashboard/input_handler.py`:
- Main event loop reading `stdscr.getch()`
- Move selection on arrow keys
- Enter → attach selected session
- `n` → prompt for new session name
- `q` / Ctrl+C → exit (logout)

### Step 2: Attach behavior

- Before running attach, call `curses.endwin()`.
- Run `subprocess.run(tmux_manager.attach_command(name))`.
- After detach, reinitialize curses and return to dashboard loop.

### Step 3: Create session prompt

- Use a minimal input line at bottom of screen.
- Validate name (non-empty, trim spaces).
- Create session via `TmuxManager.create_session(name)` then attach.

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] Arrow keys move selection without errors
- [ ] Enter attaches and returns to dashboard after detach
- [ ] `n` prompts for name, creates session, auto-attaches
- [ ] `q`/Ctrl+C exits and closes SSH session
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 04 to "completed"
2. Read next card: [05-tmux-dashboard-search-help.md](./05-tmux-dashboard-search-help.md)
3. Continue execution
