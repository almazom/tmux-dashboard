# Headless Session Management Documentation

## Overview

This document describes the headless session management system implemented in `tmux-dashboard`. This feature allows users to spawn, monitor, and manage AI agent sessions that run in the background without requiring a dedicated terminal window (until the user chooses to attach).

## Problem Statement

Traditional tmux usage involves creating a session, attaching to it, running a command, and then detaching. For long-running AI tasks (e.g., "refactor this module", "write tests for X"), this workflow is friction-heavy:

1.  **Context Switching**: Users must manually create sessions and run commands.
2.  **Monitoring**: checking status requires attaching/detaching or parsing `tmux list-panes`.
3.  **Output Visibility**: It's hard to see "at a glance" what an agent is doing without full attachment.
4.  **Metadata Loss**: tmux sessions don't natively store structured metadata (e.g., "what prompt started this?", "which model is being used?").

## Solution Architecture

The "Headless Session" system introduces a metadata layer on top of standard tmux sessions.

### Core Components

1.  **HeadlessRegistry** (`headless.py`):
    *   Manages JSON metadata files in `~/.local/state/tmux-dashboard/headless/`.
    *   Tracks session lifecycle (created, running, completed).
    *   Stores AI-specific context: Agent name, Model, Instruction/Prompt, Flow.

2.  **HeadlessSession Model**:
    *   Data class representing the extended state.
    *   Includes `exit_code`, `last_raw_line` (for status previews), and `output_path`.

3.  **Tmux Integration** (`tmux_manager.py`):
    *   `create_session_with_command`: Spawns sessions with specific environment variables and commands.
    *   `get_session_runtime_status`: Checks if the pane is dead (process exited) and retrieves the exit code.

4.  **UI Extensions** (`ui.py`, `input_handler.py`):
    *   **'H' Keybinding**: triggers the headless creation wizard.
    *   **Live Preview**: Tails the agent's output log (JSONL or text) directly in the dashboard preview pane.
    *   **Status Indicators**: ✅ (Completed), ⏳ (Running), ⚠️ (Missing/Error).

### Data Flow

1.  **Creation**:
    *   User presses `H`.
    *   Enters Workdir, Agent (e.g., `codex`), Model (e.g., `gpt-4`), and Instruction.
    *   App generates a unique session name (e.g., `hl_codex_project_20260123-1000`).
    *   A shell command is constructed using a template (e.g., `codex run ...`).
    *   tmux session starts in background.
    *   Metadata is saved to registry.

2.  **Monitoring**:
    *   Dashboard loop polls `headless_registry` and `tmux` status.
    *   If a session is selected, `HeadlessLogTail` reads the output file.
    *   UI renders the status icon and preview lines.

3.  **Completion**:
    *   When the process exits, `tmux_manager` detects the exit code.
    *   Registry updates metadata with `completed_at` and `exit_code`.
    *   Optional notification (`t2me`) is sent.

## User Guide

### creating a Headless Session

1.  Press `H` in the dashboard.
2.  **Workdir**: Defaults to current directory. Press Enter to accept.
3.  **Agent**: Enter agent name (configured in `config.json`, e.g., `codex`, `cladcode`).
4.  **Model**: Select from list or type manual. (Support for `?` to list CLI models).
5.  **Instruction**: Enter the prompt for the agent.

### Viewing & Interaction

*   **Select**: Navigate to the session in the list. It will be marked with `H` and a status icon.
*   **Preview**: The right pane shows the live output log.
*   **Enter**: Opens a detailed "Headless View" with full prompt, metadata, and live log tailing.
    *   `p`: Toggle full prompt display.
    *   `r`: Force refresh.
    *   `a`: Attach (standard tmux attach).
    *   `i`: Send input (send text to the running process).
    *   `k`: Kill session.
    *   `q`: Return to dashboard.

### Configuration (`config.json`)

```json
{
  "headless_state_dir": "~/.local/state/tmux-dashboard/headless",
  "headless_output_dir": "~/.local/state/tmux-dashboard/headless/output",
  "headless_agents": {
    "codex": "codex run --model {model} --instruction {instruction} --output {output}",
    "cladcode": "cladcode --model {model} -m {instruction} > {output}"
  },
  "headless_models": {
    "codex": ["gpt-4", "gpt-3.5-turbo"],
    "cladcode": ["claude-3-opus", "claude-3-sonnet"]
  },
  "headless_default_agent": "codex"
}
```

## Implementation Details

### File Structure

*   **Metadata**: stored as JSON.
    ```json
    {
      "session_name": "hl_codex_...",
      "agent": "codex",
      "model": "gpt-4",
      "instruction": "Refactor app.py",
      "created_at": "2026-01-23T...",
      "status": "running"
    }
    ```
*   **Output**: stored as `.jsonl` or text files in `headless_output_dir`. The dashboard tails these files for preview.

### Log Tailing

The `HeadlessLogTail` class implements a robust tailing mechanism:
*   Handles log rotation/truncation.
*   Parses JSON lines for structured events (e.g., `{"type": "tool_use", ...}`).
*   Summarizes events with emojis (🛠, 🧠, 💬) for the UI.

## Troubleshooting

1.  **"Headless command template error"**: Check `headless_agents` in config. Ensure all placeholders (`{model}`, `{instruction}`) are valid.
2.  **Output not showing**: Ensure the agent writes to the `{output}` path provided in the template.
3.  **Session marked "missing"**: The tmux session was killed manually (outside dashboard) but metadata remains. Use `d` to delete the metadata entry.
