# Card 08: Tmux Dashboard - zsh auto-start integration

| Field | Value |
|-------|-------|
| **ID** | TMUXD-08 |
| **Story Points** | 2 |
| **Depends On** | Previous card |
| **Sprint** | 3 |

## User Story

> As a user, I want the dashboard to auto-start on SSH login without breaking non-interactive commands.

## Context

Read before starting:
- [requirements.md](../requirements.md) - Section 1.1
- [ui-flow.md](../ui-flow.md) - Auto-start step

## Instructions

### Step 1: Document the zsh snippet

Add documentation snippet (e.g., in project README or `docs/INSTALL.md`):

```zsh
# ~/.zshrc or ~/.zprofile
if [[ $- == *i* ]] && [[ -z "${TMUX}" ]]; then
  exec python3 /path/to/tmux_dashboard.py
fi
```

### Step 2: Optional helper script

Create `scripts/install_zsh_autostart.sh` to append the snippet safely and idempotently.

### Step 3: Non-interactive safety

- Ensure snippet only runs for interactive shells.
- Confirm it does not break `ssh user@host 'cmd'`.

### Step 4: Verification

```bash
# Simulate interactive shell
zsh -i -c 'echo ok'
```

## Acceptance Criteria

- [ ] zsh auto-start snippet is documented
- [ ] Interactive + non-TMUX check is present
- [ ] Non-interactive SSH commands remain unaffected
- [ ] Helper script (if added) is idempotent

## Next Steps

After completing this card:
1. Update state.json: set card 08 to "completed"
2. Read next card: [09-tmux-dashboard-manual-e2e.md](./09-tmux-dashboard-manual-e2e.md)
3. Continue execution
