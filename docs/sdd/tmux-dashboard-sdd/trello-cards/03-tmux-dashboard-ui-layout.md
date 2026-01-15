# Card 03: Tmux Dashboard - Curses dashboard layout

| Field | Value |
|-------|-------|
| **ID** | TMUXD-03 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 1 |

## User Story

> As a user, I want a clear dashboard layout so I can see sessions and context at a glance.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Sections 3.1, 5.2
- [ui-flow.md](../ui-flow.md) - Main Dashboard template

## Instructions

### Step 1: Implement UI module

Create `src/tmux_dashboard/ui.py` with:
- curses init helpers (colors, noecho, cbreak, curs_set)
- `render_list(stdscr, sessions, selected_index)`
- `render_status(stdscr, message)`
- `render_empty_state(stdscr)` when no sessions

### Step 2: Build layout rules

- Title bar with app name and help/exit hints
- Main list area
- Preview pane placeholder (filled in later card)
- Footer with key hints

### Step 3: Add base app loop scaffold

Create `src/tmux_dashboard/app.py` with:
- `run()` that calls `curses.wrapper(main)`
- `main(stdscr)` loads sessions via `TmuxManager` and renders initial UI

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] Dashboard renders list with selected highlight
- [ ] Colors enabled with fallback to monochrome
- [ ] Empty state message renders when no sessions
- [ ] `curses.wrapper` used and terminal state restored on exit
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 03 to "completed"
2. Read next card: [04-tmux-dashboard-input-actions.md](./04-tmux-dashboard-input-actions.md)
3. Continue execution
