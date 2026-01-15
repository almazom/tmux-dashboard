# Agent Protocol - State Management & Execution

> Reference from KICKOFF.md when needed
> This document provides state update patterns for 9 cards.

## State File: state.json

The `state.json` file tracks execution progress. Update it after EACH card.

### State Structure (abridged)

```json
{
  "overall_status": "NOT_STARTED",
  "current_card": null,
  "cards": {
    "01": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "02": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "03": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "04": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "05": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "06": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "07": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "08": { "status": "pending", "started_at": null, "completed_at": null, "error": null },
    "09": { "status": "pending", "started_at": null, "completed_at": null, "error": null }
  },
  "execution_log": []
}
```

## State Update Patterns

### Start a Card (example for card 01)

```bash
jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.cards."01".status = "in_progress" | .cards."01".started_at = $now | .current_card = "01"' \
  state.json > state.json.tmp && mv state.json.tmp state.json

jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.execution_log += [{timestamp: $now, level: "INFO", message: "Card 01 started", card: "01"}]' \
  state.json > state.json.tmp && mv state.json.tmp state.json
```

### Complete a Card (example for card 01)

```bash
jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.cards."01".status = "completed" | .cards."01".completed_at = $now' \
  state.json > state.json.tmp && mv state.json.tmp state.json

jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.execution_log += [{timestamp: $now, level: "INFO", message: "Card 01 completed", card: "01"}]' \
  state.json > state.json.tmp && mv state.json.tmp state.json
```

### Fail a Card (example for card 02)

```bash
jq --arg err "Error description" \
  '.cards."02".status = "failed" | .cards."02".error = $err | .overall_status = "FAILED"' \
  state.json > state.json.tmp && mv state.json.tmp state.json

jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.execution_log += [{timestamp: $now, level: "ERROR", message: "Card 02 failed", card: "02"}]' \
  state.json > state.json.tmp && mv state.json.tmp state.json
```

### Complete All Cards

```bash
TOTAL=$(jq -r '.cards | length' state.json)
DONE=$(jq -r '[.cards | to_entries[] | select(.value.status == "completed")] | length' state.json)
if [ "$TOTAL" -eq "$DONE" ]; then
  jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '.overall_status = "COMPLETE" | .completed_at = $now' \
    state.json > state.json.tmp && mv state.json.tmp state.json
fi
```

## Execution Log Format

Each log entry should include:

```json
{
  "timestamp": "2026-01-15T14:12:23Z",
  "level": "INFO",
  "message": "Card 01 completed",
  "card": "01"
}
```

## Notes

- Use UTC timestamps in state.json for consistency.
- Repeat the examples above for other cards by changing the card number.
