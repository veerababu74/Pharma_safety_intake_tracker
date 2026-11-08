"""Locust load file for the local Pharma Safety Intake API.

Start the API first, then from backend/:

    locust --host http://127.0.0.1:8000
    # UI: http://127.0.0.1:8089

Headless reads only (no writes, no LLM):

    locust --headless -u 5 -r 1 -t 30s --tags read --host http://127.0.0.1:8000

Reads plus intake creates:

    locust --headless -u 5 -r 1 -t 30s --tags read write --host http://127.0.0.1:8000

Add a few Knowledge Query calls (uses the configured LLM):

    locust --headless -u 5 -r 1 -t 60s --tags read write rag --host http://127.0.0.1:8000

CSV report:

    locust --headless -u 5 -r 1 -t 30s --tags read --host http://127.0.0.1:8000 --csv evaluation/locust

Overlapping intake creates can fail with UNIQUE constraint on reports.reference_id
because REF ids are allocated as max+1. RAG tasks call the configured LLM.
"""

from __future__ import annotations

import itertools
import os
import threading
import uuid

from locust import HttpUser, between, tag, task

_lot_lock = threading.Lock()
_lot_seq = itertools.count(94000)

_RAG_QUESTIONS = (
    "What should we do for a packaging complaint on LOT-88392?",
    "Which references are In Review right now?",
    "What lot pattern does intake validation require?",
    "How soon must a packaging complaint lot be quarantined, and who is notified?",
)


def _next_lot() -> str:
    with _lot_lock:
        return f"LOT-{next(_lot_seq)}"


class PharmaIntakeUser(HttpUser):
    """One user class so --tags read does not spawn an empty RAG user."""

    host = "http://127.0.0.1:8000"
    wait_time = between(0.4, 1.2)

    def on_start(self) -> None:
        username = os.environ.get("LOCUST_USERNAME", "reviewer")
        password = os.environ.get("LOCUST_PASSWORD", "Reviewer@123")
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            name="POST /auth/login",
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"
        self._questions = itertools.cycle(_RAG_QUESTIONS)

    @tag("read")
    @task(6)
    def health(self) -> None:
        self.client.get("/api/v1/system/health", name="GET /system/health")

    @tag("read")
    @task(5)
    def list_reports(self) -> None:
        self.client.get("/api/v1/reports", name="GET /reports")

    @tag("read")
    @task(3)
    def get_report(self) -> None:
        self.client.get("/api/v1/reports/REF-2026-0001", name="GET /reports/{ref}")

    @tag("write")
    @task(1)
    def create_report(self) -> None:
        self.client.post(
            "/api/v1/reports",
            json={
                "report_type": "Product Quality Complaint",
                "product_name": "NeuroCalm 50mg",
                "batch_lot_number": _next_lot(),
                "date_received": "2026-11-06",
                "reporter_type": "Consumer",
                "description": f"Locust fictional seal check {uuid.uuid4().hex[:8]}.",
            },
            name="POST /reports",
        )

    @tag("rag")
    @task(1)
    def rag_query(self) -> None:
        self.client.post(
            "/api/v1/rag/query",
            json={"question": next(self._questions), "top_n": 3},
            name="POST /rag/query",
        )
