"""Prompt 3.7 security test: no party name, client name or TRN from the test data (or any
e-mail, phone, IBAN or Emirates ID) may reach any AI payload."""

from __future__ import annotations

import csv
import json
import socket
from collections.abc import Iterator
from typing import Any

import pytest

from app.services import ai_gateway, anonymiser
from tests.conftest import DATA

CLIENT_NAME, CLIENT_CODE = "Dummy Trading LLC", "DUMMY01"


def _csv(name: str) -> list[dict[str, Any]]:
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


ROWS = _csv("dummy_gl.csv") + _csv("edge_cases.csv") + _csv("fy2021_2022.csv")
REGISTER = _csv("supplier_register.csv")
SECRETS = sorted({v for r in ROWS + REGISTER for k in ("party_name", "trn") if (v := r.get(k))}
                 | {CLIENT_NAME})


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def _blocked(*a: Any, **k: Any) -> None:
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    yield


def _check(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    leaked = [s for s in SECRETS if s.lower() in blob]
    assert not leaked, f"identifying data reached the AI payload: {leaked[:3]}"


def test_test_data_has_secrets_to_protect() -> None:
    assert len(SECRETS) > 30 and any(len(s) == 15 and s.isdigit() for s in SECRETS)


def test_no_party_client_or_trn_in_any_payload() -> None:
    names = anonymiser.forbidden_terms(client_name=CLIENT_NAME, client_code=CLIENT_CODE,
                                       rows=ROWS, register=REGISTER)
    stub = ai_gateway.StubProvider()
    sent = 0
    for r in ROWS:
        if not (r.get("party_name") or r.get("trn")):
            continue
        # Worst case: the auditor pastes the narration, party, TRN and client into the remark.
        remark = (f"{r['narration']} | {r['party_name']} TRN {r['trn']} for {CLIENT_NAME}; "
                  "call +971 50 123 4567 or ap@example.ae, IBAN AE070331234567890123456, "
                  "EID 784-1985-1234567-1")
        p = anonymiser.build_payload(
            area=f"{r['account_type']} / {r['account_name']}", test="Vouching",
            item_ref=r["line_id"], amounts={"book_value": r["debit"] or r["credit"]},
            failed_attribute=f"Invoice {r['invoice_no']} not agreed to {r['party_name']}",
            applicable_references=[{"ref": "vat.rate.SR@v1", "citation": "Decree-Law 8/2017"}],
            auditor_remark=remark, names=names)
        _check(p)
        assert not any(pat.search(json.dumps(p)) for _, pat in anonymiser.PATTERNS)
        ai_gateway.draft_observation(p, stub)
        sent += 1
    assert sent > 100
    for user in stub.calls:  # what actually left the anonymiser
        _check(json.loads(user))


def test_patterns_alone_catch_trns_and_most_names() -> None:
    """Without the deny list, patterns still remove every TRN and suffixed / "Al ..." name.
    Names with neither (e.g. a utility authority) rely on the deny list (D21), which the API
    always builds from the ledger, the supplier register and the client record."""
    leaked = []
    for r in REGISTER:
        p = anonymiser.build_payload(
            area="Expense", test="t", item_ref="L1", amounts={},
            failed_attribute="f", applicable_references=[],
            auditor_remark=f"Supplier {r['party_name']} TRN {r['trn']}", names=[])
        blob = json.dumps(p)
        assert not r["trn"] or r["trn"] not in blob
        leaked += [r["party_name"]] if r["party_name"] in blob else []
    assert len(leaked) <= len(REGISTER) // 4, leaked


def test_assert_clean_blocks_leaks() -> None:
    with pytest.raises(anonymiser.AnonymisationError, match="Non-whitelisted"):
        anonymiser.assert_clean({"area": "x", "narration": "y"}, [])
    with pytest.raises(anonymiser.AnonymisationError, match="identifying"):
        anonymiser.assert_clean({"area": "Paid to Dummy Trading LLC"}, [CLIENT_NAME])
    with pytest.raises(anonymiser.AnonymisationError, match="identifying"):
        anonymiser.assert_clean({"area": "TRN 100286583490896"}, [])
