#!/usr/bin/env zsh
set -euo pipefail

TARGET_FILE="${1:-$HOME/.zshrc}"
SCRIPT_DIR="${0:A:h}"
PROMPT_SCRIPT="$SCRIPT_DIR/ssh_login_prompt.sh"
MARKER="# tmux-dashboard autostart"

if [ ! -f "$TARGET_FILE" ]; then
  touch "$TARGET_FILE"
fi

if grep -q "$MARKER" "$TARGET_FILE"; then
  echo "Autostart snippet already present in $TARGET_FILE"
  exit 0
fi

cat >> "$TARGET_FILE" << EOF_SNIPPET

$MARKER
# Source the SSH login prompt script
if [[ -f "$PROMPT_SCRIPT" ]]; then
  source "$PROMPT_SCRIPT"
fi
EOF_SNIPPET

echo "Autostart snippet added to $TARGET_FILE"
echo "The prompt will ask users to choose Tmux Manager or Raw Shell on SSH login."
