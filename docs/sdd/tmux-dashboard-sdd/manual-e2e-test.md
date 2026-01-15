# Manual E2E Test Checklist

**Prerequisites:**
- [ ] Python 3.11 installed
- [ ] tmux installed and running
- [ ] zsh + oh-my-zsh configured
- [ ] Dashboard script available (e.g., `~/bin/tmux_dashboard.py`)
- [ ] `TMUX_DASHBOARD_DRY_RUN=false` for delete tests

**Test Environment:**
- Dry-run mode: disabled
- Test data: at least 2 tmux sessions exist

## Test Cases

### Test 1: Basic Flow (attach + detach)

Steps:
1. [ ] Login via SSH (interactive).
2. [ ] Verify: dashboard auto-starts (no shell prompt).
3. [ ] Select existing session and press Enter.
4. [ ] Verify: tmux attaches to the session.
5. [ ] Detach (Ctrl+b, d).
6. [ ] Verify: dashboard returns automatically.
7. [ ] Press `q`.
8. [ ] Verify: SSH session closes (no shell).

Expected result: ✅ Dashboard loop and exit behavior work

### Test 2: Create Session

Steps:
1. [ ] From dashboard, press `n`.
2. [ ] Enter name `tmp-e2e` and confirm.
3. [ ] Verify: tmux attaches to new session.
4. [ ] Detach.
5. [ ] Verify: `tmp-e2e` is listed.

Expected result: ✅ Create + auto-attach works

### Test 3: Search/Filter

Steps:
1. [ ] Press `/` and type `tmp`.
2. [ ] Verify: list filters to matching sessions.
3. [ ] Press Enter to attach first filtered session.

Expected result: ✅ Search mode works and attaches

### Test 4: Delete Session

Steps:
1. [ ] Select `tmp-e2e`.
2. [ ] Press `d`.
3. [ ] Confirm deletion.
4. [ ] Verify: session removed from list (`tmux has-session -t tmp-e2e` fails).

Expected result: ✅ Delete with confirmation works

### Test 5: Error Handling (no tmux server)

Steps:
1. [ ] Stop tmux server: `tmux kill-server`.
2. [ ] Launch dashboard.
3. [ ] Verify: empty state + prompt to create new session.
4. [ ] Create a new session.
5. [ ] Verify: tmux server starts and attach succeeds.

Expected result: ✅ Graceful fallback works

## Regression Tests

- [ ] Non-interactive SSH command (`ssh host 'ls'`) is not hijacked by dashboard
- [ ] Color fallback works in terminals without color support
- [ ] No broken terminal state after attach/detach cycle
