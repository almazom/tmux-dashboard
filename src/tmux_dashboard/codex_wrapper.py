"""Wrap raw Codex output into JSONL for headless streaming."""

from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tmux-dashboard-codex-wrapper",
        description="Wrap stdin lines into JSONL events.",
    )
    parser.add_argument(
        "--raw-to-stderr",
        action="store_true",
        help="Mirror raw input lines to stderr for interactive viewing.",
    )
    args = parser.parse_args(argv)

    for raw in sys.stdin:
        if args.raw_to_stderr:
            sys.stderr.write(raw)
            sys.stderr.flush()
        line = raw.rstrip("\r\n")
        payload = {
            "timestamp": time.time(),
            "type": "output",
            "content": line,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
