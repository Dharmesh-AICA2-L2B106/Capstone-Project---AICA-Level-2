"""D56: clear import errors - bad mappings are a synchronous 422 on every route, and a
parse job that fails stores the real reason instead of a generic ValueError."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import DATA, auth

DUMMY = (DATA / "dummy_gl.csv").read_bytes()
SIX = {"posting_date": "posting_date", "voucher_no": "voucher_no",
       "account_code": "account_code", "debit": "debit", "credit": "credit",
       "narration": "narration"}
LABELS = b"Ref,Posting Date,Voucher No,Account,Dr,Cr\n1,2025-01-05,J1,6100,10,0\n" \
         b"2,2025-01-05,J1,2010,0,10\n"


def _multipart(client: TestClient, tok: str, eng: str, data: bytes,
               override: Any = None, name: str = "gl.csv") -> Any:
    form = {"engagement_id": eng}
    if override is not None:
        form["mapping_override"] = override if isinstance(override, str) else json.dumps(
            override)
    return client.post("/v1/datasets", headers=auth(tok), data=form,
                       files={"file": (name, data)})


def _chunked(client: TestClient, tok: str, eng: str, data: bytes) -> str:
    r = client.post("/v1/uploads", headers=auth(tok),
                    json={"engagement_id": eng, "file_name": "gl.csv", "size_bytes": len(data)})
    sid: str = r.json()["dataset_id"]
    assert client.put(f"/v1/uploads/{sid}/chunks/0", headers=auth(tok),
                      content=data).status_code == 200
    return sid


def _job(client: TestClient, tok: str, job_id: str) -> dict[str, Any]:
    out: dict[str, Any] = client.get(f"/v1/jobs/{job_id}", headers=auth(tok)).json()
    return out


def test_dummy_gl_with_six_field_mapping_succeeds(client: TestClient,
                                                  token: Callable[..., str],
                                                  engagement: str) -> None:
    tok = token()
    r = _multipart(client, tok, engagement, DUMMY, SIX, name="dummy_gl.csv")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "parsed" and body["profile"]["rows"] == 3000
    assert body["mapping_suggestion"]["line_id"] == "line_id"  # still auto-matched
    assert _job(client, tok, body["job_id"])["status"] == "succeeded"
    did = body["dataset_id"]
    # the same mapping through the re-map route, as labels and reversed: same result
    for override in (SIX, {"Posting Date": "posting_date", "Voucher No": "voucher_no",
                           "Account Code": "account_code", "Dr": "debit", "Cr": "credit",
                           "Narration": "narration"},
                     {v: k for k, v in SIX.items()}):
        m = client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok),
                       json={"mapping_override": override})
        assert m.status_code == 202, m.text
        assert _job(client, tok, m.json()["job_id"])["status"] == "succeeded"
        ds = client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()
        assert ds["rows"] == 3000 and ds["mapping"]["posting_date"] == "posting_date"


def test_label_keys_on_upload(client: TestClient, token: Callable[..., str],
                              engagement: str) -> None:
    tok = token()
    r = _multipart(client, tok, engagement, LABELS,
                   {"line_id": "Ref", "Posting Date": "Posting Date", "voucher": "Voucher No"})
    assert r.status_code == 202, r.text
    m = r.json()["mapping_suggestion"]
    assert m["line_id"] == "Ref" and m["posting_date"] == "Posting Date"
    assert m["voucher_no"] == "Voucher No" and m["debit"] == "Dr"


def test_put_mapping_prevalidates(client: TestClient, token: Callable[..., str],
                                  engagement: str) -> None:
    tok = token()
    did = _multipart(client, tok, engagement, LABELS).json()["dataset_id"]
    before = client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()
    jobs_before = client.get("/v1/jobs", headers=auth(tok),
                             params={"engagement_id": engagement}).json()
    bad = client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok),
                     json={"mapping_override": {"Posting Dt": "Posting Date", "zzz": "Ref"}})
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert detail.startswith("Mapping problem: Unknown fields 'Posting Dt', 'zzz' in the "
                             "mapping. Allowed fields: line_id, entry_date, posting_date")
    missing = client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok),
                         json={"mapping_override": {"posting_date": "Txn Date"}})
    assert missing.status_code == 422
    assert ("Column 'Txn Date' (mapped to posting_date) is not in the file. Columns in the "
            "file: Ref, Posting Date, Voucher No, Account, Dr, Cr.") in missing.json()["detail"]
    typed = client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok),
                       json={"mapping_override": {"debit": 4}})
    assert typed.status_code == 422 and isinstance(typed.json()["detail"], str)
    assert "The value for 'debit' must be a column header (text)" in typed.json()["detail"]
    assert client.put(f"/v1/datasets/{did}/mapping", headers=auth(tok),
                      json={"mapping_override": ["x"]}).status_code == 422  # schema
    # nothing was queued and the dataset kept its status and mapping
    after = client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()
    assert after["status"] == before["status"] and after["mapping"] == before["mapping"]
    assert client.get("/v1/jobs", headers=auth(tok),
                      params={"engagement_id": engagement}).json() == jobs_before


def test_multipart_bad_mapping_422(client: TestClient, token: Callable[..., str],
                                   engagement: str) -> None:
    tok = token()
    r = _multipart(client, tok, engagement, LABELS, {"debit": ["Dr"]})
    assert r.status_code == 422 and "got a list" in r.json()["detail"]
    r2 = _multipart(client, tok, engagement, LABELS, "[1]")
    assert r2.status_code == 422 and "must be a JSON object" in r2.json()["detail"]
    r3 = _multipart(client, tok, engagement, LABELS, {"Dr Amt": "Dr"})
    assert r3.status_code == 422 and "Unknown field 'Dr Amt'" in r3.json()["detail"]


def test_chunked_complete_prevalidates_and_can_retry(client: TestClient,
                                                     token: Callable[..., str],
                                                     engagement: str) -> None:
    tok = token()
    sid = _chunked(client, tok, engagement, LABELS)
    bad = client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok),
                      json={"mapping_override": {"line_id": "Row"}})
    assert bad.status_code == 422 and "Column 'Row'" in bad.json()["detail"]
    typed = client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok),
                        json={"mapping_override": {"line_id": 1}})
    assert typed.status_code == 422 and "got a number" in typed.json()["detail"]
    ok = client.post(f"/v1/uploads/{sid}/complete", headers=auth(tok),
                     json={"mapping_override": {"Ref": "line_id"}})  # reversed
    assert ok.status_code == 202, ok.text
    assert ok.json()["status"] == "parsed" and ok.json()["mapping_suggestion"]["line_id"] == "Ref"


def test_parse_job_failure_message_is_the_real_reason(client: TestClient,
                                                      token: Callable[..., str],
                                                      engagement: str) -> None:
    from app.services import datasets, jobs

    tok = token()
    did = _multipart(client, tok, engagement, LABELS).json()["dataset_id"]
    # an old-style queued job (raw label keys, e.g. from before 0.2.2) now says why it failed
    jid = jobs.enqueue("parse", {"dataset_id": did,
                                 "mapping_override": {"Posting Dt": "Posting Date"}},
                       engagement_id=engagement, created_by="user-1")
    job = _job(client, tok, jid)
    assert job["status"] == "failed"
    assert job["error"].startswith("Mapping problem: Unknown field 'Posting Dt' in the "
                                   "mapping. Allowed fields: line_id, entry_date,")
    assert "the job failed" not in job["error"]
    assert client.get(f"/v1/datasets/{did}", headers=auth(tok)).json()["status"] == "failed"

    # a file that is not UTF-8: refused at upload when the first block is unreadable ...
    head = b"line_id,posting_date,voucher_no,account_code,debit,credit,narration\n"
    small = _multipart(client, tok, engagement, head + b"1,2025-01-05,J1,6100,10,0,Caf\xe9\n")
    assert small.status_code == 422
    assert small.json()["detail"].startswith("The file is not UTF-8 text (a character near "
                                             "byte ")
    # ... and when the bad byte comes later, the parse job says so
    rows = b"".join(b"%d,2025-01-05,J1,6100,10,0,ok\n" % i for i in range(1, 2000))
    r = _multipart(client, tok, engagement, head + rows + b"2000,2025-01-05,J1,6100,10,0,"
                   b"Caf\xe9\n")
    assert r.status_code == 202 and r.json()["status"] == "failed"
    err = _job(client, tok, r.json()["job_id"])["error"]
    assert err.startswith("The file is not UTF-8 text") and "CSV UTF-8" in err
    assert "Traceback" not in err and "codec" not in err

    assert jobs.job_error_text(ValueError("x")) == (
        "ValueError: the job failed. Check the file and try again.")
    assert jobs.job_error_text(datasets.DatasetError("plain words")) == "plain words"

    class Shown(ValueError):
        user_facing = True

    assert jobs.job_error_text(Shown("our own reason")) == "our own reason"


def test_read_error_texts() -> None:
    import csv
    import zipfile

    from app.services.datasets import _read_error
    from app.services.importer import MappingError

    assert _read_error(MappingError("m")) == "m"
    assert _read_error(csv.Error("field larger than field limit")) == (
        "The CSV file could not be read (field larger than field limit). Check the quotes "
        "and separators.")
    assert _read_error(zipfile.BadZipFile("bad")).startswith("The Excel file could not be")
    assert _read_error(ValueError("line one\nline two")) == (
        "The file could not be read: line one.")
    assert _read_error(ValueError("")) == "The file could not be read: ValueError."
    assert _read_error(OSError("disk")) == (
        "OSError: the file could not be read. Check the file and try again.")
