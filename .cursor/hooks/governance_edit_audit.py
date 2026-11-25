#!/usr/bin/env python3
"""Deterministic PostToolUse / afterFileEdit governance audit logger.

Reads Cursor hook JSON from stdin and appends one JSONL event to
`.governance/edit-audit.jsonl`. Never blocks the agent (fail-open).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / ".governance" / "edit-audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw[:2000]}

    event = {
        "timestamp": _now(),
        "hook": "post_tool_use_or_after_file_edit",
        "tool_name": payload.get("tool_name")
        or payload.get("toolName")
        or payload.get("tool")
        or "unknown",
        "file_path": payload.get("file_path")
        or payload.get("filePath")
        or payload.get("path")
        or None,
        "command": (payload.get("command") or "")[:500] or None,
        "status": "ok",
        "source": "cursor_governance_hook",
    }

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=True) + "\n")
    except OSError:
        # Fail open — never block agent edits
        pass

    # afterFileEdit / postToolUse expect optional JSON; empty object is fine
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
