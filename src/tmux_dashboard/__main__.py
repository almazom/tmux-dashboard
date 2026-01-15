"""Run with: python -m tmux_dashboard

Config path default: ~/.config/tmux-dashboard/config.json
"""

from .app import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
