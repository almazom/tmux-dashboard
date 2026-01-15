# Card 07: Tmux Dashboard - Delete with confirmation

| Field | Value |
|-------|-------|
| **ID** | TMUXD-07 |
| **Story Points** | 2 |
| **Depends On** | Previous card |
| **Sprint** | 3 |

## User Story

> As a user, I want to delete sessions safely with confirmation to avoid accidental loss.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Section 2.4
- [ui-flow.md](../ui-flow.md) - Delete confirmation

## Instructions

### Step 1: Add confirmation dialog

- On `d`, open a modal-style confirmation.
- Show session name and a warning if session is attached.

### Step 2: Respect dry-run

- If `TMUX_DASHBOARD_DRY_RUN=true`, block deletion and show message.

### Step 3: Execute deletion

- Call `TmuxManager.kill_session(name)` only after confirmation.
- Refresh list after deletion.

### Step 4: Verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] `d` opens confirmation dialog
- [ ] Attached sessions show warning before deletion
- [ ] Dry-run blocks deletion with a clear message
- [ ] Session is removed from list after delete
- [ ] `python -m compileall src/tmux_dashboard` succeeds

## Next Steps

After completing this card:
1. Update state.json: set card 07 to "completed"
2. Read next card: [08-tmux-dashboard-autostart.md](./08-tmux-dashboard-autostart.md)
3. Continue execution
