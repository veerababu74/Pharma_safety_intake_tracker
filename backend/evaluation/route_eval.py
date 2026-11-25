"""Routing evaluation — intent accuracy and write safety for the agent router.

Usage:
    python -m evaluation.route_eval                # LLM-first router (as configured)
    python -m evaluation.route_eval --rules-only   # deterministic rules only (LLM disabled)

Gold sets: evaluation/gold/routing_gold.json + evaluation/gold/agent_gold.json.

Metrics
- accuracy:          routed intent == expected
- accepted_accuracy: routed intent in the case's accepted set; for write intents
                     (status/intake) a confirmation question ("clarify") is accepted
- unsafe_write_rate: read-only messages routed to a write intent — must be 0
- clarify_rate:      share of messages where the agent asked to confirm
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

GOLD_DIR = Path(__file__).resolve().parent / "gold"
OUT_PATH = Path(__file__).resolve().parent / "last_route_eval.json"
WRITE_INTENTS = {"status", "intake"}


def load_routing_cases() -> list[dict[str, Any]]:
    rows = json.loads((GOLD_DIR / "routing_gold.json").read_text(encoding="utf-8"))
    for a in json.loads((GOLD_DIR / "agent_gold.json").read_text(encoding="utf-8")):
        rows.append(
            {"id": a["id"], "utterance": a["utterance"], "expected": a["expected_intent"], "role": a.get("role")}
        )
    return rows


def _accepted(case: dict[str, Any]) -> set[str]:
    acc = set(case.get("accept") or [case["expected"]])
    if case["expected"] in WRITE_INTENTS:
        acc.add("clarify")
    return acc


def run(rules_only: bool = False) -> dict[str, Any]:
    from app.db.session import db_manager

    db_manager.init()
    import app.modules.agents.graph as g

    if rules_only:
        g._llm_route = lambda m, h: (None, {"router_source": "llm_disabled"})  # type: ignore[assignment]

    cases = load_routing_cases()
    results = []
    for case in cases:
        t0 = time.perf_counter()
        out = g.router_node(
            {
                "message": case["utterance"],
                "actor": "eval",
                "role": case.get("role") or "reviewer",
                "chat_history": case.get("history") or [],
            }
        )
        ms = (time.perf_counter() - t0) * 1000
        got = out["intent"]
        expected = case["expected"]
        results.append(
            {
                "id": case["id"],
                "utterance": case["utterance"],
                "expected": expected,
                "got": got,
                "correct": got == expected,
                "accepted": got in _accepted(case),
                "unsafe_write": expected not in WRITE_INTENTS
                and got in WRITE_INTENTS
                and got not in set(case.get("accept") or []),
                "router_source": (out.get("route_meta") or {}).get("router_source"),
                "slots": out.get("route_slots") or {},
                "latency_ms": round(ms, 1),
            }
        )

    n = len(results)
    per_intent: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        per_intent[r["expected"]].append(r["accepted"])
    report = {
        "mode": "rules_only" if rules_only else "llm_first",
        "cases": n,
        "accuracy": round(sum(r["correct"] for r in results) / n, 3),
        "accepted_accuracy": round(sum(r["accepted"] for r in results) / n, 3),
        "unsafe_write_rate": round(sum(r["unsafe_write"] for r in results) / n, 3),
        "clarify_rate": round(sum(r["got"] == "clarify" for r in results) / n, 3),
        "per_intent_accepted": {k: round(sum(v) / len(v), 3) for k, v in sorted(per_intent.items())},
        "router_sources": dict(Counter(r["router_source"] for r in results)),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / n, 1),
        "failures": [r for r in results if not r["accepted"] or r["unsafe_write"]],
        "results": results,
    }
    return report


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rules-only", action="store_true", help="disable the LLM router")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    report = run(rules_only=args.rules_only)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in {"results", "failures"}}
    print(json.dumps(summary, indent=2))
    for f in report["failures"]:
        flag = "UNSAFE " if f["unsafe_write"] else ""
        print(f"  {flag}{f['id']}: expected {f['expected']}, got {f['got']} ({f['router_source']}) — {f['utterance']}")
    return report


if __name__ == "__main__":
    main()
