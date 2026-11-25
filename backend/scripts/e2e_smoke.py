"""Quick production-readiness smoke against a running local API + UI."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

BASE = "http://127.0.0.1:8000/api/v1"
failures: list[str] = []


def req(method: str, path: str, token: str | None = None, data=None, form: bool = False):
    headers: dict[str, str] = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None and form:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name} {detail}")
        failures.append(name)


def login(username: str, password: str) -> str | None:
    for path, form in (("/auth/token", True), ("/auth/login", True), ("/auth/login", False)):
        code, payload = req(
            "POST",
            path,
            form=form,
            data={"username": username, "password": password},
        )
        if code == 200 and payload.get("access_token"):
            return payload["access_token"]
    print(f"login failed for {username}: {code} {payload}")
    return None


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=30) as resp:
            check("docs", resp.status == 200)
    except Exception as exc:
        check("docs", False, str(exc))

    op = login("operator", "Operator@123")
    check("operator_login", bool(op))
    rv = login("reviewer", "Reviewer@123")
    check("reviewer_login", bool(rv))
    ap = login("approver", "Approver@123")
    check("approver_login", bool(ap))
    ad = login("admin", "Admin@123")
    check("admin_login", bool(ad))
    if not all([op, rv, ap, ad]):
        print("FAILURES=", len(failures))
        return 1

    code, err = req(
        "POST",
        "/reports",
        token=op,
        data={
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-1111",
            "date_received": str(date.today()),
            "reporter_type": "Consumer",
            "description": "bad lot smoke",
        },
    )
    check("lot_validation_400", code in (400, 422), f"{code} {err}")

    code, report = req(
        "POST",
        "/reports",
        token=op,
        data={
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-88392",
            "date_received": str(date.today()),
            "reporter_type": "Consumer",
            "description": "Bottle seal broken on arrival (fictional training).",
        },
    )
    check("create_pqc", code == 200 and report.get("status") == "New", f"{code} {report}")
    ref = report.get("reference_id")

    code, denied = req(
        "POST",
        f"/reports/{ref}/status",
        token=op,
        data={"new_status": "In Review"},
    )
    check("operator_cannot_triage", code in (401, 403), f"{code} {denied}")

    code, mid = req(
        "POST",
        f"/reports/{ref}/status",
        token=rv,
        data={"new_status": "In Review", "reviewer_notes": "Initial triage"},
    )
    check("start_review", code == 200 and mid.get("status") == "In Review", f"{code} {mid}")

    code, pending = req(
        "POST",
        f"/reports/{ref}/status",
        token=rv,
        data={
            "new_status": "Closed",
            "reviewer_notes": "Lot verified; packaging photos reviewed; recommend close",
        },
    )
    check(
        "request_close",
        code == 200 and pending.get("pending_close") is True,
        f"{code} {pending}",
    )

    code, closed = req(
        "POST",
        f"/reports/{ref}/approve-close",
        token=ap,
        data={"confirm": True, "comment": "Looks complete"},
    )
    check("approve_close", code == 200 and closed.get("status") == "Closed", f"{code} {closed}")

    code, cfg_denied = req("PUT", "/agent/config", token=op, data={"tool_backend": "local"})
    check("operator_cannot_set_agent_config", code in (401, 403), f"{code} {cfg_denied}")
    code, cfg_ok = req("PUT", "/agent/config", token=ad, data={"tool_backend": "local"})
    check(
        "admin_can_set_agent_config",
        code == 200 and cfg_ok.get("tool_backend") == "local",
        f"{code} {cfg_ok}",
    )

    code, rows = req("GET", "/reports?status=Closed", token=ap)
    check("list_closed", code == 200 and isinstance(rows, list), f"{code}")

    try:
        with urllib.request.urlopen("http://127.0.0.1:5173/", timeout=30) as resp:
            html = resp.read().decode()
            check(
                "frontend_index",
                resp.status == 200 and ("root" in html or "NovaCure" in html),
                html[:120],
            )
    except Exception as exc:
        check("frontend_index", False, str(exc))

    print("\nREF=", ref)
    print("FAILURES=", len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
