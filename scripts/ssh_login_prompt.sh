#!/usr/bin/env zsh
# SSH Login Prompt - Ask user to choose tmux manager or raw shell

set -euo pipefail

DASHBOARD_CMD="${TMUX_DASHBOARD_CMD:-python3 -m tmux_dashboard}"

# Only prompt on interactive shells not already in tmux
if [[ $- != *i* ]] || [[ -n "${TMUX:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

# Check if we're in an SSH session
if [[ -z "${SSH_CONNECTION:-}" ]] && [[ -z "${SSH_CLIENT:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

# Function to show the prompt and get user choice
_prompt_user() {
  while true; do
    echo ""
    echo "Welcome! How would you like to connect?"
    echo "  1) Tmux Manager (session manager dashboard)"
    echo "  2) Raw Shell (standard terminal)"
    echo ""
    echo -n "Choose [1-2] (default: 1): "
    read -r -k 1 choice 2>/dev/null || choice=""
    echo ""

    # Handle Enter key (default to 1)
    if [[ -z "$choice" ]] || [[ "$choice" == $'\n' ]]; then
      choice="1"
    fi

    case "$choice" in
      1|t|T|m|M)
        # Launch tmux manager
        exec $DASHBOARD_CMD
        ;;
      2|r|R|s|S)
        # Raw shell - just return to normal shell
        echo "Starting raw shell..."
        return 0
        ;;
      q|Q)
        echo "Exit requested. Use 'exit' to disconnect."
        return 0
        ;;
      *)
        echo "Invalid choice. Please enter 1 or 2."
        ;;
    esac
  done
}

# Run the prompt
_prompt_user
