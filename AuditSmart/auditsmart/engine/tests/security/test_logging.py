from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import JsonFormatter, configure_logging, log_event, scrub

pytestmark = pytest.mark.security


def _format(record_kwargs: dict[str, object], msg: str = "x") -> dict[str, object]:
    rec = logging.LogRecord("auditsmart", logging.INFO, __file__, 1, msg, (), None)
    for k, v in record_kwargs.items():
        setattr(rec, k, v)
    return json.loads(JsonFormatter().format(rec))  # type: ignore[no-any-return]


def test_only_whitelisted_fields_emitted() -> None:
    out = _format({"dataset_id": "d1", "rows": 3, "party_name": "Al Futtaim", "narration": "x"})
    assert out["dataset_id"] == "d1" and out["rows"] == 3
    assert "party_name" not in out and "narration" not in out


def test_message_scrubbing() -> None:
    text = "TRN 100549222448546 mail a.b@client.ae IBAN AE070331234567890123456 ph +971 50 123 4567"
    s = scrub(text)
    for secret in ("100549222448546", "a.b@client.ae", "AE070331234567890123456", "123 4567"):
        assert secret not in s


def test_exception_message_not_logged() -> None:
    try:
        raise ValueError("party Al Futtaim TRN 100549222448546")
    except ValueError:
        import sys

        rec = logging.LogRecord("a", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    out = json.loads(JsonFormatter().format(rec))
    assert out["exc_type"] == "ValueError"
    assert "Futtaim" not in json.dumps(out)


def test_log_event_drops_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    log_event("dataset.parsed", dataset_id="d9", party_name="Secret Supplier LLC", rows=5)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "dataset.parsed" and data["rows"] == 5
    assert "Secret Supplier" not in line
