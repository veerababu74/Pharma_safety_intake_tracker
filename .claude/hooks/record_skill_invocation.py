#!/usr/bin/env python3
"""Record that the pharma-intake-review skill (or another skill) was invoked.

Usage:
  python .claude/hooks/record_skill_invocation.py --skill pharma-intake-review --verdict PASS
  python .claude/hooks/record_skill_invocation.py --skill pharma-intake-review --verdict "PASS WITH NOTES" --files backend/app/modules/agents/prompts.py

Writes one JSONL row to `.governance/skill-invocations.jsonl` (no secrets, no chat text).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / ".governance" / "skill-invocations.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Record skill invocation evidence")
    parser.add_argument("--skill", default="pharma-intake-review")
    parser.add_argument("--verdict", default="PASS")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": args.skill,
        "verdict": args.verdict,
        "files_touched": list(args.files),
        "note": (args.note or "")[:240] or None,
        "source": "claude_skill_invocation",
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=True) + "\n")
    print(json.dumps(event, indent=2))
    print(f"Appended → {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
