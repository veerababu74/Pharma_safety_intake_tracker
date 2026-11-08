"""Modest local load probe for the training API.

Not a production capacity test. One uvicorn worker and SQLite will serialize
writes. RAG calls also rebuild the BM25 index and may call the configured LLM,
so that scenario stays small on purpose.

    cd backend
    python -m evaluation.run_load
    python -m evaluation.run_load --skip-rag
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parent


@dataclass
class Sample:
    name: str
    status: int
    elapsed_ms: float
    ok: bool
    error: str | None = None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _request(
    client: httpx.Client,
    name: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    ok_status: set[int] | None = None,
) -> Sample:
    allowed = ok_status or {200, 201}
    started = time.perf_counter()
    try:
        response = client.request(method, url, headers=headers, json=json_body)
        elapsed = (time.perf_counter() - started) * 1000
        ok = response.status_code in allowed
        err = None if ok else response.text[:240]
        return Sample(name, response.status_code, elapsed, ok, err)
    except Exception as exc:  # noqa: BLE001 — record transport failures as samples
        elapsed = (time.perf_counter() - started) * 1000
        return Sample(name, 0, elapsed, False, f"{type(exc).__name__}: {exc}")


def _run_pool(name: str, count: int, workers: int, call: Callable[[int], Sample]) -> list[Sample]:
    samples: list[Sample] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(call, i) for i in range(count)]
        for future in as_completed(futures):
            sample = future.result()
            sample.name = name
            samples.append(sample)
    return samples


def summarize(name: str, samples: list[Sample], started: float, finished: float) -> dict[str, Any]:
    latencies = [s.elapsed_ms for s in samples]
    errors = [s for s in samples if not s.ok]
    wall = max(finished - started, 1e-9)
    return {
        "scenario": name,
        "requests": len(samples),
        "ok": len(samples) - len(errors),
        "errors": len(errors),
        "error_rate": round(len(errors) / len(samples), 4) if samples else 0.0,
        "wall_seconds": round(wall, 3),
        "throughput_rps": round(len(samples) / wall, 2) if samples else 0.0,
        "latency_ms": {
            "min": round(min(latencies), 1) if latencies else 0.0,
            "p50": round(percentile(latencies, 50), 1),
            "p95": round(percentile(latencies, 95), 1),
            "max": round(max(latencies), 1) if latencies else 0.0,
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        },
        "status_counts": _status_counts(samples),
        "sample_errors": [s.error for s in errors[:3] if s.error],
    }


def _status_counts(samples: list[Sample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status)
        counts[key] = counts.get(key, 0) + 1
    return counts


def login(client: httpx.Client, base: str, username: str, password: str) -> str:
    response = client.post(
        f"{base}/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def run_load(
    *,
    base_url: str,
    username: str,
    password: str,
    skip_rag: bool,
    intake_count: int,
    rag_count: int,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    scenarios: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        health = client.get(f"{base}/system/health")
        health.raise_for_status()
        token = login(client, base, username, password)
        headers = {"Authorization": f"Bearer {token}"}

        def health_call(_: int) -> Sample:
            return _request(client, "health", "GET", f"{base}/system/health")

        def list_call(_: int) -> Sample:
            return _request(client, "list_reports", "GET", f"{base}/reports", headers=headers)

        def create_call(i: int) -> Sample:
            lot = f"LOT-{93000 + i}"
            body = {
                "report_type": "Product Quality Complaint",
                "product_name": "NeuroCalm 50mg",
                "batch_lot_number": lot,
                "date_received": "2026-11-06",
                "reporter_type": "Consumer",
                "description": f"Load-test fictional seal check {uuid.uuid4().hex[:8]}.",
            }
            return _request(client, "create_report", "POST", f"{base}/reports", headers=headers, json_body=body)

        started = time.perf_counter()
        health_samples = _run_pool("health", 40, 10, health_call)
        scenarios.append(summarize("health", health_samples, started, time.perf_counter()))

        started = time.perf_counter()
        list_samples = _run_pool("list_reports", 30, 6, list_call)
        scenarios.append(summarize("list_reports", list_samples, started, time.perf_counter()))

        started = time.perf_counter()
        create_samples = _run_pool("create_report", intake_count, 3, create_call)
        scenarios.append(summarize("create_report", create_samples, started, time.perf_counter()))

        started = time.perf_counter()
        get_samples = _run_pool("get_report", 15, 5, lambda _: _request(
            client, "get_report", "GET", f"{base}/reports/REF-2026-0001", headers=headers, ok_status={200, 404}
        ))
        scenarios.append(summarize("get_report", get_samples, started, time.perf_counter()))

        if not skip_rag:
            questions = [
                "What should we do for a packaging complaint on LOT-88392?",
                "Which references are In Review right now?",
                "What lot pattern does intake validation require?",
                "How soon must a packaging complaint lot be quarantined, and who is notified?",
            ]

            def rag_call(i: int) -> Sample:
                body = {"question": questions[i % len(questions)], "top_n": 3}
                return _request(client, "rag_query", "POST", f"{base}/rag/query", headers=headers, json_body=body)

            started = time.perf_counter()
            rag_samples = _run_pool("rag_query", rag_count, 1, rag_call)
            scenarios.append(summarize("rag_query", rag_samples, started, time.perf_counter()))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": base,
        "profile": {
            "username": username,
            "workers_note": "Single local API process. SQLite writes are serialized.",
            "intake_count": intake_count,
            "rag_count": 0 if skip_rag else rag_count,
            "skip_rag": skip_rag,
            "disclaimer": (
                "Training-machine probe only. Do not treat these numbers as production capacity. "
                "RAG latency includes retrieval plus the configured LLM."
            ),
        },
        "scenarios": scenarios,
    }


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Local load probe for the Pharma intake API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--username", default="reviewer")
    parser.add_argument("--password", default="Reviewer@123")
    parser.add_argument("--intake-count", type=int, default=15)
    parser.add_argument("--rag-count", type=int, default=4)
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "last_load_report.json"))
    args = parser.parse_args(argv)

    report = run_load(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        skip_rag=args.skip_rag,
        intake_count=args.intake_count,
        rag_count=args.rag_count,
    )
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return report


if __name__ == "__main__":
    main()
