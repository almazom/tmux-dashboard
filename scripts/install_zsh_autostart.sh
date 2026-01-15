#!/usr/bin/env zsh
set -euo pipefail

TARGET_FILE="${1:-$HOME/.zshrc}"
DASHBOARD_CMD="${TMUX_DASHBOARD_CMD:-python3 -m tmux_dashboard}"
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
if [[ \$- == *i* ]] && [[ -z "\${TMUX}" ]]; then
  exec $DASHBOARD_CMD
fi
EOF_SNIPPET

echo "Autostart snippet added to $TARGET_FILE"
