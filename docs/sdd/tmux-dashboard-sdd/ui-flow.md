# Tmux Dashboard - UI Flow

> Status: READY | Last updated: 2026-01-15 (MSK)

## User Journey

```
┌────────────────────────────────────────────┐
│                SSH LOGIN                   │
│  User connects via SSH                     │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│           ZSH AUTO-START                   │
│  ~/.zshrc exec python3 tmux_dashboard      │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│         DASHBOARD (CURSES UI)              │
│  List sessions + preview + help            │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│             USER ACTION                    │
│  Enter / n / d / / / r / F1 / q             │
└───────┬────────────┬───────────┬───────────┘
        │            │           │
        ▼            ▼           ▼
  Attach session  Create new   Delete session
  (child process) (prompt)     (confirm)
        │            │           │
        ▼            ▼           ▼
  tmux attach     tmux new     tmux kill
        │            │           │
        ▼            ▼           ▼
  Detach → return  Auto-attach  Return to list
  to dashboard

  q / Ctrl+C → SSH logout (no shell)
```

## Screen Templates

### Main Dashboard

```
Tmux Dashboard                         [F1 Help]  [q Exit]
──────────────────────────────────────────────────────────
> mysession     [attached]  windows: 3
  build         [detached]  windows: 1
  logs          [detached]  windows: 2
  + Create new session
──────────────────────────────────────────────────────────
Preview:
- window: editor
  - pane: vim (pane_current_command)
- window: api
  - pane: python (pane_current_command)
──────────────────────────────────────────────────────────
Keys: ↑/↓ move  Enter attach  n new  d delete  / search  r refresh
```

### Create Session Prompt

```
Create new session
Name: [______________]
[Enter] create   [Esc] cancel
```

### Delete Confirmation

```
Delete session "build"?
This will terminate running processes.
[Enter] confirm   [Esc] cancel
```

### Search Mode

```
Search: [api]
Filtered sessions: api-dev, api-prod
[Enter] attach   [Esc] clear
```

### Help Overlay

```
Keys:
- Enter: attach
- n: create new session
- d: delete session
- /: search
- r: refresh list
- F1 or ?: help
- q / Ctrl+C: exit (logout)
```

## Open Questions

- None
