# Install and Autostart (zsh)

## Run the dashboard

From the repo root:

```bash
PYTHONPATH=./src python3 -m tmux_dashboard
```

## Enable autostart on SSH login

Add this snippet to `~/.zshrc` or `~/.zprofile`:

```zsh
if [[ $- == *i* ]] && [[ -z "${TMUX}" ]]; then
  exec python3 -m tmux_dashboard
fi
```

Notes:
- The `exec` call prevents access to a raw shell after SSH login.
- The interactive check keeps non-interactive SSH commands working.
- Adjust the command if you install the module elsewhere.

## Optional helper script

Use `scripts/install_zsh_autostart.sh` to append the snippet safely.
