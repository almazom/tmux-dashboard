# Card 05: Tmux Dashboard - Search/filter and help

| Field | Value |
|-------|-------|
| **ID** | TMUXD-05 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 2 |

## User Story

> As a user, I want quick search and help so I can navigate many sessions fast.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Sections 3.2, 3.4
- [ui-flow.md](../ui-flow.md) - Search mode and Help overlay

## Instructions

### Step 1: Implement search mode

- `/` enters search mode and shows input line.
- Filter sessions by substring (case-insensitive by default).
- `Esc` clears search and returns to full list.

### Step 2: Add refresh

- `r` reloads sessions from `TmuxManager` and resets selection if out of range.

### Step 3: Help overlay

- `F1` or `?` toggles help screen with key list.
- Overlay should not destroy current selection or filter.

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] `/` enters search mode and filters list
- [ ] `Esc` clears search and restores full list
- [ ] `r` refreshes list without crash
- [ ] `F1`/`?` toggles help overlay
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 05 to "completed"
2. Read next card: [06-tmux-dashboard-preview.md](./06-tmux-dashboard-preview.md)
3. Continue execution
