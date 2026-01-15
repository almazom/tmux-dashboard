# Tmux Dashboard - Keybinding Detection Spec

> Status: READY | Last updated: 2026-01-15 (MSK)

## Purpose

Define exact keybindings that trigger actions in the Tmux Dashboard UI.

## Detection Strategy

**Approach:** Direct curses keycode matching (no text parsing in v1)

## Keybindings (FINAL LIST)

**Total: 10 bindings** - Exact match on keycode

### Group 1: Navigation

| # | Key | Action |
|---|-----|--------|
| 1 | `KEY_UP` | Move selection up |
| 2 | `KEY_DOWN` | Move selection down |

### Group 2: Primary Actions

| # | Key | Action |
|---|-----|--------|
| 3 | `ENTER` | Attach to selected session |
| 4 | `n` | Create new session |
| 5 | `d` | Delete selected session (confirm) |
| 6 | `/` | Enter search mode |
| 7 | `r` | Refresh list |

### Group 3: Help & Exit

| # | Key | Action |
|---|-----|--------|
| 8 | `F1` or `?` | Toggle help overlay |
| 9 | `q` | Exit dashboard (logout) |
|10 | `Ctrl+C` | Exit dashboard (logout) |

## Matching Rules (CONFIRMED)

- [x] Case-sensitive for letter keys (`n`, `d`, `q`, `r`, `/`).
- [x] Exact keycode match for special keys (arrows, Enter, F1).
- [x] Mode-aware: search input consumes characters until `Enter` or `Esc`.

## Implementation Code (Python)

```python
# File: src/tmux_dashboard/input_handler.py

KEYMAP = {
    curses.KEY_UP: "move_up",
    curses.KEY_DOWN: "move_down",
    10: "attach",  # Enter
    ord('n'): "create",
    ord('d'): "delete",
    ord('/'): "search",
    ord('r'): "refresh",
    curses.KEY_F1: "help",
    ord('?'): "help",
    ord('q'): "exit",
}
```

## Edge Cases

| Input | Expected | Reason |
|-------|----------|--------|
| `Enter` in search mode | Attach first filtered session | Fast path for search |
| `d` on attached session | Show warning before confirm | Prevent accidental disconnect |
| Unknown key | No-op | Avoid unexpected actions |

## Performance

- Key handling in O(1) per event.
- No regex, no text parsing.
