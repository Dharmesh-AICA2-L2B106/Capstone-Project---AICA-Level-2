"""FTA rules monitor (prompt 3.9, SPEC 3.4).

Watches public FTA pages/PDFs, detects changes, asks the AI rule extractor
(app/ai_prompts/rule_extraction_v1.txt) for structured proposals, validates them
strictly (rule_proposals.parse_extraction) and stores them as ``proposed`` rule
versions.  Nothing is ever approved here; a Tax Partner approves in /v1/rules.

Politeness: identified User-Agent, robots.txt honoured, per-host rate limit,
timeout, size cap, https only, no cookies or logins.  The transport is injectable;
tests use saved fixtures only (no network).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog, UpdateAlert, WatchedSource
from app.services import rule_proposals, rules
from app.version import ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.9"

log = logging.getLogger("auditsmart.rules_monitor")

SEED_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "watched_sources.json"
USER_AGENT = (f"AuditSmart-RulesMonitor/{ENGINE_VERSION} (CLA Emirates audit tool; "
              "weekly check of public FTA pages; no login)")
TIMEOUT_S = 20
MIN_INTERVAL_S = 5.0  # per host
MAX_BYTES = 20 * 1024 * 1024
MAX_AI_CHARS = 60_000
CHECK_EVERY = timedelta(days=7)
SOURCE_TYPES = ("html", "pdf")
DOC_SUFFIXES = (".pdf", ".aspx", ".htm", ".html")


class MonitorError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ----------------------------------------------------------------- fetching
@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes


Transport = Callable[[str, dict[str, str], float], Response]


def urllib_transport(url: str, headers: dict[str, str], timeout: float) -> Response:
    """Real HTTPS GET (never used by the tests)."""
    req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  # pragma: no cover
            body = r.read(MAX_BYTES + 1)
            return Response(r.status, r.headers.get("Content-Type", ""), body)
    except urllib.error.HTTPError as exc:  # pragma: no cover - network
        return Response(exc.code, "", b"")


class Fetcher(Protocol):
    def fetch(self, url: str) -> Response: ...


@dataclass
class PoliteFetcher:
    transport: Transport = urllib_transport
    user_agent: str = USER_AGENT
    timeout: float = TIMEOUT_S
    min_interval: float = MIN_INTERVAL_S
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _get(self, url: str) -> Response:
        host = urlsplit(url).netloc.lower()
        with self._lock:
            wait = self._last.get(host, -1e9) + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
            self._last[host] = self.clock()
        return self.transport(url, {"User-Agent": self.user_agent,
                                    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"},
                              self.timeout)

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            r = self._get(base + "/robots.txt")
            if r.status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(r.body.decode("utf-8", "replace").splitlines())
                self._robots[base] = rp
            elif r.status in (401, 403):
                self._robots[base] = None  # treat as "disallow all"
            else:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse([])  # missing robots.txt -> allowed
                self._robots[base] = rp
        rp_ = self._robots[base]
        return rp_ is not None and rp_.can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> Response:
        if urlsplit(url).scheme != "https":
            raise MonitorError(f"Only https sources are fetched: {url}", 400)
        if not self.allowed(url):
            raise MonitorError(f"robots.txt disallows {url}", 403)
        r = self._get(url)
        if r.status != 200:
            raise MonitorError(f"HTTP {r.status} from {url}")
        if len(r.body) > MAX_BYTES:
            raise MonitorError(f"{url} is larger than {MAX_BYTES} bytes", 413)
        return r


# --------------------------------------------------------------- extraction
@dataclass(frozen=True)
class Document:
    text: str
    links: list[str]
    kind: str  # html | pdf | text

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _clean_link(base: str, href: str) -> str | None:
    u = urlsplit(urljoin(base, href.strip()))
    if u.scheme != "https" or not u.netloc:
        return None
    return urlunsplit((u.scheme, u.netloc.lower(), u.path, u.query, ""))


def html_document(body: bytes, base_url: str) -> Document:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    host = urlsplit(base_url).netloc.lower()
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        link = _clean_link(base_url, str(a["href"]))
        if link and urlsplit(link).netloc == host and \
                urlsplit(link).path.lower().endswith(DOC_SUFFIXES):
            links.add(link)
    return Document(_norm(soup.get_text("\n")), sorted(links), "html")


def pdf_document(body: bytes) -> Document:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:  # pdfminer raises many types
        raise MonitorError(f"Could not read the PDF: {type(exc).__name__}", 422) from None
    return Document(_norm(text), [], "pdf")


def to_document(body: bytes, content_type: str, url: str) -> Document:
    ct = content_type.lower()
    if body[:5] == b"%PDF-" or "pdf" in ct:
        return pdf_document(body)
    if "html" in ct or body.lstrip()[:1] == b"<":
        return html_document(body, url)
    return Document(_norm(body.decode("utf-8", "replace")), [], "text")


# ---------------------------------------------------------------- AI step
Extractor = Callable[[str], str]  # user message -> model text


def current_rules() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in rules.default_rules():  # shared defaults only, never a firm override (D42)
        if r.status == "approved" and r.effective_to is None and \
                rule_proposals.key_allowed(r.rule_key):
            out[r.rule_key] = r.value
    return out


def user_message(url: str | None, text: str) -> str:
    """Exactly the input layout tested in Stage 2.2 (rule_test1/2_input.txt)."""
    return (f"current_rules: {json.dumps(current_rules(), sort_keys=True, default=str)}\n"
            f"document_url: {url or 'manual upload'}\n"
            f"document_text: {text[:MAX_AI_CHARS]}")


def default_extractor() -> Extractor:
    """The configured AI provider with the rule-extraction prompt (no stub calls out)."""
    from app.services import ai_gateway

    provider = ai_gateway.get_provider()  # raises AIError(503) when not configured
    if getattr(provider, "name", "") == "stub":
        def stub(_: str) -> str:
            return json.dumps({"summary": rule_proposals.NO_CHANGE, "changes": []})
        return stub
    system = rule_proposals.PROMPT_PATH.read_text(encoding="utf-8")
    return lambda user: provider.complete(system, user, 0.0)


# ----------------------------------------------------------- notifications
Notifier = Callable[[UpdateAlert], None]


def log_notifier(alert: UpdateAlert) -> None:
    """Default: log only.  Email / Teams delivery is configured per deployment (Stage 7)."""
    log.warning("rules monitor alert %s [%s]: %s", alert.id, alert.kind, alert.summary)


def teams_notifier(webhook_url: str, transport: Callable[[str, bytes], int]) -> Notifier:
    """Teams incoming-webhook notifier; only built when TEAMS_WEBHOOK_URL is configured."""
    if urlsplit(webhook_url).scheme != "https":
        raise MonitorError("Teams webhook must be https", 400)

    def send(alert: UpdateAlert) -> None:
        body = json.dumps({"text": f"AuditSmart rules monitor ({alert.kind}): "
                                   f"{alert.summary}"}).encode()
        transport(webhook_url, body)
    return send


# -------------------------------------------------------------------- core
def _now() -> datetime:
    return datetime.now(UTC)


def _snapshot_dir() -> Path:
    return get_settings().storage_path / "rules_monitor"


def save_snapshot(doc: Document) -> str:
    d = _snapshot_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{doc.sha256}.txt"
    if not p.exists():
        p.write_text(doc.text, encoding="utf-8")
    return f"rules_monitor/{p.name}"


def seed_sources(s: Session) -> int:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    have = set(s.scalars(select(WatchedSource.url)))
    n = 0
    for src in data["sources"]:
        if src["url"] in have:
            continue
        s.add(WatchedSource(url=src["url"], type=src["type"], active=src["active"],
                            name=src["name"]))
        n += 1
    s.flush()
    return n


def seed_sources_db() -> int:
    from app.core.db import session_factory

    with session_factory()() as s:
        n = seed_sources(s)
        s.commit()
    return n


def _alert(s: Session, source: WatchedSource | None, kind: str, summary: str,
           details: dict[str, Any], proposal_ids: list[str], notify: Notifier) -> UpdateAlert:
    a = UpdateAlert(source_id=source.id if source else None, kind=kind,
                    summary=summary[:2000], details=details, proposal_ids=proposal_ids,
                    status="open")
    s.add(a)
    s.flush()
    s.add(AuditLog(user_id="fta-monitor", action=f"monitor_{kind}", entity="update_alert",
                   entity_id=a.id, old=None,
                   new={"summary": a.summary, "proposal_ids": proposal_ids}))
    try:
        notify(a)
    except Exception as exc:  # a failed notification never loses the alert
        log.error("notification failed for alert %s: %s", a.id, exc)
        a.details = {**details, "notify_error": str(exc)[:300]}
    return a


def analyse(s: Session, doc: Document, *, url: str | None, extractor: Extractor | None
            ) -> tuple[list[str], dict[str, Any], str]:
    """AI extraction -> strict validation -> ``proposed`` versions.  Never raises for AI."""
    info: dict[str, Any] = {"sha256": doc.sha256, "snapshot": save_snapshot(doc)}
    try:
        ext_fn = extractor or default_extractor()
        raw = ext_fn(user_message(url, doc.text))
        ext, rejected = rule_proposals.parse_extraction(raw)
    except Exception as exc:  # AIError, ExtractionError, provider errors
        info["ai_error"] = str(getattr(exc, "message", exc))[:500]
        return [], info, "Document changed; AI extraction unavailable or invalid - " \
                         "review the document manually."
    ids, undated = rule_proposals.create_proposals(
        s, ext, source_url=url if url and url.startswith("https://") else None,
        source_doc_hash=doc.sha256)
    info.update({"ai_summary": ext.summary, "rejected": rejected, "undated": undated})
    return ids, info, ext.summary


def check_source(s: Session, src: WatchedSource, fetcher: Fetcher, *,
                 extractor: Extractor | None = None, notify: Notifier = log_notifier
                 ) -> UpdateAlert | None:
    """One source: fetch, extract, hash, compare, snapshot, propose.  Returns the alert."""
    src.last_checked = _now()
    try:
        r = fetcher.fetch(src.url)
        doc = to_document(r.body, r.content_type, src.url)
        if not doc.text:
            raise MonitorError("No text could be extracted", 422)
    except Exception as exc:
        msg = str(getattr(exc, "message", exc))[:500]
        src.last_error = msg
        return _alert(s, src, "failure", f"Monitor failure for {src.name or src.url}: {msg}",
                      {"url": src.url}, [], notify)
    src.last_error = None
    new_links = sorted(set(doc.links) - set(src.last_links or [])) \
        if src.last_links is not None else []
    if src.last_hash == doc.sha256:
        src.last_links = doc.links
        if not new_links:
            return None
        return _alert(s, src, "change", f"{len(new_links)} new document link(s) on "
                      f"{src.name or src.url}; page text unchanged.",
                      {"url": src.url, "new_links": new_links, "sha256": doc.sha256}, [], notify)
    first = src.last_hash is None
    ids, info, summary = analyse(s, doc, url=src.url, extractor=extractor)
    src.last_hash = doc.sha256
    src.last_links = doc.links
    info.update({"url": src.url, "first_check": first, "new_links": new_links})
    if not ids and not new_links and summary == rule_proposals.NO_CHANGE \
            and not info.get("undated") and not info.get("rejected"):
        # changed page with nothing relevant: keep an audit trace, no alert noise
        s.add(AuditLog(user_id="fta-monitor", action="monitor_no_change",
                       entity="watched_source", entity_id=src.id, old=None, new=info))
        return None
    if new_links and not ids:
        summary = f"{len(new_links)} new document link(s) on {src.name or src.url}; " + summary
    return _alert(s, src, "change", summary, info, ids, notify)


def due(src: WatchedSource, now: datetime | None = None) -> bool:
    if not src.active or not src.url.startswith("https://"):
        return False
    if src.last_checked is None:
        return True
    last = src.last_checked if src.last_checked.tzinfo else src.last_checked.replace(tzinfo=UTC)
    return (now or _now()) - last >= CHECK_EVERY


def check_all(s: Session, fetcher: Fetcher, *, force: bool = False,
              extractor: Extractor | None = None, notify: Notifier = log_notifier
              ) -> dict[str, Any]:
    """Weekly run (``force`` = check-now).  One failing source never stops the others."""
    srcs = list(s.scalars(select(WatchedSource).order_by(WatchedSource.url)))
    checked, alerts = 0, []
    for src in srcs:
        if not (force and src.active and src.url.startswith("https://")) and not due(src):
            continue
        a = check_source(s, src, fetcher, extractor=extractor, notify=notify)
        checked += 1
        if a is not None:
            alerts.append(a.id)
    return {"checked": checked, "alerts": alerts}


def upload(s: Session, body: bytes, *, file_name: str, source_url: str | None,
           uploaded_by: str, extractor: Extractor | None = None,
           notify: Notifier = log_notifier) -> UpdateAlert:
    """Manual PDF (or HTML/text) upload by an admin/Tax Partner."""
    if source_url is not None and not source_url.startswith("https://"):
        raise MonitorError("source_url must be an https:// link", 422)
    if not body:
        raise MonitorError("Empty file", 422)
    if len(body) > MAX_BYTES:
        raise MonitorError(f"File is larger than {MAX_BYTES} bytes", 413)
    ct = "application/pdf" if file_name.lower().endswith(".pdf") else \
        "text/html" if file_name.lower().endswith((".htm", ".html")) else "text/plain"
    doc = to_document(body, ct, source_url or "https://upload.invalid/")
    if not doc.text:
        raise MonitorError("No text could be extracted from the file", 422)
    src = s.scalar(select(WatchedSource).where(WatchedSource.url == source_url)) \
        if source_url else None
    ids, info, summary = analyse(s, doc, url=source_url, extractor=extractor)
    info.update({"file_name": file_name, "uploaded_by": uploaded_by, "url": source_url})
    return _alert(s, src, "upload", f"Manual upload {file_name}: {summary}", info, ids, notify)
