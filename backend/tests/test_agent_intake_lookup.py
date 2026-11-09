"""Regression: NL intake create, LOT validation, and lot-based lookup."""

from __future__ import annotations

import re

import pytest

from app.db.session import db_manager
from app.modules.agents.graph import (
    _is_intake_create_request,
    _is_lot_lookup_request,
    _parse_intake_from_message,
    _rule_route,
    _soft_message,
    intake_node,
    lookup_node,
    router_node,
)
from app.services.report_service import ReportService


def setup_module():
    db_manager.init()


def test_unicode_dash_lot_normalizes():
    soft = _soft_message("give me the LOT\u20111111 details")
    assert "lot-1111" in soft
    assert _is_lot_lookup_request(soft)


@pytest.mark.parametrize(
    "message,intent",
    [
        (
            "create a product quality complaint for AllergyClear 5mg LOT-33018 "
            "loose desiccant found inside bottle. Reporter Consumer. Date received 2026-11-04.",
            "intake",
        ),
        (
            "create a product quality complaint for novacurve relaxation cream LOT-1111 "
            "loose desiccant found inside bottle. Reporter Consumer. Date received today.",
            "intake",
        ),
        ("give me the lot-1111 details", "lookup"),
        ("LOT-1111", "lookup"),
        ("What should we do for packaging complaint LOT-88392?", "rag"),
        ("File a product quality complaint for NeuroCalm 50mg LOT-88392 — bottle seal broken", "intake"),
    ],
)
def test_rule_route_intake_vs_lookup_vs_rag(message: str, intent: str):
    assert _rule_route(message) == intent


@pytest.mark.parametrize(
    "message,intent",
    [
        (
            "create a product quality complaint for AllergyClear 5mg LOT-33018 "
            "loose desiccant. Reporter Consumer. Date received 2026-11-04.",
            "intake",
        ),
        ("give me the LOT-33018 details", "lookup"),
        ("What should we do for packaging complaint LOT-88392?", "rag"),
    ],
)
def test_router_node_rules_safe_overrides(message: str, intent: str):
    out = router_node(
        {
            "message": message,
            "actor": "operator",
            "role": "operator",
            "chat_history": [],
        }
    )
    assert out["intent"] == intent
    assert out["route_meta"]["router_source"] == "rules_safe"


def test_parse_intake_pqc_prose():
    args = _parse_intake_from_message(
        "create a product quality complaint for AllergyClear 5mg LOT-33018 "
        "loose desiccant found inside bottle. Reporter Consumer. Date received 2026-11-04."
    )
    assert args is not None
    assert args["report_type"] == "Product Quality Complaint"
    assert args["product_name"] == "AllergyClear 5mg"
    assert args["batch_lot_number"] == "LOT-33018"
    assert args["reporter_type"] == "Consumer"
    assert args["date_received"] == "2026-11-04"
    assert "desiccant" in args["description"].lower()


def test_parse_intake_invalid_four_digit_lot():
    args = _parse_intake_from_message(
        "create a product quality complaint for novacurve relaxation cream LOT-1111 "
        "loose desiccant found inside bottle. Reporter Consumer. Date received today."
    )
    assert args is not None
    assert args["batch_lot_number"] == "LOT-1111"
    assert args["product_name"].lower() == "novacurve relaxation cream"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", args["date_received"])


def test_intake_rejects_four_digit_lot_without_inventing_ref():
    out = intake_node(
        {
            "message": (
                "create a product quality complaint for novacurve relaxation cream LOT-1111 "
                "loose desiccant found inside bottle. Reporter Consumer. Date received 2026-11-09."
            ),
            "actor": "operator",
            "role": "operator",
            "tool_args": {},
            "chat_history": [],
        }
    )
    text = (out.get("response") or "").lower()
    assert out.get("details", {}).get("errors")
    assert "not created" in text or "invalid" in text
    assert "ref-" not in text
    assert "lot-#####" in text or "5 digits" in text


def test_intake_creates_valid_pqc_from_prose():
    out = intake_node(
        {
            "message": (
                "create a product quality complaint for AllergyClear 5mg LOT-33018 "
                "loose desiccant found inside bottle. Reporter Consumer. Date received 2026-11-04."
            ),
            "actor": "operator",
            "role": "operator",
            "tool_args": {},
            "chat_history": [],
        }
    )
    report = out.get("details", {}).get("report") or {}
    assert report.get("reference_id", "").startswith("REF-")
    assert report.get("batch_lot_number") == "LOT-33018"
    assert report.get("status") == "New"
    assert report["reference_id"] in (out.get("response") or "")


def test_lookup_by_lot_returns_created_report():
    created = ReportService().create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "Novacurve Relaxation Cream",
            "batch_lot_number": "LOT-01111",
            "date_received": "2026-11-09",
            "reporter_type": "Consumer",
            "description": "Loose desiccant found inside bottle",
        },
        actor="operator",
        role="operator",
    )
    out = lookup_node(
        {
            "message": "give me the LOT-01111 details",
            "actor": "operator",
            "role": "operator",
            "chat_history": [],
        }
    )
    report = out.get("details", {}).get("report") or {}
    assert report.get("reference_id") == created["reference_id"]
    assert created["reference_id"] in (out.get("response") or "")


def test_lookup_invalid_lot_explains_format():
    out = lookup_node(
        {
            "message": "LOT-1111",
            "actor": "operator",
            "role": "operator",
            "chat_history": [],
        }
    )
    text = (out.get("response") or "").lower()
    assert "no report" in text or "no product" in text or "not found" in text or "no reports" in text
    assert "5 digits" in text or "lot-#####" in text


def test_helpers_intake_and_lot_lookup():
    assert _is_intake_create_request(_soft_message("create a product quality complaint for X"))
    assert _is_lot_lookup_request(_soft_message("give me the lot-1111 details"))
    assert not _is_lot_lookup_request(
        _soft_message("What should we do for packaging complaint LOT-88392?")
    )
