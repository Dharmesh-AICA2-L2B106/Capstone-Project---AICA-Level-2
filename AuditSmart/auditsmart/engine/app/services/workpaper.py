"""Working paper (ISA 230): an 11-sheet Excel file built from stored engine results (prompt 3.6).

The builder only lays out figures the engine already computed and stored; it does not
recalculate anything, and no AI is used. Generation is refused while any included result is
STALE (unless a Manager/Partner records a justified override, DECISIONS D19) or while any
AI-generated draft on the included sample is unreviewed.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.services import jobs
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.6"

SHEETS = ("Lead", "Population", "Sampling", "Sample & Testing", "JE Risk", "Benford",
          "Evaluation", "Input VAT", "AI Drafts", "Rules & Calendar", "Sign-offs")
YES_NO_NA = '"Yes,No,N/A"'
OVERRIDE_ROLES = ("Manager", "Partner")
MIN_JUSTIFICATION = 20
AED = '#,##0.00;[Red](#,##0.00);"-"'
NAVY = "1F3864"
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEAD_FILL = PatternFill("solid", fgColor=NAVY)
_HEAD_FONT = Font(bold=True, color="FFFFFF")
_LABEL_FONT = Font(bold=True)
_DRAFT_FILL = PatternFill("solid", fgColor="FFF2CC")


class WorkpaperError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class WorkpaperData:
    """Everything the workbook shows. Values are the stored (JSON) engine results."""

    wp_ref: str
    engagement: dict[str, Any]
    dataset: dict[str, Any] | None = None
    sample: dict[str, Any] | None = None
    sample_items: list[dict[str, Any]] = field(default_factory=list)
    je: dict[str, Any] | None = None
    input_vat: dict[str, Any] | None = None
    ai_drafts: list[dict[str, Any]] = field(default_factory=list)
    preparer: str = ""
    reviewer: str | None = None
    overrides: list[dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def tool_version(self) -> str:
        return f"{ENGINE_NAME} {ENGINE_VERSION}"


# ------------------------------------------------------------------ gate
def check_gate(results: Sequence[Mapping[str, Any]], drafts: Iterable[Mapping[str, Any]],
               overrides: Sequence[Mapping[str, Any]], role: str | None) -> list[dict[str, Any]]:
    """results: [{kind, id, status}]. Returns the overrides that were applied."""
    by = {(o.get("kind"), o.get("id")): o for o in overrides}
    applied: list[dict[str, Any]] = []
    for r in results:
        if str(r.get("status") or "").lower() != "stale":
            continue
        o = by.get((r["kind"], r["id"]))
        if o is None:
            raise WorkpaperError(f"The {r['kind']} {r['id']} is STALE (a rule or calendar it "
                                 "used has changed). Re-run it, or have a Manager or Partner "
                                 "record a justified override.", 409)
        if role not in OVERRIDE_ROLES:
            raise WorkpaperError("Only a Manager or Partner on the engagement can override a "
                                 "STALE result.", 403)
        if len(str(o.get("justification") or "").strip()) < MIN_JUSTIFICATION:
            raise WorkpaperError(f"The override for {r['kind']} {r['id']} needs a justification "
                                 f"of at least {MIN_JUSTIFICATION} characters.", 422)
        applied.append(dict(o))
    unreviewed = [d for d in drafts if d.get("ai_generated") and not d.get("reviewed_by")]
    if unreviewed:
        refs = ", ".join(sorted(str(d.get("line_ref")) for d in unreviewed))
        raise WorkpaperError(f"{len(unreviewed)} AI draft(s) are not reviewed ({refs}). A "
                             "reviewer must tick each draft before the working paper is "
                             "generated.", 409)
    return applied


# ------------------------------------------------------------------ cell helpers
def _num(v: Any) -> Any:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, int | float | Decimal):
        return float(v) if isinstance(v, Decimal) else v
    try:
        return float(Decimal(str(v).replace(",", "")))
    except ArithmeticError:
        return str(v)


def _txt(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, list | tuple):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_txt(x)}" for k, x in v.items())
    return v


class _Sheet:
    """Writes a titled sheet with key/value blocks and tables."""

    def __init__(self, ws: Worksheet, data: WorkpaperData, title: str, widths: Sequence[int]):
        self.ws, self.row = ws, 1
        ws["A1"] = f"{data.engagement.get('client_name', '')} – {title}"
        ws["A1"].font = Font(bold=True, size=14, color=NAVY)
        ws["A2"] = (f"WP ref {data.wp_ref} | FYE {data.engagement.get('fye', '')} | "
                    f"{data.tool_version}")
        ws["A2"].font = Font(italic=True, color="595959")
        self.row = 4
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A4"
        ws.sheet_view.showGridLines = False
        ps = ws.page_setup
        ps.orientation = "landscape"
        ps.paperSize = ws.PAPERSIZE_A4
        ps.fitToWidth, ps.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_title_rows = "1:3"
        ws.oddFooter.left.text = f"WP {data.wp_ref}"
        ws.oddFooter.center.text = "Page &P of &N"
        ws.oddFooter.right.text = data.tool_version
        ws.oddHeader.right.text = "&A"

    def kv(self, pairs: Iterable[tuple[str, Any]], money_keys: Iterable[str] = ()) -> None:
        mk = set(money_keys)
        for k, v in pairs:
            a = self.ws.cell(self.row, 1, k)
            a.font = _LABEL_FONT
            if k in mk:
                c = self.ws.cell(self.row, 2, _num(v))
                c.number_format = AED
            else:
                c = self.ws.cell(self.row, 2, _txt(v))
                c.alignment = Alignment(wrap_text=True, vertical="top")
            self.row += 1
        self.row += 1

    def heading(self, text: str) -> None:
        c = self.ws.cell(self.row, 1, text)
        c.font = Font(bold=True, size=12, color=NAVY)
        self.row += 1

    def table(self, headers: Sequence[str], rows: Iterable[Sequence[Any]],
              money_cols: Iterable[int] = (), freeze: bool = False) -> tuple[int, int]:
        """Writes a header row + rows; returns (first data row, last data row)."""
        mc = set(money_cols)
        for i, h in enumerate(headers, start=1):
            c = self.ws.cell(self.row, i, h)
            c.fill, c.font, c.border = _HEAD_FILL, _HEAD_FONT, _BORDER
            c.alignment = Alignment(wrap_text=True, vertical="center")
        if freeze:
            self.ws.freeze_panes = f"A{self.row + 1}"
            self.ws.print_title_rows = f"1:{self.row}"
        self.row += 1
        first = self.row
        for r in rows:
            for i, v in enumerate(r, start=1):
                c = self.ws.cell(self.row, i, _num(v) if i in mc else _txt(v))
                c.border = _BORDER
                if i in mc:
                    c.number_format = AED
            self.row += 1
        last = self.row - 1
        self.row += 1
        return first, last

    def note(self, text: str) -> None:
        c = self.ws.cell(self.row, 1, text)
        c.font = Font(italic=True, color="7F7F7F")
        self.row += 2


# ------------------------------------------------------------------ sheets
def _lead(sh: _Sheet, d: WorkpaperData) -> None:
    e, s, j = d.engagement, d.sample or {}, d.je or {}
    ev = s.get("evaluation") or {}
    sh.kv([("Client", e.get("client_name")), ("Client code", e.get("client_code")),
           ("Emirate", e.get("emirate")), ("Financial year end", e.get("fye")),
           ("Framework", e.get("framework")), ("Materiality", e.get("materiality")),
           ("Performance materiality", e.get("perf_materiality")),
           ("Clearly trivial", e.get("trivial")), ("Working paper ref", d.wp_ref),
           ("Objective", "Document the sampling, journal-entry, Benford, evaluation and VAT "
                         "procedures performed with AuditSmart (ISA 230, 240, 450, 530).")],
          money_keys=("Materiality", "Performance materiality", "Clearly trivial"))
    sh.heading("Summary of results")
    bf = (j.get("benford") or {}).get("conclusion")
    sh.table(["Area", "Result", "Conclusion"], [
        ("Sampling", f"{s.get('method', 'not included')}; n = {s.get('sample_size', '')}"
         if s else "Not included", s.get("status", "")),
        ("Evaluation", f"UML {ev.get('uml', '')} vs TM {ev.get('tolerable_misstatement', '')}"
         if ev.get("method") == "mus" else
         (f"Projected {ev.get('projected_misstatement', '')}" if ev else "Not evaluated"),
         ev.get("conclusion", "")),
        ("JE testing", f"{j.get('flagged_lines', 0)} lines flagged; "
                       f"{j.get('selected_for_testing', 0)} selected" if j else "Not included",
         ""),
        ("Benford", (j.get("benford") or {}).get("conclusion_text", "Not included"), bf or ""),
        ("Input VAT", (d.input_vat or {}).get("conclusion", "Not included"), ""),
    ])
    pending = any(x.get("rules_pending_verification") for x in (s, j, d.input_vat or {}))
    if pending:
        sh.note("Some rule values are pending verification (Rules Library, DECISIONS D9). "
                "Conclusions are provisional until they are approved.")


def _population(sh: _Sheet, d: WorkpaperData) -> None:
    ds, s = d.dataset or {}, d.sample or {}
    pop = s.get("population") or {}
    sh.kv([("Dataset", ds.get("file_name")), ("Dataset ID", ds.get("id")),
           ("SHA-256", ds.get("sha256")), ("Rows", ds.get("rows")),
           ("Total debits", ds.get("total_dr")), ("Total credits", ds.get("total_cr")),
           ("Validation status", ds.get("status")),
           ("Sampling population lines", pop.get("lines")),
           ("Sampling population value", pop.get("value")),
           ("Accounts", _txt((s.get("parameters") or {}).get("account_types"))),
           ("Basis", (s.get("parameters") or {}).get("basis")),
           ("Credit lines excluded", (s.get("credit_lines_excluded") or {}).get("count"))],
          money_keys=("Total debits", "Total credits", "Sampling population value"))
    sh.note("The population is reconciled to the uploaded file by its SHA-256; the engine "
            "reads the stored Parquet copy only.")


def _sampling(sh: _Sheet, d: WorkpaperData) -> None:
    s = d.sample
    if not s:
        sh.note("No sample is included in this working paper.")
        return
    p = s.get("parameters") or {}
    sh.kv([("Sample ID", s.get("sample_id")), ("Method", s.get("method")),
           ("Confidence", p.get("confidence")), ("Confidence factor (CF)", s.get("cf_value")),
           ("CF rule version", s.get("cf_rule_version")),
           ("Expansion factor (EF)", s.get("ef_value")),
           ("Tolerable misstatement", p.get("tolerable_misstatement")),
           ("Expected misstatement", s.get("expected_misstatement")),
           ("Sample size required", s.get("n_required")), ("Items selected", s.get("sample_size")),
           ("Sampling interval (J)", s.get("interval")),
           ("Basic precision", s.get("basic_precision")),
           ("Top stratum items", (s.get("top_stratum") or {}).get("count")),
           ("Top stratum value", (s.get("top_stratum") or {}).get("value")),
           ("Seed", s.get("seed")), ("Random start", s.get("random_start")),
           ("Formula", s.get("formula_text")), ("Rationale", s.get("rationale")),
           ("Engine version", s.get("engine_version")), ("Dataset hash", s.get("dataset_hash"))],
          money_keys=("Tolerable misstatement", "Expected misstatement", "Sampling interval (J)",
                      "Basic precision", "Top stratum value", "Random start"))
    for w in s.get("warnings") or []:
        sh.note(str(w))


def _testing(sh: _Sheet, d: WorkpaperData) -> None:
    if not d.sample_items:
        sh.note("No sample items.")
        return
    heads = ["#", "Line ref", "Row", "Account", "Book value", "Top stratum", "Key item",
             "Exists", "Agreed to evidence", "Correctly recorded", "Audited value",
             "Misstatement", "Evidence ref", "Remarks"]
    rows = [(i, it.get("line_ref"), it.get("row_no"), it.get("account_code"),
             it.get("book_value"), it.get("top_stratum"), it.get("key_item"), "", "", "",
             it.get("audited_value"), it.get("misstatement"), it.get("evidence_ref"),
             it.get("remarks")) for i, it in enumerate(d.sample_items, start=1)]
    first, last = sh.table(heads, rows, money_cols=(5, 11, 12), freeze=True)
    dv = DataValidation(type="list", formula1=YES_NO_NA, allow_blank=True,
                        showErrorMessage=True, errorTitle="Yes / No / N/A",
                        error="Choose Yes, No or N/A.")
    dv.add(f"H{first}:J{last}")
    sh.ws.add_data_validation(dv)
    sh.ws.auto_filter.ref = f"A{first - 1}:N{last}"


def _je(sh: _Sheet, d: WorkpaperData) -> None:
    j = d.je
    if not j:
        sh.note("No JE testing run is included in this working paper.")
        return
    cal = j.get("calendar") or {}
    sh.kv([("JE run ID", j.get("je_run_id")), ("Calendar hash", j.get("calendar_hash")),
           ("Calendar version", f"{cal.get('emirate', '')} {cal.get('start', '')} to "
                                f"{cal.get('end', '')}"),
           ("Non-working days in period", cal.get("non_working_days")),
           ("Lines tested", (j.get("population") or {}).get("lines")),
           ("Lines flagged", j.get("flagged_lines")),
           ("Selected for testing", j.get("selected_for_testing")),
           ("Selected value", j.get("selected_value")),
           ("Selection basis", j.get("selection_basis"))], money_keys=("Selected value",))
    sh.heading("Criteria")
    sh.table(["Test", "Description", "Enabled", "Lines", "Vouchers", "Value"],
             [(t["test"], t.get("title"), t.get("enabled"), t.get("lines"), t.get("vouchers"),
               t.get("value")) for t in j.get("summary") or []], money_cols=(6,))
    sh.heading("Lines selected for testing")
    sel = [f for f in j.get("flags") or [] if f.get("selection") in ("test", "test_topup")]
    sh.table(["Line ref", "Voucher", "Date", "Time", "User", "Account", "Amount", "Score",
              "Selection", "Criteria", "Non-working reason"],
             [(f.get("line_ref"), f.get("voucher_no"), f.get("date"), f.get("time"),
               f.get("user_id"), f.get("account_code"), f.get("amount"), f.get("risk_score"),
               f.get("selection"), f.get("flags"), f.get("non_working_reason")) for f in sel],
             money_cols=(7,))


def _benford(sh: _Sheet, d: WorkpaperData) -> None:
    b = (d.je or {}).get("benford") or {}
    if not b.get("chart"):
        sh.note(str(b.get("error") or "No Benford analysis is included."))
        return
    sh.kv([("Amounts tested", b.get("n")), ("MAD", b.get("mad")),
           ("MAD thresholds", b.get("mad_thresholds")), ("Conclusion", b.get("conclusion")),
           ("Chi-square", b.get("chi_square")), ("Critical value", b.get("chi_square_critical")),
           ("p-value", b.get("p_value")), ("Commentary", b.get("conclusion_text"))])
    first, last = sh.table(["Digit", "Actual count", "Expected count", "Actual %", "Expected %",
                            "z", "Significant"],
                           [(c["digit"], c.get("actual_count"), c.get("expected_count"),
                             c.get("actual_pct"), c.get("expected_pct"), c.get("z"),
                             c.get("significant")) for c in b["chart"]])
    ch = BarChart()
    ch.type, ch.title = "col", "First-digit distribution (Benford)"
    ch.y_axis.title, ch.x_axis.title = "% of amounts", "First digit"
    ch.add_data(Reference(sh.ws, min_col=4, max_col=5, min_row=first - 1, max_row=last),
                titles_from_data=True)
    ch.set_categories(Reference(sh.ws, min_col=1, min_row=first, max_row=last))
    ch.height, ch.width = 8, 16
    sh.ws.add_chart(ch, f"I{first - 1}")


def _evaluation(sh: _Sheet, d: WorkpaperData) -> None:
    ev = (d.sample or {}).get("evaluation")
    if not ev:
        sh.note("The sample has not been evaluated yet.")
        return
    if ev.get("method") == "mus":
        sh.kv([("Confidence", ev.get("confidence")), ("Interval (J)", ev.get("interval")),
               ("Basic precision", ev.get("basic_precision")),
               ("Sum of projected misstatements", ev.get("sum_projected")),
               ("Incremental allowance", ev.get("incremental_allowance")),
               ("Upper misstatement limit", ev.get("uml")),
               ("Tolerable misstatement", ev.get("tolerable_misstatement")),
               ("Conclusion", ev.get("conclusion")), ("Formula", ev.get("formula_text"))],
              money_keys=("Interval (J)", "Basic precision", "Sum of projected misstatements",
                          "Incremental allowance", "Upper misstatement limit",
                          "Tolerable misstatement"))
        sh.table(["Line ref", "Book value", "Audited value", "Misstatement", "Top stratum",
                  "Tainting", "Projected", "Rank", "Factor", "Incremental allowance"],
                 [(r["line_ref"], r.get("book_value"), r.get("audited_value"),
                   r.get("misstatement"), r.get("top_stratum"), r.get("tainting"),
                   r.get("projected"), r.get("rank"), r.get("incremental_factor"),
                   r.get("incremental_allowance")) for r in ev.get("items") or []],
                 money_cols=(2, 3, 4, 7, 10))
    else:
        sh.kv([("Projected misstatement", ev.get("projected_misstatement")),
               ("Actual (key / top items)", ev.get("actual_misstatement_key_items")),
               ("Tolerable misstatement", ev.get("tolerable_misstatement")),
               ("Conclusion", ev.get("conclusion")), ("Formula", ev.get("formula_text"))],
              money_keys=("Projected misstatement", "Actual (key / top items)",
                          "Tolerable misstatement"))
        sh.table(["Stratum", "Items", "Sample book", "Sample misstatement", "Population value",
                  "Projected"],
                 [(r.get("stratum"), r.get("sample_items"), r.get("sample_book"),
                   r.get("sample_misstatement"), r.get("population_value"), r.get("projected"))
                  for r in ev.get("strata") or []], money_cols=(3, 4, 5, 6))
    for w in ev.get("warnings") or []:
        sh.note(str(w))


def _input_vat(sh: _Sheet, d: WorkpaperData) -> None:
    iv = d.input_vat
    if not iv:
        sh.note("No input VAT run is included in this working paper.")
        return
    sh.kv([("Input VAT run ID", iv.get("input_vat_run_id")),
           ("Conclusion", iv.get("conclusion")), ("Basis", iv.get("basis"))])
    sh.table(["Check", "Lines", "Value"],
             [(c.get("check"), c.get("lines"), c.get("value")) for c in iv.get("summary") or []],
             money_cols=(3,))
    sh.table(["Line ref", "Check", "Party", "Amount", "Reason"],
             [(e.get("line_ref"), e.get("check"), e.get("party_id"), e.get("amount"),
               e.get("reason")) for e in iv.get("exceptions") or []], money_cols=(4,))


def _drafts(sh: _Sheet, d: WorkpaperData) -> None:
    if not d.ai_drafts:
        sh.note("No AI drafts are attached to the included results.")
        return
    first, last = sh.table(["Line ref", "Status", "Draft text", "Prompt version", "Model",
                            "Reviewed", "Reviewer", "Reviewed at"],
                           [(a.get("line_ref"),
                             "DRAFT – AI generated" if a.get("ai_generated") else "Manual",
                             a.get("text"), a.get("prompt_version"), a.get("model"),
                             "✓" if a.get("reviewed_by") else "✗", a.get("reviewed_by"),
                             a.get("reviewed_at")) for a in d.ai_drafts])
    for r in range(first, last + 1):
        sh.ws.cell(r, 2).fill = _DRAFT_FILL
        sh.ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical="top")
    sh.note("AI text is a draft prepared from anonymised data; the reviewer's tick records "
            "that it was read, corrected where needed and accepted.")


def rule_rows(*results: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """All rule versions used by the given results, one row per ref (sorted)."""
    from app.services.rules import all_rules

    seed = {r.ref: r for r in all_rules()}
    out: dict[str, dict[str, Any]] = {}

    def visit(src: str, used: Mapping[str, Any] | None) -> None:
        for key, v in (used or {}).items():
            if not isinstance(v, Mapping):
                continue
            ref = str(v.get("ref") or key)
            rule_key = str(v.get("rule_key") or ref.split("@")[0])
            row = out.setdefault(ref, {"ref": ref, "rule_key": rule_key,
                                       "version": v.get("version"), "value": v.get("value"),
                                       "status": v.get("status"), "used_by": [],
                                       "source_ref": getattr(seed.get(ref), "source_ref", ""),
                                       "source_url": v.get("source_url")
                                       or getattr(seed.get(ref), "source_url", None) or ""})
            if src not in row["used_by"]:
                row["used_by"].append(src)

    for res in results:
        if not res:
            continue
        name = str(res.get("_name", "result"))
        visit(name, res.get("rule_versions_used"))
        visit(f"{name}/benford", (res.get("benford") or {}).get("rule_versions_used"))
        visit(f"{name}/evaluation", (res.get("evaluation") or {}).get("rule_versions_used"))
    return [out[k] for k in sorted(out)]


def _rules(sh: _Sheet, d: WorkpaperData) -> None:
    rows = rule_rows(*({**(x or {}), "_name": n} if x else None for n, x in
                       (("sampling", d.sample), ("je", d.je), ("input_vat", d.input_vat))))
    sh.heading("Rule versions used")
    sh.table(["Rule", "Version", "Value", "Status", "Used by", "Source", "Source URL"],
             [(r["rule_key"], r["version"], _txt(r["value"]), r["status"], r["used_by"],
               r["source_ref"], r["source_url"] or "(not recorded – Rules Library 3.8)")
              for r in rows])
    cal = (d.je or {}).get("calendar")
    sh.heading("Working calendar")
    if not cal:
        sh.note("No calendar was used (no JE testing run included).")
        return
    lay = cal.get("layers") or {}
    sh.kv([("Calendar hash", cal.get("hash")), ("Emirate", cal.get("emirate")),
           ("Period", f"{cal.get('start')} to {cal.get('end')}"),
           ("Work-week layers", lay.get("work_weeks")),
           ("Holiday layers", lay.get("holidays")),
           ("Company exceptions", lay.get("company_exceptions")),
           ("Days by source", lay.get("day_sources")),
           ("Provisional holidays", cal.get("provisional_holidays")),
           ("Pending verification", cal.get("pending_verification"))])


def _signoffs(sh: _Sheet, d: WorkpaperData) -> None:
    sh.table(["Role", "Name", "Date", "Signature / tick"],
             [("Preparer", d.preparer, d.generated_at.date().isoformat(), "✓"),
              ("Reviewer", d.reviewer or "", "", "")])
    sh.kv([("Tool version", d.tool_version),
           ("Generated at (UTC)", d.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
           ("Dataset SHA-256", (d.dataset or {}).get("sha256")),
           ("Sample ID", (d.sample or {}).get("sample_id")),
           ("JE run ID", (d.je or {}).get("je_run_id")),
           ("Calendar hash", (d.je or {}).get("calendar_hash"))])
    if d.overrides:
        sh.heading("STALE overrides")
        sh.table(["Result", "ID", "Justification", "By"],
                 [(o.get("kind"), o.get("id"), o.get("justification"), o.get("by"))
                  for o in d.overrides])


_WIDTHS: dict[str, Sequence[int]] = {
    "Lead": (30, 70, 22), "Population": (30, 70), "Sampling": (30, 80),
    "Sample & Testing": (5, 11, 7, 10, 15, 8, 8, 9, 11, 11, 15, 14, 14, 30),
    "JE Risk": (24, 40, 11, 10, 10, 15, 14, 7, 11, 40, 18), "Benford": (16, 14, 14, 11, 11, 9, 11),
    "Evaluation": (32, 15, 15, 15, 11, 11, 15, 7, 8, 15), "Input VAT": (22, 22, 14, 15, 50),
    "AI Drafts": (11, 20, 70, 12, 14, 10, 14, 20), "Rules & Calendar": (30, 9, 22, 20, 24, 50, 30),
    "Sign-offs": (22, 70, 14, 16),
}
_BUILDERS = (_lead, _population, _sampling, _testing, _je, _benford, _evaluation, _input_vat,
             _drafts, _rules, _signoffs)


def build_workbook(d: WorkpaperData) -> bytes:
    wb = Workbook()
    wb.remove(wb.active) if wb.active is not None else None
    for name, fn in zip(SHEETS, _BUILDERS, strict=True):
        ws = wb.create_sheet(name)
        fn(_Sheet(ws, d, name, _WIDTHS[name]), d)
    wb.properties.creator = d.tool_version
    wb.properties.title = f"{d.wp_ref} – AuditSmart working paper"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ service
def _wp_dir() -> Path:
    from app.core.config import get_settings

    p = get_settings().storage_path / "workpapers"
    p.mkdir(parents=True, exist_ok=True)
    return p


def generate(*, engagement_id: str, wp_ref: str, user_id: str, role: str | None,
             sample_id: str | None = None, je_run_id: str | None = None,
             input_vat_run_id: str | None = None, reviewer: str | None = None,
             stale_overrides: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import (
        AuditLog,
        Client,
        Dataset,
        Engagement,
        InputVatRun,
        JeRun,
        Observation,
        Sample,
        SampleItem,
        Workpaper,
    )
    from app.services.sampling import jsonable

    if not (sample_id or je_run_id or input_vat_run_id):
        raise WorkpaperError("Include at least one result (sample, JE run or input VAT run).")
    with session_factory()() as s:
        eng = s.get(Engagement, engagement_id)
        if eng is None:  # pragma: no cover - membership is checked first
            raise WorkpaperError("Engagement not found.", 404)
        cl = s.get(Client, eng.client_id)
        results: list[dict[str, Any]] = []
        smp = s.get(Sample, sample_id) if sample_id else None
        if sample_id and (smp is None or smp.engagement_id != engagement_id):
            raise WorkpaperError("Sample not found on this engagement.", 404)
        je = s.get(JeRun, je_run_id) if je_run_id else None
        if je_run_id and (je is None or je.engagement_id != engagement_id or je.result is None):
            raise WorkpaperError("JE run not found (or not finished) on this engagement.", 404)
        iv = s.get(InputVatRun, input_vat_run_id) if input_vat_run_id else None
        if input_vat_run_id and (iv is None or iv.engagement_id != engagement_id):
            raise WorkpaperError("Input VAT run not found on this engagement.", 404)
        items: list[dict[str, Any]] = []
        drafts: list[dict[str, Any]] = []
        if smp is not None:
            results.append({"kind": "sample", "id": smp.id, "status": smp.status})
            rows = s.query(SampleItem).filter_by(sample_id=smp.id).all()
            by_id = {r.id: r for r in rows}
            for r in sorted(rows, key=lambda x: int((x.attributes or {}).get("row_no") or 0)):
                a = r.attributes or {}
                items.append({"line_ref": r.line_ref, "row_no": a.get("row_no"),
                              "account_code": a.get("account_code"), "book_value": r.book_value,
                              "top_stratum": r.top_stratum, "key_item": a.get("key_item"),
                              "audited_value": r.audited_value, "misstatement": r.misstatement,
                              "evidence_ref": r.evidence_ref, "remarks": r.remarks})
            for ob in s.query(Observation).filter(Observation.sample_item_id.in_(list(by_id))):
                drafts.append({"line_ref": by_id[ob.sample_item_id].line_ref,
                               "ai_generated": ob.ai_generated, "text": _txt(ob.text),
                               "prompt_version": ob.prompt_version, "model": ob.model,
                               "reviewed_by": ob.reviewed_by,
                               "reviewed_at": ob.reviewed_at.isoformat() if ob.reviewed_at
                               else None})
        if je is not None:
            results.append({"kind": "je_run", "id": je.id, "status": je.status})
        if iv is not None:
            results.append({"kind": "input_vat_run", "id": iv.id, "status": iv.status})
        applied = check_gate(results, drafts, stale_overrides, role)
        for o in applied:
            o["by"] = user_id
        ds_id = (smp.dataset_id if smp else je.dataset_id if je else
                 iv.dataset_id if iv else None)
        ds = s.get(Dataset, ds_id) if ds_id else None
        data = WorkpaperData(
            wp_ref=wp_ref,
            engagement={"client_name": cl.name if cl else "", "client_code":
                        cl.client_code if cl else "", "emirate": cl.emirate if cl else "",
                        "fye": eng.fye.isoformat(), "framework": eng.framework,
                        "materiality": eng.materiality, "perf_materiality": eng.perf_materiality,
                        "trivial": eng.trivial},
            dataset=None if ds is None else {
                "id": ds.id, "file_name": ds.file_name, "sha256": ds.sha256, "rows": ds.rows,
                "total_dr": ds.total_dr, "total_cr": ds.total_cr, "status": ds.status},
            sample=dict(smp.result or {}) if smp else None, sample_items=items,
            je={**(je.result or {}), "je_run_id": je.id} if je else None,
            input_vat={**(getattr(iv, "result", None) or {}), "input_vat_run_id": iv.id}
            if iv else None,
            ai_drafts=drafts, preparer=user_id, reviewer=reviewer, overrides=applied)
        blob = build_workbook(data)
        digest = hashlib.sha256(blob).hexdigest()
        wp = Workpaper(engagement_id=engagement_id, wp_ref=wp_ref, status="prepared",
                       preparer=user_id, reviewer=reviewer, prepared_at=data.generated_at,
                       tool_version=data.tool_version, sha256=digest)
        s.add(wp)
        s.flush()
        path = _wp_dir() / f"{wp.id}.xlsx"
        path.write_bytes(blob)
        manifest = jsonable({"results": results, "overrides": applied, "sheets": list(SHEETS),
                             "rules": [r["ref"] for r in rule_rows(
                                 data.sample, data.je, data.input_vat)],
                             "ai_drafts": len(drafts), "sample_items": len(items)})
        wp.file_ref, wp.manifest = str(path), manifest
        s.add(AuditLog(user_id=user_id, action="generate", entity="workpaper", entity_id=wp.id,
                       new={"wp_ref": wp_ref, "sha256": digest, **manifest}))
        s.commit()
        return describe(wp)


def _utc(v: datetime | None) -> str | None:
    if v is None:  # pragma: no cover - always set on generation
        return None
    return (v if v.tzinfo else v.replace(tzinfo=UTC)).isoformat()


def describe(wp: Any) -> dict[str, Any]:
    return {"workpaper_id": wp.id, "engagement_id": wp.engagement_id, "wp_ref": wp.wp_ref,
            "status": wp.status, "preparer": wp.preparer, "reviewer": wp.reviewer,
            "prepared_at": _utc(wp.prepared_at),
            "tool_version": wp.tool_version, "sha256": wp.sha256, "manifest": wp.manifest,
            "file_url": f"/v1/workpapers/{wp.id}/file"}


def get_workpaper(workpaper_id: str) -> tuple[str, dict[str, Any], Path]:
    from app.core.db import session_factory
    from app.models import Workpaper

    with session_factory()() as s:
        wp = s.get(Workpaper, workpaper_id)
        if wp is None or not wp.file_ref:
            raise WorkpaperError("Working paper not found.", 404)
        return wp.engagement_id, describe(wp), Path(wp.file_ref)


@jobs.task("workpaper")
def workpaper_task(job_id: str, **kwargs: Any) -> str:
    """Large export as a background job (prompt 3.11)."""
    jobs.set_progress(job_id, 10)
    out = generate(**kwargs)
    return f"workpaper:{out['workpaper_id']}"
