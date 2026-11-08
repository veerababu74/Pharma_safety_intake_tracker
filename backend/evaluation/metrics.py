"""RAG + agent evaluation metrics."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\-]+", text.lower()))


@dataclass
class RetrievalCase:
    query: str
    retrieved_ids: list[str]
    relevant_ids: list[str]
    answer: str = ""
    reference_answer: str = ""
    grounded_contexts: list[str] | None = None


def precision_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    hits = sum(1 for x in top if x in set(relevant))
    return hits / len(top)


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = set(list(retrieved)[:k])
    hits = sum(1 for x in relevant if x in top)
    return hits / len(relevant)


def mrr(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    rel = set(relevant)
    for i, item in enumerate(retrieved, start=1):
        if item in rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    rel = set(relevant)
    dcg = 0.0
    for i, item in enumerate(list(retrieved)[:k], start=1):
        gain = 1.0 if item in rel else 0.0
        dcg += gain / math.log2(i + 1)
    ideal_hits = min(len(rel), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def hit_rate(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    return 1.0 if set(list(retrieved)[:k]) & set(relevant) else 0.0


def answer_token_f1(answer: str, reference: str) -> float:
    pred = _tokens(answer)
    gold = _tokens(reference)
    if not pred or not gold:
        return 0.0
    common = len(pred & gold)
    precision = common / len(pred)
    recall = common / len(gold)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def grounding_overlap(answer: str, contexts: Iterable[str]) -> float:
    """Approx faithfulness: fraction of answer tokens found in contexts."""
    ans = _tokens(answer)
    if not ans:
        return 0.0
    ctx = set()
    for c in contexts:
        ctx |= _tokens(c)
    if not ctx:
        return 0.0
    return len(ans & ctx) / len(ans)


def refusal_correctness(answer: str, should_refuse: bool) -> float:
    refused = any(
        x in answer.lower()
        for x in ["insufficient", "out of scope", "cannot", "do not provide medical", "no grounded"]
    )
    return 1.0 if refused == should_refuse else 0.0


def evaluate_cases(cases: list[RetrievalCase], k: int = 5) -> dict[str, float]:
    if not cases:
        return {}
    metrics = {
        "precision@k": 0.0,
        "recall@k": 0.0,
        "mrr": 0.0,
        "ndcg@k": 0.0,
        "hit_rate@k": 0.0,
        "answer_f1": 0.0,
        "grounding_overlap": 0.0,
    }
    for case in cases:
        metrics["precision@k"] += precision_at_k(case.retrieved_ids, case.relevant_ids, k)
        metrics["recall@k"] += recall_at_k(case.retrieved_ids, case.relevant_ids, k)
        metrics["mrr"] += mrr(case.retrieved_ids, case.relevant_ids)
        metrics["ndcg@k"] += ndcg_at_k(case.retrieved_ids, case.relevant_ids, k)
        metrics["hit_rate@k"] += hit_rate(case.retrieved_ids, case.relevant_ids, k)
        if case.reference_answer:
            metrics["answer_f1"] += answer_token_f1(case.answer, case.reference_answer)
        if case.grounded_contexts is not None:
            metrics["grounding_overlap"] += grounding_overlap(case.answer, case.grounded_contexts)
    n = len(cases)
    return {k: v / n for k, v in metrics.items()}
