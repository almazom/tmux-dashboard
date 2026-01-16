"""Run with: python -m tmux_dashboard

Config path default: ~/.config/tmux-dashboard/config.json
"""

import sys

from .app import main as _main


if __name__ == "__main__":
    sys.exit(_main())
