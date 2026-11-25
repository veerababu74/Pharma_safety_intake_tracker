#!/usr/bin/env python3
"""Claude Code PostToolUse governance audit logger (fail-open).

Mirrors `.cursor/hooks/governance_edit_audit.py` so both Cursor and Claude Code
append deterministic edit events to `.governance/edit-audit.jsonl`.
Payloads store tool name + path only — never prompt text or secrets.
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

    # Claude Code may nest tool input under tool_input / tool_response
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    event = {
        "timestamp": _now(),
        "hook": "claude_post_tool_use",
        "tool_name": payload.get("tool_name")
        or payload.get("toolName")
        or payload.get("tool")
        or "unknown",
        "file_path": tool_input.get("file_path")
        or tool_input.get("filePath")
        or tool_input.get("path")
        or payload.get("file_path")
        or payload.get("filePath")
        or None,
        "command": str(tool_input.get("command") or payload.get("command") or "")[:500] or None,
        "status": "ok",
        "source": "claude_governance_hook",
    }

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=True) + "\n")
    except OSError:
        pass

    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
