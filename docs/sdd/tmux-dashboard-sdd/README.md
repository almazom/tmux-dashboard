# Tmux Dashboard - SDD Requirements

> Status: READY FOR IMPLEMENTATION | All gaps filled

## Overview

This folder contains Spec-Driven Development (SDD) documentation for the Tmux Dashboard feature.

## Documents

| File | Description | Status |
|------|-------------|--------|
| [requirements.md](./requirements.md) | Functional requirements | READY |
| [ui-flow.md](./ui-flow.md) | User interaction flow | READY |
| [keyword-detection.md](./keyword-detection.md) | Keybinding detection spec | READY |
| [gaps.md](./gaps.md) | Open questions & gaps | READY |
| [manual-e2e-test.md](./manual-e2e-test.md) | Manual end-to-end tests | READY |

## Pipeline Summary

```
SSH Login → zsh auto-start → Dashboard render → Action selection
       ↓                     ↓               ↓
  (no raw shell)        List/search/preview  Attach/Create/Delete/Exit
       ↓                     ↓               ↓
  tmux attach (child) → detach returns → dashboard loop or SSH exit
```

## Quick Reference

| Aspect | Decision |
|--------|----------|
| **Channel** | Interactive SSH (zsh + oh-my-zsh) |
| **Detection** | Curses keybinding handling (no text parsing) |
| **Required Fields** | action, session_name (for attach/create/delete) |
| **Execution** | libtmux for metadata + tmux CLI for attach/kill |
| **Delivery** | tmux client attach or SSH logout |
| **Config** | `~/.config/tmux-dashboard/config.json` + `TMUX_DASHBOARD_*` env vars |

## Development Notes

- [ ] Add dry-run guard for destructive actions (delete)
- [ ] Follow module split: `tmux_manager`, `ui`, `input_handler`, `app`
- [ ] Location: `src/tmux_dashboard/`

## Implementation

See [trello-cards/BOARD.md](./trello-cards/BOARD.md) for:
- 9 executable cards (24 SP total)
- Linear execution order
- Machine-friendly instructions
- Max 4 SP per card
