"""RAGAS-based RAG evaluation.

Order of execution:
1) Official `ragas` library when importable + non-mock LLM configured
2) Project-native LLM-as-judge metrics (RAGAS-style prompts) via configured LLM
3) Deterministic heuristic proxies (offline / mock / CI)

Metrics:
- faithfulness
- answer_relevancy
- context_precision
- context_recall
- answer_correctness
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging import get_logger
from evaluation.dataset import EvalCase, load_gold_cases
from evaluation.metrics import answer_token_f1, grounding_overlap, precision_at_k, recall_at_k

logger = get_logger("ragas_eval")

_METRIC_KEYS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
)


def _avg(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def _extract_score(raw: str, default: float = 0.0) -> float:
    """Parse a 0-1 score from LLM output."""
    text = (raw or "").strip()
    # Prefer explicit JSON {"score": 0.8}
    try:
        fence = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
        if fence:
            data = json.loads(fence.group(0))
            if isinstance(data, dict) and "score" in data:
                return max(0.0, min(1.0, float(data["score"])))
    except Exception:
        pass
    # Fallback: first float in text
    m = re.search(r"(?<![A-Za-z])(0(?:\.\d+)?|1(?:\.0+)?)(?![A-Za-z0-9])", text)
    if m:
        try:
            return max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            return default
    return default


def _heuristic_ragas_scores(cases: list[EvalCase]) -> dict[str, Any]:
    """Local proxy metrics that mirror RAGAS intent without an LLM judge."""
    if not cases:
        return {"mode": "heuristic", "n_cases": 0, "metrics": {}}

    buckets: dict[str, list[float]] = {k: [] for k in _METRIC_KEYS}
    per_case: list[dict[str, Any]] = []

    for case in cases:
        faith = grounding_overlap(case.answer, case.contexts)
        if case.should_refuse and not case.contexts:
            lower = case.answer.lower()
            faith = (
                1.0
                if any(x in lower for x in ("insufficient", "does not provide", "no medical"))
                else 0.0
            )

        relevancy = max(
            answer_token_f1(case.answer, case.question),
            answer_token_f1(case.answer, case.reference_answer) * 0.85,
        )
        ctx_precision = precision_at_k(case.retrieved_ids, case.relevant_ids, k=5)
        if case.should_refuse and not case.relevant_ids:
            ctx_precision = 1.0
        ctx_recall = recall_at_k(case.retrieved_ids, case.relevant_ids, k=5)
        if not case.relevant_ids:
            ctx_recall = 1.0
        correctness = answer_token_f1(case.answer, case.reference_answer)

        scores = {
            "faithfulness": faith,
            "answer_relevancy": relevancy,
            "context_precision": ctx_precision,
            "context_recall": ctx_recall,
            "answer_correctness": correctness,
        }
        for k, v in scores.items():
            buckets[k].append(v)
        per_case.append({"id": case.id, **{k: round(v, 4) for k, v in scores.items()}})

    return {
        "mode": "heuristic",
        "n_cases": len(cases),
        "metrics": {k: _avg(v) for k, v in buckets.items()},
        "per_case": per_case,
        "note": "Heuristic RAGAS-like scores (no LLM judge).",
    }


def _judge_prompt(metric: str, case: EvalCase) -> tuple[str, str]:
    contexts = "\n---\n".join(case.contexts) if case.contexts else "(no context)"
    system = (
        "You are a strict RAG evaluator for a fictional pharma intake training system. "
        "Return ONLY JSON: {\"score\": <float 0 to 1>, \"reason\": \"short\"}. "
        "Never give medical or regulatory advice."
    )
    if metric == "faithfulness":
        user = (
            "Score faithfulness: is the answer supported by the contexts only?\n"
            f"Question: {case.question}\nAnswer: {case.answer}\nContexts:\n{contexts}\n"
            "1=fully grounded, 0=unsupported/hallucinated."
        )
    elif metric == "answer_relevancy":
        user = (
            "Score answer relevancy to the question (ignore style).\n"
            f"Question: {case.question}\nAnswer: {case.answer}\n"
            "1=directly addresses question, 0=off-topic."
        )
    elif metric == "context_precision":
        user = (
            "Score context precision: how relevant are the retrieved contexts to the question?\n"
            f"Question: {case.question}\nContexts:\n{contexts}\n"
            "1=all contexts useful, 0=none useful."
        )
    elif metric == "context_recall":
        user = (
            "Score context recall vs the ground-truth answer.\n"
            f"Question: {case.question}\nGround truth: {case.reference_answer}\n"
            f"Contexts:\n{contexts}\n"
            "1=contexts cover ground truth, 0=missing key facts."
        )
    else:  # answer_correctness
        user = (
            "Score answer correctness vs ground truth (semantic, not exact match).\n"
            f"Question: {case.question}\nAnswer: {case.answer}\n"
            f"Ground truth: {case.reference_answer}\n"
            "1=equivalent, 0=wrong/contradictory."
        )
    return system, user


def _run_llm_judge(cases: list[EvalCase]) -> dict[str, Any] | None:
    """RAGAS-style scoring via the project's configured LLM role."""
    try:
        from app.core.config import get_settings
        from app.core.container import get_container
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_llm_judge_import_failed", error=str(exc))
        return None

    settings = get_settings()
    # Prefer response/eval quality model; fall back to default
    cfg = settings.resolve_llm_role("response")
    if (cfg.get("provider") or "mock") == "mock" and settings.llm_provider == "mock":
        return None

    llm = get_container().llm_for("response")
    if getattr(llm, "name", "") == "mock":
        return None

    buckets: dict[str, list[float]] = {k: [] for k in _METRIC_KEYS}
    per_case: list[dict[str, Any]] = []

    for case in cases:
        row: dict[str, Any] = {"id": case.id}
        for metric in _METRIC_KEYS:
            # Prefer retrieval gold labels for precision/recall when available
            if metric == "context_precision" and (case.relevant_ids or case.should_refuse):
                score = precision_at_k(case.retrieved_ids, case.relevant_ids, k=5)
                if case.should_refuse and not case.relevant_ids:
                    score = 1.0
            elif metric == "context_recall" and (case.relevant_ids or not case.relevant_ids):
                score = recall_at_k(case.retrieved_ids, case.relevant_ids, k=5)
                if not case.relevant_ids:
                    score = 1.0
            else:
                system, user = _judge_prompt(metric, case)
                try:
                    raw = llm.generate(user, system=system).content
                    score = _extract_score(raw, default=0.0)
                    # Mock essay guard
                    if "context excerpt considered" in (raw or "").lower():
                        score = _heuristic_ragas_scores([case])["metrics"][metric]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ragas_metric_failed", metric=metric, case=case.id, error=str(exc))
                    score = _heuristic_ragas_scores([case])["metrics"][metric]
            buckets[metric].append(float(score))
            row[metric] = round(float(score), 4)
        per_case.append(row)

    return {
        "mode": "llm_judge_ragas_style",
        "n_cases": len(cases),
        "metrics": {k: _avg(v) for k, v in buckets.items()},
        "per_case": per_case,
        "judge_llm": {
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "role": "response",
        },
        "note": "Project-native RAGAS-style LLM judge (faithfulness/relevancy/correctness).",
    }


