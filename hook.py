"""
Vibe hook — receives Claude Code hook events on stdin, appends to the event log.

Invoked by Claude Code via ~/.claude/settings.json. Must exit fast (< 50 ms),
because Claude waits for hooks before continuing. No I/O other than the log write.

Event record format (one JSON object per line in ~/.vibe/sessions.jsonl):
    {
      "ts": 1713470000.123,          # epoch seconds, monotonic enough for ordering
      "event": "Stop",               # hook_event_name
      "session_id": "...",
      "cwd": "D:/Code/foo",
      "transcript": "...",
      "extra": { ...event-specific... }
    }
"""

import json
import os
import sys
import time
from pathlib import Path

VIBE_DIR = Path(os.path.expanduser("~")) / ".vibe"
LOG_PATH = VIBE_DIR / "sessions.jsonl"


def main() -> int:
    event_hint = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {"_parse_error": True, "_raw": raw[:500] if raw else ""}

    record = {
        "ts": time.time(),
        "event": payload.get("hook_event_name") or event_hint or "Unknown",
        "session_id": payload.get("session_id", ""),
        "cwd": payload.get("cwd", ""),
        "transcript": payload.get("transcript_path", ""),
        "extra": {
            k: v for k, v in payload.items()
            if k not in ("hook_event_name", "session_id", "cwd", "transcript_path")
        },
    }

    VIBE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
