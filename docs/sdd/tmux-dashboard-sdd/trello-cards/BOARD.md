# Tmux Dashboard - Trello Board

> Scrum Master: AI Agent | Sprint: Linear Execution
> Story Point Cap: 4 SP per card | Principle: KISS

## Execution Order

```
┌────────────────────────────────────────────────────────┐
│                     EXECUTION PIPELINE                 │
├────────────────────────────────────────────────────────┤
│                                                        │
│  SPRINT 1: Foundation                                  │
│  ┌─────┐   ┌─────┐   ┌─────┐                           │
│  │ 01  │ → │ 02  │ → │ 03  │                           │
│  │ 3SP │   │ 3SP │   │ 3SP │                           │
│  └─────┘   └─────┘   └─────┘                           │
│  Scaffold TmuxMgr  UI Layout                           │
│                                                        │
│  SPRINT 2: Interaction                                 │
│  ┌─────┐   ┌─────┐   ┌─────┐                           │
│  │ 04  │ → │ 05  │ → │ 06  │                           │
│  │ 3SP │   │ 3SP │   │ 3SP │                           │
│  └─────┘   └─────┘   └─────┘                           │
│  Input   Search/Help Preview                           │
│                                                        │
│  SPRINT 3: Safety & Ops                                │
│  ┌─────┐   ┌─────┐   ┌─────┐                           │
│  │ 07  │ → │ 08  │ → │ 09  │                           │
│  │ 2SP │   │ 2SP │   │ 2SP │                           │
│  └─────┘   └─────┘   └─────┘                           │
│  Delete  AutoStart  E2E                                │
│                                                        │
└────────────────────────────────────────────────────────┘
```

## Card Index

| Card | Title | SP | Depends On | Status |
|------|-------|----|-----------:|--------|
| [01](./01-tmux-dashboard-scaffold.md) | Scaffold app + config/logging | 3 | - | TODO |
| [02](./02-tmux-dashboard-tmux-manager.md) | Tmux manager core | 3 | 01 | TODO |
| [03](./03-tmux-dashboard-ui-layout.md) | Curses dashboard layout | 3 | 02 | TODO |
| [04](./04-tmux-dashboard-input-actions.md) | Input handling and core actions | 3 | 03 | TODO |
| [05](./05-tmux-dashboard-search-help.md) | Search/filter and help | 3 | 04 | TODO |
| [06](./06-tmux-dashboard-preview.md) | Session preview pane | 3 | 05 | TODO |
| [07](./07-tmux-dashboard-delete.md) | Delete with confirmation | 2 | 06 | TODO |
| [08](./08-tmux-dashboard-autostart.md) | zsh auto-start integration | 2 | 07 | TODO |
| [09](./09-tmux-dashboard-manual-e2e.md) | Manual E2E and verification | 2 | 08 | TODO |

## Sprint Summary

- Sprint 1: 9 SP
- Sprint 2: 9 SP
- Sprint 3: 6 SP

**Total Story Points: 24**

---

## ⚡ Auto-Commit Daemon (MANDATORY)

**Activate before starting cards:**
```bash
nohup ./auto-commit-daemon.sh --feature "tmux-dashboard" &
```

**This ensures:**
- ✅ Changes committed every 5 minutes automatically
- ✅ Never lose work
- ✅ Incremental commit history
- ✅ Zero cognitive overhead

---

## 🎯 Final PR Creation (CARD 09)

**After completing final card, execute:**
```bash
# 1. Verify all committed
git status

# 2. Push branch
./smart_commit.sh --feature "tmux-dashboard"
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"

# 3. Create Pull Request (MANDATORY)
gh pr create \
  --title "feat: tmux-dashboard implementation" \
  --body "Complete implementation of tmux-dashboard\n\n- Cards: 9\n- Status: Ready\n\nSee trello-cards/KICKOFF.md for details"
```

**⚠️ DO NOT MARK COMPLETE WITHOUT PR ⚠️**