def _ensure_ragas_compat_shims() -> None:
    """ragas still imports optional langchain_community Vertex chat model."""
    import sys
    import types

    name = "langchain_community.chat_models.vertexai"
    if name in sys.modules:
        return
    try:
        __import__(name)
        return
    except Exception:
        pass
    mod = types.ModuleType(name)

    class ChatVertexAI:  # pragma: no cover - import compatibility only
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("ChatVertexAI stub is only for ragas import compatibility")

    mod.ChatVertexAI = ChatVertexAI
    sys.modules[name] = mod


def _run_ragas_library(cases: list[EvalCase]) -> dict[str, Any] | None:
    """Execute official RAGAS evaluate() when the package imports cleanly."""
    try:
        _ensure_ragas_compat_shims()
        from datasets import Dataset
        from ragas import evaluate

        try:
            from ragas.metrics.collections import (
                answer_correctness,
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
        except Exception:
            from ragas.metrics import (
                answer_correctness,
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_import_failed", error=str(exc))
        return None

    llm = None
    embeddings = None
    try:
        from app.core.config import get_settings

        settings = get_settings()
        cfg = settings.resolve_llm_role("response")
        provider = (cfg.get("provider") or settings.llm_provider or "mock").lower()
        model = cfg.get("model") or settings.llm_model_name
        api_key = cfg.get("api_key") or ""
        if provider == "mock" or not api_key:
            return None

        if provider in {"openai", "openrouter"}:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {
                "model": model or "gpt-4o-mini",
                "api_key": api_key,
                "temperature": 0,
            }
            if provider == "openrouter":
                kwargs["base_url"] = "https://openrouter.ai/api/v1"
            llm = ChatOpenAI(**kwargs)
        elif provider == "groq":
            from langchain_groq import ChatGroq

            llm = ChatGroq(model=model or "llama-3.1-8b-instant", api_key=api_key, temperature=0)
        else:
            return None

        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings

            embeddings = HuggingFaceEmbeddings(
                model_name=settings.embedding_model_name or "all-MiniLM-L6-v2"
            )
        except Exception as emb_exc:  # noqa: BLE001
            logger.warning("ragas_embeddings_unavailable", error=str(emb_exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_llm_setup_failed", error=str(exc))
        return None

    dataset = Dataset.from_dict(
        {
            "question": [c.question for c in cases],
            "answer": [c.answer for c in cases],
            "contexts": [c.contexts for c in cases],
            "ground_truth": [c.reference_answer for c in cases],
        }
    )
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness]
    try:
        kwargs: dict[str, Any] = {"metrics": metrics, "llm": llm}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        result = evaluate(dataset, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_evaluate_failed", error=str(exc))
        return None

    metrics_out: dict[str, float] = {}
    per_case: list[dict[str, Any]] = []
    try:
        if hasattr(result, "to_pandas"):
            df = result.to_pandas()
            for col in _METRIC_KEYS:
                if col in df.columns:
                    series = df[col].dropna()
                    metrics_out[col] = round(float(series.mean()), 4) if len(series) else 0.0
            for i, case in enumerate(cases):
                row: dict[str, Any] = {"id": case.id}
                for col in _METRIC_KEYS:
                    if col in df.columns and i < len(df):
                        val = df.iloc[i][col]
                        row[col] = None if val != val else round(float(val), 4)
                per_case.append(row)
        elif isinstance(result, dict):
            for k, v in result.items():
                try:
                    metrics_out[str(k)] = round(float(v), 4)
                except (TypeError, ValueError):
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_result_parse_failed", error=str(exc))
        return None

    if not metrics_out:
        return None

    return {
        "mode": "ragas",
        "n_cases": len(cases),
        "metrics": metrics_out,
        "per_case": per_case,
        "judge_llm": {"provider": provider, "model": model},
    }


def run_ragas_evaluation(
    cases: list[EvalCase] | None = None,
    *,
    force_heuristic: bool = False,
    prefer_llm_judge: bool = False,
) -> dict[str, Any]:
    """Run RAGAS / RAGAS-style evaluation with graceful fallbacks."""
    cases = cases or load_gold_cases()
    if force_heuristic:
        return _heuristic_ragas_scores(cases)

    if not prefer_llm_judge:
        ragas_result = _run_ragas_library(cases)
        if ragas_result is not None:
            return ragas_result

    judge_result = _run_llm_judge(cases)
    if judge_result is not None:
        return judge_result

    # If official ragas was skipped because prefer_llm_judge=True, try it now
    if prefer_llm_judge:
        ragas_result = _run_ragas_library(cases)
        if ragas_result is not None:
            return ragas_result

    return _heuristic_ragas_scores(cases)
