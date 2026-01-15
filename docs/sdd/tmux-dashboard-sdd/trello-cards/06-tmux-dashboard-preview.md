# Card 06: Tmux Dashboard - Session preview pane

| Field | Value |
|-------|-------|
| **ID** | TMUXD-06 |
| **Story Points** | 3 |
| **Depends On** | Previous card |
| **Sprint** | 2 |

## User Story

> As a user, I want to preview windows and panes so I can identify the right session quickly.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Section 3.3
- [ui-flow.md](../ui-flow.md) - Preview area

## Instructions

### Step 1: Fetch preview data

- Use `TmuxManager.get_session_details(name)` for the selected session.
- Limit output to `preview_lines` from config.

### Step 2: Render preview pane

- Add a right-side or bottom pane for preview.
- Show window name and pane current command.
- If details unavailable, show "No preview available".

### Step 3: Handle errors gracefully

- If tmux query fails, show a short error in status bar.
- Do not crash the UI loop.

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] Preview pane shows windows/panes for selected session
- [ ] Output is capped by `preview_lines`
- [ ] Errors are shown in status bar without crashing
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 06 to "completed"
2. Read next card: [07-tmux-dashboard-delete.md](./07-tmux-dashboard-delete.md)
3. Continue execution
