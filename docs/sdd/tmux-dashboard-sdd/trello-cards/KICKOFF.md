# Tmux Dashboard Implementation - AI Agent Kickoff

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   🤖 AI AGENT INSTRUCTION                                                    ║
║                                                                              ║
║   Execute ALL 9 cards below in LINEAR order.                                 ║
║   Update state.json after EACH card.                                         ║
║   Do NOT stop until all cards are "completed".                               ║
║                                                                              ║
║   START NOW. First action: Read state.json, find first pending card.         ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

> **ENTRY POINT**: This is the ONLY file you need. Everything is linked from here.
> This file is SELF-CONTAINED. Do not ask for clarification - all info is here.

## Mission

Implement the Tmux Dashboard feature by executing 9 Trello cards in linear order.
Track progress in `state.json`. Update after each step. Never skip cards.

**DRY-RUN MODE IS ON** - no destructive actions during development.

## Protocol

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT EXECUTION LOOP                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. READ state.json → Find current card (status = "pending")            │
│  2. UPDATE state.json → Set card to "in_progress"                       │
│  3. READ card file → Execute all instructions                           │
│  4. VERIFY → Check all acceptance criteria                              │
│  5. UPDATE state.json → Set card to "completed" or "failed"             │
│  6. UPDATE progress.md → Render progress bar                            │
│  7. LOOP → Go to step 1 until all cards completed                       │
│                                                                         │
│  ON ERROR: Set card to "failed", add error message, STOP for help        │
│  ON COMPLETE: Set overall status to "COMPLETE"                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose | Agent Action |
|------|---------|--------------|
| [BOARD.md](./BOARD.md) | Card overview and pipeline | Read once at start |
| [state.json](./state.json) | Progress tracking | Read+write each card |
| [AGENT_PROTOCOL.md](./AGENT_PROTOCOL.md) | State update patterns | Reference when needed |
| [01-tmux-dashboard-scaffold.md](./01-tmux-dashboard-scaffold.md) | First card | **Execute** |
| [02-tmux-dashboard-tmux-manager.md](./02-tmux-dashboard-tmux-manager.md) | Second card | **Execute** |
| ... | ... | ... |
| [09-tmux-dashboard-manual-e2e.md](./09-tmux-dashboard-manual-e2e.md) | Last card | **Execute** |

## Getting Started

```bash
cd trello-cards
ls -la
```

**First action:** Read [BOARD.md](./BOARD.md) to understand card sequence.

**Second action:** Read [state.json](./state.json) to find current card.

**Then:** Execute cards in order: 01 → 02 → 03 → ... → 09

## Completion Criteria

- [ ] All cards in state.json show "completed"
- [ ] No errors in execution log
- [ ] Manual E2E test passes (see card 09)
- [ ] DRY_RUN can be set to false safely

## Troubleshooting

### If a command fails:

1. **Read the error message**
2. **Check file exists:** `ls -la path/to/file`
3. **Check syntax:** `cat file | head -20`
4. **Check dependencies:** Previous cards complete?
5. **Document error** in state.json
6. **Get help** if stuck >10 minutes

### If state.json is missing:

```bash
cat > state.json << 'EOF'
{
  "overall_status": "IN_PROGRESS",
  "started_at": "2026-01-15T14:12:23Z",
  "current_card": "01",
  "cards": {
    "01": { "status": "pending", "started_at": null, "completed_at": null },
    "02": { "status": "pending", "started_at": null, "completed_at": null },
    "03": { "status": "pending", "started_at": null, "completed_at": null },
    "04": { "status": "pending", "started_at": null, "completed_at": null },
    "05": { "status": "pending", "started_at": null, "completed_at": null },
    "06": { "status": "pending", "started_at": null, "completed_at": null },
    "07": { "status": "pending", "started_at": null, "completed_at": null },
    "08": { "status": "pending", "started_at": null, "completed_at": null },
    "09": { "status": "pending", "started_at": null, "completed_at": null }
  },
  "execution_log": []
}
EOF
```

## Success Definition

This implementation is **SUCCESSFUL** when:

1. ✅ Auto-start launches the dashboard after SSH login
2. ✅ Session list, search, and preview render correctly
3. ✅ Attach/create/delete actions work with confirmations
4. ✅ Detach returns to dashboard loop
5. ✅ Exit closes SSH (no shell)
6. ✅ Logging is JSONL and includes required fields
7. ✅ Error handling works with graceful fallback
8. ✅ Manual E2E test passes

---

## 🎯 Git Flow Enforcement - MANDATORY

**You MUST follow git flow and create a Pull Request. This is NOT optional.**

### Phase 1: Auto-Commit Setup (Start Immediately)

Before executing cards, start the auto-commit daemon:

```bash
# Start background auto-commit subagent (checks every 5 minutes)
nohup ./auto-commit-daemon.sh --feature "tmux-dashboard" &

# Or start with custom interval (e.g., 10 minutes)
nohup ./auto-commit-daemon.sh --feature "tmux-dashboard" --interval 600 &

# Check daemon status
ps aux | grep auto-commit-daemon

# Stop daemon when done
./auto-commit-daemon.sh --stop
```

### Phase 2: Final Git Flow Steps (After Final Card)

**After completing card 09, you MUST execute these commands:**

```bash
# 1. Ensure all changes are committed (daemon likely did this)
git status

# 2. If any remaining changes, commit manually
./smart_commit.sh --feature "tmux-dashboard"

# 3. Verify branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "On branch: $CURRENT_BRANCH"

# 4. Push branch to remote
git push -u origin "$CURRENT_BRANCH"

# 5. Create Pull Request (FORCEFUL - DO NOT SKIP)
# GitHub CLI PR creation
if command -v gh &> /dev/null; then
    gh pr create \
        --title "feat: tmux-dashboard implementation" \
        --body "Automated PR from SDD Flow implementation\n\n- Feature: tmux-dashboard\n- Cards completed: 9\n- Status: Ready for review" \
        --base main
fi
```

---

**NOW BEGIN.** First card: [01-tmux-dashboard-scaffold.md](./01-tmux-dashboard-scaffold.md)
