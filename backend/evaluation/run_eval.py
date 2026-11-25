"""Run offline evaluation harness (classic retrieval metrics + RAGAS)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.dataset import load_gold_cases
from evaluation.metrics import RetrievalCase, evaluate_cases, refusal_correctness
from evaluation.ragas_eval import run_ragas_evaluation

ROOT = Path(__file__).resolve().parent


def _classic_report(k: int = 5) -> dict:
    gold = load_gold_cases()
    cases = [
        RetrievalCase(
            query=c.question,
            retrieved_ids=c.retrieved_ids,
            relevant_ids=c.relevant_ids,
            answer=c.answer,
            reference_answer=c.reference_answer,
            grounded_contexts=c.contexts,
        )
        for c in gold
    ]
    metrics = evaluate_cases(cases, k=k)
    refuse_scores = [refusal_correctness(c.answer, c.should_refuse) for c in gold]
    metrics["refusal_accuracy"] = sum(refuse_scores) / len(refuse_scores) if refuse_scores else 0.0
    return {
        "mode": "classic",
        "n_cases": len(cases),
        "k": k,
        "metrics": {key: round(float(val), 4) for key, val in metrics.items()},
    }


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Pharma intake RAG evaluation harness")
    parser.add_argument(
        "--mode",
        choices=["classic", "ragas", "both"],
        default="both",
        help="classic=precision/recall/MRR/...; ragas=RAGAS metrics; both=combined report",
    )
    parser.add_argument("--k", type=int, default=5, help="Cutoff k for classic retrieval metrics")
    parser.add_argument(
        "--force-heuristic",
        action="store_true",
        help="Force heuristic RAGAS-like scores (no LLM / no ragas package)",
    )
    parser.add_argument(
        "--prefer-llm-judge",
        action="store_true",
        help="Prefer project LLM-as-judge RAGAS-style metrics over official ragas package",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(ROOT / "last_eval_report.json"),
        help="Output JSON report path",
    )
    args = parser.parse_args(argv)

    report: dict = {"modes": args.mode}
    if args.mode in {"classic", "both"}:
        report["classic"] = _classic_report(k=args.k)
    if args.mode in {"ragas", "both"}:
        report["ragas"] = run_ragas_evaluation(
            force_heuristic=args.force_heuristic,
            prefer_llm_judge=args.prefer_llm_judge,
        )

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return report


if __name__ == "__main__":
    main()
