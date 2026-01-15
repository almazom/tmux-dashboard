# Card 09: Tmux Dashboard - Manual E2E and verification

| Field | Value |
|-------|-------|
| **ID** | TMUXD-09 |
| **Story Points** | 2 |
| **Depends On** | Previous card |
| **Sprint** | 3 |

## User Story

> As a user, I want confidence that all core flows work end-to-end before completion.

## Context

Read before starting:
- [manual-e2e-test.md](../manual-e2e-test.md) - Full checklist
- [requirements.md](../requirements.md) - Acceptance-critical behaviors

## Instructions

### Step 1: Run manual checklist

Follow every step in `manual-e2e-test.md`.

### Step 2: Capture results

- Record pass/fail notes in a simple log file (e.g., `docs/test-results.md`).
- Log any deviations and fixes applied.

### Step 3: Final verification

```bash
python -m compileall src/tmux_dashboard
```

## Acceptance Criteria

- [ ] All manual E2E tests pass
- [ ] Search, preview, delete, and auto-start behaviors verified
- [ ] Error handling tested (no tmux server)
- [ ] Terminal state restores correctly after detach
- [ ] Test results recorded

## Next Steps

After completing this card:
1. Update state.json: set card 09 to "completed"
2. Set overall status to "COMPLETE"
3. Prepare PR per KICKOFF.md
