"""5-step agent control plane: router, validation, memory, HITL, circuit breaker."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.container import get_container
from app.services.report_service import ReportService

LOT_RE = re.compile(r"^LOT-\d{5}$")


class SubmitIntakeArgs(BaseModel):
    report_type: str
    product_name: str
    batch_lot_number: str
    date_received: str
    reporter_type: str
    description: str
    event_description: str | None = None
    event_onset_date: str | None = None

    @field_validator("batch_lot_number")
    @classmethod
    def validate_lot(cls, v: str) -> str:
        if not LOT_RE.match(v):
            raise ValueError("batch_lot_number must match LOT-#####")
        return v


class UpdateStatusArgs(BaseModel):
    reference_id: str
    new_status: str


@dataclass
class CircuitBreaker:
    limit: int = 2
    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def key(self, tool: str, signature: str) -> str:
        return f"{tool}::{signature}"

    def record_failure(self, tool: str, signature: str) -> bool:
        k = self.key(tool, signature)
        self._counts[k] += 1
        return self._counts[k] > self.limit

    def reset(self, tool: str, signature: str) -> None:
        self._counts.pop(self.key(tool, signature), None)


@dataclass
class ShortTermMemory:
    traces: list[dict[str, Any]] = field(default_factory=list)

    def add(self, thought: str, action: str, observation: str) -> None:
        self.traces.append({"thought": thought, "action": action, "observation": observation})


class AgentOrchestrator:
    def __init__(self) -> None:
        self.breaker = CircuitBreaker()
        self.memory = ShortTermMemory()
        self.reports = ReportService()

    def route(self, message: str) -> str:
        text = message.lower().strip()
        if text in {"hi", "hello", "hey"} or text.startswith("hello"):
            return "direct"
        if any(k in text for k in ["status", "close", "in review", "approve"]):
            return "status"
        if any(k in text for k in ["create", "submit", "complaint", "adverse", "intake"]):
            return "intake"
        if any(k in text for k in ["sop", "quarantine", "lot-", "what should", "guidance", "policy"]):
            return "rag"
        return "rag"

    def handle(self, message: str, actor: str, role: str, tool_args: dict[str, Any] | None = None) -> dict[str, Any]:
        intent = self.route(message)
        self.memory.add("classify intent", intent, "routed")

        if intent == "direct":
            return {
                "intent": intent,
                "response": "Hello! I can help with intake, status triage, or SOP/history lookup (training only).",
            }

        if intent == "rag":
            container = get_container()
            result = container.rag.query(message, actor=actor, role=role)
            self.memory.add("rag", "hybrid_rag_query", result["answer"][:200])
            return {"intent": intent, "response": result["answer"], "rag": result}

        if intent == "intake":
            args = tool_args or {}
            signature = str(sorted(args.items()))
            try:
                validated = SubmitIntakeArgs(**args)
            except ValidationError as exc:
                tripped = self.breaker.record_failure("submit_intake_report", signature)
                if tripped:
                    return {
                        "intent": intent,
                        "error": "Circuit breaker open: repeated invalid submit_intake_report args",
                        "halted": True,
                        "details": exc.errors(),
                    }
                return {"intent": intent, "error": "validation_failed", "details": exc.errors(), "halted": False}
            self.breaker.reset("submit_intake_report", signature)
            created = self.reports.create(validated.model_dump(), actor=actor, role=role)
            self.memory.add("intake", "submit_intake_report", created["reference_id"])
            return {"intent": intent, "response": f"Created {created['reference_id']}", "report": created}

        if intent == "status":
            args = tool_args or {}
            signature = str(sorted(args.items()))
            try:
                validated = UpdateStatusArgs(**args)
            except ValidationError as exc:
                tripped = self.breaker.record_failure("update_status", signature)
                if tripped:
                    return {
                        "intent": intent,
                        "error": "Circuit breaker open: repeated invalid update_status args",
                        "halted": True,
                        "details": exc.errors(),
                    }
                return {"intent": intent, "error": "validation_failed", "details": exc.errors()}
            result = self.reports.request_status(
                validated.reference_id, validated.new_status, actor=actor, role=role
            )
            msg = (
                f"{validated.reference_id} pending HITL close approval"
                if result.get("pending_close")
                else f"{validated.reference_id} -> {result['status']}"
            )
            self.memory.add("status", "update_status", msg)
            return {"intent": intent, "response": msg, "report": result}

        return {"intent": "unknown", "response": "Unable to route request."}
