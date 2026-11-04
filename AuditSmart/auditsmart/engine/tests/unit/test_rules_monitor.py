"""FTA rules monitor (prompt 3.9).  Saved fixtures only; no network."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.models import AuditLog, RuleVersion, UpdateAlert, WatchedSource
from app.services import rule_proposals
from app.services import rules_monitor as mon

ROOT = Path(__file__).resolve().parents[3]
S2 = ROOT / "prompts" / "stage2_tests"
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "fta_monitor"
HTML = (S2 / "fta_unrelated_source.html").read_bytes()
D17_PDF = (S2 / "FTA_Decision_17_of_2026.pdf").read_bytes()
D13_PDF = (S2 / "FTA_Decision_13_of_2026.pdf").read_bytes()
D17_OUT = (FIX / "decision17_extraction.json").read_text()
NO_CHANGE_OUT = (FIX / "unrelated_extraction.json").read_text()
D17_URL = (S2 / "fta_decision17_excerpt.txt").read_text().splitlines()[0].strip()
NEWS_URL = "https://tax.gov.ae/en/media.centre/news.aspx"


class FakeFetcher:
    def __init__(self, pages: dict[str, mon.Response | Exception]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str) -> mon.Response:
        self.calls.append(url)
        r = self.pages[url]
        if isinstance(r, Exception):
            raise r
        return r


def html(body: bytes = HTML) -> mon.Response:
    return mon.Response(200, "text/html; charset=utf-8", body)


def pdf(body: bytes = D17_PDF) -> mon.Response:
    return mon.Response(200, "application/pdf", body)


def fixed(text: str) -> mon.Extractor:
    def ext(user: str) -> str:
        assert user.startswith("current_rules: ")
        return text
    return ext


def _src(s: Any, url: str, type_: str = "html") -> WatchedSource:
    src = WatchedSource(url=url, type=type_, active=True, name="test source")
    s.add(src)
    s.flush()
    return src


# ------------------------------------------------------------------ text
def test_html_text_and_links() -> None:
    doc = mon.html_document(HTML, NEWS_URL)
    assert "Zero Government" in doc.text
    assert "<script" not in doc.text and "function(" not in doc.text
    assert "https://tax.gov.ae/en/legislation.aspx" in doc.links
    assert all(link.startswith("https://tax.gov.ae/") for link in doc.links)
    assert all("#" not in link for link in doc.links)
    assert len(doc.sha256) == 64


def test_pdf_and_text_documents() -> None:
    d17 = mon.to_document(D17_PDF, "application/octet-stream", D17_URL)
    assert d17.kind == "pdf" and "17 of 2026" in d17.text
    d13 = mon.pdf_document(D13_PDF)
    assert "13 of 2026" in d13.text and d13.sha256 != d17.sha256
    txt = mon.to_document(b"  plain   text \n\n line ", "text/plain", "https://x.example/")
    assert txt.kind == "text" and txt.text == "plain text\nline"
    with pytest.raises(mon.MonitorError, match="Could not read the PDF"):
        mon.pdf_document(b"%PDF-1.4 broken")


# --------------------------------------------------------------- fetcher
class Transport:
    def __init__(self, robots: mon.Response, page: mon.Response) -> None:
        self.robots, self.page = robots, page
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> mon.Response:
        self.calls.append((url, headers, timeout))
        return self.robots if url.endswith("/robots.txt") else self.page


def test_polite_fetcher_robots_ua_rate_limit_timeout() -> None:
    t = Transport(mon.Response(200, "text/plain", b"User-agent: *\nDisallow: /private/\n"),
                  html())
    now = [100.0]
    slept: list[float] = []

    def sleep(sec: float) -> None:
        slept.append(sec)
        now[0] += sec

    f = mon.PoliteFetcher(transport=t, clock=lambda: now[0], sleep=sleep)
    assert f.fetch(NEWS_URL).status == 200
    assert f.fetch("https://tax.gov.ae/en/legislation.aspx").status == 200
    urls = [c[0] for c in t.calls]
    assert urls.count("https://tax.gov.ae/robots.txt") == 1  # cached
    assert all(c[1]["User-Agent"].startswith("AuditSmart-RulesMonitor/") for c in t.calls)
    assert all(c[2] == mon.TIMEOUT_S for c in t.calls)
    assert all("Cookie" not in c[1] and "Authorization" not in c[1] for c in t.calls)
    assert len(slept) == 2 and all(abs(x - mon.MIN_INTERVAL_S) < 1e-9 for x in slept)
    with pytest.raises(mon.MonitorError, match=r"robots\.txt disallows"):
        f.fetch("https://tax.gov.ae/private/x.aspx")
    with pytest.raises(mon.MonitorError, match="Only https"):
        f.fetch("http://tax.gov.ae/en/legislation.aspx")


@pytest.mark.parametrize(("robots", "page", "err"), [
    (mon.Response(404, "", b""), mon.Response(404, "", b""), "HTTP 404"),
    (mon.Response(403, "", b""), html(), "robots.txt disallows"),
    (mon.Response(404, "", b""), mon.Response(200, "text/html", b"x" * (mon.MAX_BYTES + 1)),
     "larger than"),
])
def test_polite_fetcher_errors(robots: mon.Response, page: mon.Response, err: str) -> None:
    f = mon.PoliteFetcher(transport=Transport(robots, page), min_interval=0)
    with pytest.raises(mon.MonitorError, match=err):
        f.fetch(NEWS_URL)


def test_missing_robots_allows() -> None:
    f = mon.PoliteFetcher(transport=Transport(mon.Response(404, "", b""), html()),
                          min_interval=0)
    assert f.fetch(NEWS_URL).body == HTML


# ------------------------------------------------------------------ core
def test_seed_sources_idempotent_no_invented_urls(env: Path) -> None:
    with session_factory()() as s:
        assert mon.seed_sources(s) == 9
        assert mon.seed_sources(s) == 0
        srcs = list(s.scalars(select(WatchedSource)))
        for src in srcs:
            assert src.url.startswith(("https://tax.gov.ae/", "urn:auditsmart:pending:"))
            assert src.active == src.url.startswith("https://")
            assert mon.due(src) == src.active
        repo = "".join(p.read_text(errors="ignore") for p in S2.glob("*.*")
                       if p.suffix in (".txt", ".html", ".md"))
        for src in srcs:
            if src.url.startswith("https://"):
                assert src.url.lower() in repo.lower(), src.url  # recorded, not invented


def test_first_check_pdf_creates_proposals_then_unchanged(env: Path) -> None:
    got: list[UpdateAlert] = []
    with session_factory()() as s:
        src = _src(s, D17_URL, "pdf")
        f = FakeFetcher({D17_URL: pdf()})
        a = mon.check_source(s, src, f, extractor=fixed(D17_OUT), notify=got.append)
        assert a is not None and a.kind == "change" and a.status == "open"
        assert len(a.proposal_ids or []) == 4 and got == [a]
        rows = [s.get(RuleVersion, i) for i in a.proposal_ids or []]
        assert all(r is not None and r.status == "proposed" for r in rows)
        assert {r.source_url for r in rows if r} == {D17_URL}
        assert {r.source_doc_hash for r in rows if r} == {src.last_hash}
        assert a.details and a.details["first_check"] is True
        assert (env / "storage" / a.details["snapshot"]).read_text().startswith("This is not")
        assert src.last_checked is not None and src.last_error is None
        # unchanged -> no alert, no AI call
        assert mon.check_source(s, src, f, extractor=lambda _: pytest.fail("AI called"),
                                notify=got.append) is None
        assert len(got) == 1
        s.commit()


def test_unrelated_change_logged_not_alerted(env: Path) -> None:
    with session_factory()() as s:
        src = _src(s, NEWS_URL)
        f = FakeFetcher({NEWS_URL: html()})
        assert mon.check_source(s, src, f, extractor=fixed(NO_CHANGE_OUT)) is None
        assert s.scalar(select(AuditLog).where(AuditLog.action == "monitor_no_change"))
        assert src.last_links and src.last_hash


def test_new_document_link_detected(env: Path) -> None:
    extra = b'<a href="/datafolder/Files/Pdf/2026/legislation/new.pdf">New</a>'
    with session_factory()() as s:
        src = _src(s, NEWS_URL)
        mon.check_source(s, src, FakeFetcher({NEWS_URL: html()}), extractor=fixed(NO_CHANGE_OUT))
        body = HTML.replace(b"</body>", extra + b"</body>")
        a = mon.check_source(s, src, FakeFetcher({NEWS_URL: html(body)}),
                             extractor=fixed(NO_CHANGE_OUT))
        assert a is not None and a.kind == "change"
        new = "https://tax.gov.ae/datafolder/Files/Pdf/2026/legislation/new.pdf"
        assert a.details and a.details["new_links"] == [new]
        assert "new document link" in (a.summary or "")


def test_new_link_with_unchanged_text(env: Path) -> None:
    with session_factory()() as s:
        src = _src(s, NEWS_URL)
        mon.check_source(s, src, FakeFetcher({NEWS_URL: html()}), extractor=fixed(NO_CHANGE_OUT))
        src.last_links = [x for x in src.last_links or [] if "legislation.aspx" not in x]
        a = mon.check_source(s, src, FakeFetcher({NEWS_URL: html()}))
        assert a is not None and "page text unchanged" in (a.summary or "")
        assert a.details and a.details["new_links"] == ["https://tax.gov.ae/en/legislation.aspx"]


@pytest.mark.parametrize("ai", ["not json", '{"summary": "x", "changes": []}', "raise"])
def test_ai_failure_still_alerts(env: Path, ai: str) -> None:
    def ext(_: str) -> str:
        if ai == "raise":
            raise RuntimeError("provider down")
        return ai
    with session_factory()() as s:
        src = _src(s, D17_URL, "pdf")
        a = mon.check_source(s, src, FakeFetcher({D17_URL: pdf()}), extractor=ext)
        assert a is not None and a.proposal_ids == []
        assert a.details and a.details["ai_error"]
        assert "review the document manually" in (a.summary or "")


def test_rejected_and_undated_changes_reported(env: Path) -> None:
    out = json.dumps({"summary": "mixed", "changes": [
        {"rule_key": "payroll.rate", "current_value": None, "proposed_value": 1,
         "effective_date": "2026-10-01", "citation": "Art 1", "confidence": "low"},
        {"rule_key": "vat.rate.standard", "current_value": "0.05", "proposed_value": "0.06",
         "effective_date": None, "citation": "Art 2", "confidence": "low"}]})
    with session_factory()() as s:
        src = _src(s, D17_URL, "pdf")
        a = mon.check_source(s, src, FakeFetcher({D17_URL: pdf()}), extractor=fixed(out))
        assert a is not None and a.proposal_ids == []
        assert a.details and len(a.details["rejected"]) == 1 and len(a.details["undated"]) == 1


def test_failure_creates_alert_and_check_all_continues(env: Path) -> None:
    sent: list[str] = []
    with session_factory()() as s:
        bad = _src(s, "https://tax.gov.ae/en/legislation.aspx")
        good = _src(s, NEWS_URL)
        placeholder = WatchedSource(url="urn:auditsmart:pending:x", type="pdf", active=False)
        s.add(placeholder)
        f = FakeFetcher({bad.url: mon.MonitorError("HTTP 503 from FTA"),
                         good.url: html(b"<html><body><p></p></body></html>")})
        res = mon.check_all(s, f, extractor=fixed(NO_CHANGE_OUT),
                            notify=lambda a: sent.append(a.kind))
        assert res["checked"] == 2 and len(res["alerts"]) == 2 and sorted(sent) == \
            ["failure", "failure"]  # empty page text is a failure too
        assert bad.last_error == "HTTP 503 from FTA"
        assert good.last_error == "No text could be extracted"
        # not due again within a week; force checks anyway; placeholders never
        assert mon.check_all(s, f)["checked"] == 0
        assert mon.check_all(s, f, force=True, extractor=fixed(NO_CHANGE_OUT))["checked"] == 2
        later = datetime.now(UTC) + timedelta(days=8)
        assert mon.due(good, later) and not mon.due(placeholder, later)
        good.last_checked = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None)
        assert not mon.due(good)


def test_notifier_error_never_loses_alert(env: Path) -> None:
    def boom(_: UpdateAlert) -> None:
        raise OSError("smtp down")
    with session_factory()() as s:
        src = _src(s, D17_URL, "pdf")
        a = mon.check_source(s, src, FakeFetcher({D17_URL: mon.MonitorError("x")}), notify=boom)
        assert a is not None and a.details and a.details["notify_error"] == "smtp down"


def test_teams_notifier_and_log_notifier(caplog: pytest.LogCaptureFixture) -> None:
    posts: list[tuple[str, bytes]] = []
    n = mon.teams_notifier("https://example.webhook.office.com/x",
                           lambda u, b: posts.append((u, b)) or 200)
    a = UpdateAlert(id="a1", kind="change", summary="Decision 17")
    n(a)
    assert json.loads(posts[0][1])["text"].endswith("Decision 17")
    with pytest.raises(mon.MonitorError):
        mon.teams_notifier("http://insecure", lambda u, b: 200)
    mon.log_notifier(a)
    assert "Decision 17" in caplog.text


def test_upload(env: Path) -> None:
    with session_factory()() as s:
        a = mon.upload(s, D17_PDF, file_name="decision17.pdf", source_url=D17_URL,
                       uploaded_by="tp-1", extractor=fixed(D17_OUT))
        assert a.kind == "upload" and len(a.proposal_ids or []) == 4 and a.source_id is None
        t = mon.upload(s, b"FTA text without rules", file_name="note.txt", source_url=None,
                       uploaded_by="tp-1", extractor=fixed(NO_CHANGE_OUT))
        assert t.proposal_ids == [] and t.details and t.details["url"] is None
        h = mon.upload(s, HTML, file_name="page.html", source_url=None, uploaded_by="tp-1",
                       extractor=fixed(NO_CHANGE_OUT))
        assert h.kind == "upload"
        for kw, err in [({"body": b""}, "Empty"), ({"source_url": "http://x"}, "https"),
                        ({"body": b"   "}, "No text"),
                        ({"body": b"x" * (mon.MAX_BYTES + 1)}, "larger")]:
            args: dict[str, Any] = {"body": b"x", "source_url": None, **kw}
            with pytest.raises(mon.MonitorError, match=err):
                mon.upload(s, args["body"], file_name="f.txt", source_url=args["source_url"],
                           uploaded_by="tp-1")


def test_user_message_layout_and_current_rules(env: Path) -> None:
    msg = mon.user_message(D17_URL, "abc " * 30000)
    lines = msg.split("\n")
    assert lines[0].startswith("current_rules: {") and lines[1] == f"document_url: {D17_URL}"
    assert lines[2].startswith("document_text: ") and len(lines[2]) <= 15 + mon.MAX_AI_CHARS
    assert "manual upload" in mon.user_message(None, "x")
    assert all(rule_proposals.key_allowed(k) for k in mon.current_rules())


def test_default_extractor(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config
    from app.services import ai_gateway

    monkeypatch.setenv("AI_PROVIDER", "stub")
    config.reset_settings()
    out = mon.default_extractor()("current_rules: {}")
    assert json.loads(out)["summary"] == rule_proposals.NO_CHANGE
    calls: list[tuple[str, str, float]] = []

    class P:
        name = "gemini"

        def complete(self, system: str, user: str, temperature: float) -> str:
            calls.append((system, user, temperature))
            return NO_CHANGE_OUT
    monkeypatch.setattr(ai_gateway, "get_provider", lambda **_: P())
    assert mon.default_extractor()("u") == NO_CHANGE_OUT
    assert calls[0][0] == rule_proposals.PROMPT_PATH.read_text() and calls[0][2] == 0.0
    config.reset_settings()


def test_cli_monitor_check(env: Path, monkeypatch: pytest.MonkeyPatch,
                           capsys: pytest.CaptureFixture[str]) -> None:
    from app import cli

    fake = FakeFetcher({})
    monkeypatch.setattr(mon, "PoliteFetcher", lambda: fake)
    monkeypatch.setattr(mon, "default_extractor", lambda: fixed(NO_CHANGE_OUT))
    seed = json.loads(mon.SEED_PATH.read_text())["sources"]
    fake.pages = {x["url"]: mon.MonitorError("offline test") for x in seed}
    assert cli.main(["monitor-check", "--force"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["checked"] == 6 and len(res["alerts"]) == 6
