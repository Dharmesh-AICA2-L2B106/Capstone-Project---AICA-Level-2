import os
import threading

import pytest
from openpyxl import load_workbook

from app.convert.batch import BatchCallbacks, BatchProcessor
from app.convert.output_manager import ConflictHandler, OutputError, incremented_path, save_atomically


def test_incremented_names(tmp_path):
    target = tmp_path / "report.xlsx"
    target.write_text("x")
    assert incremented_path(target).name == "report (2).xlsx"
    (tmp_path / "report (2).xlsx").write_text("x")
    assert incremented_path(target).name == "report (3).xlsx"


def test_conflict_policies(tmp_path):
    target = tmp_path / "a.docx"
    target.write_text("existing")
    assert ConflictHandler("skip").resolve(target, set()) is None
    assert ConflictHandler("overwrite").resolve(target, set()) == target
    assert ConflictHandler("increment").resolve(target, set()).name == "a (2).docx"
    # "ask" uses the resolver; "apply to all" is remembered
    calls = []
    handler = ConflictHandler("ask", lambda p: calls.append(p) or ("skip", True))
    assert handler.resolve(target, set()) is None
    assert handler.resolve(target, set()) is None
    assert len(calls) == 1
    # an output produced earlier in the same batch is never overwritten
    assert ConflictHandler("overwrite").resolve(target, {target}).name == "a (2).docx"


def test_existing_file_never_silently_overwritten(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    existing = settings.output_folder / "table.xlsx"
    existing.write_bytes(b"precious")
    settings.conflict_policy = "skip"
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.status == "skipped" and existing.read_bytes() == b"precious"
    settings.conflict_policy = "increment"
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.outputs[0].name == "table (2).xlsx" and existing.read_bytes() == b"precious"
    settings.conflict_policy = "overwrite"
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.outputs[0] == existing and load_workbook(existing).sheetnames


def test_same_names_from_different_folders(pdfs, settings, no_ocr, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    copy = other / "table.pdf"
    copy.write_bytes(pdfs["table"].read_bytes())
    settings.output_format = "excel"
    summary = BatchProcessor([pdfs["table"], copy], settings, no_ocr).run()
    names = sorted(r.outputs[0].name for r in summary.results)
    assert names == ["table (2).xlsx", "table.xlsx"]


def test_suffix_and_subfolder_naming(pdfs, settings, no_ocr):
    settings.output_format = "word"
    settings.naming = "suffix"
    settings.subfolder_per_pdf = True
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.outputs[0] == settings.output_folder / "table_Converted" / "table_Converted.docx"


def test_failed_write_leaves_no_partial_file(tmp_path):
    target = tmp_path / "out.xlsx"

    def broken_writer(tmp):
        tmp.write_bytes(b"not a real workbook")
        return []

    with pytest.raises(OutputError):
        save_atomically(target, broken_writer)
    assert not target.exists()
    assert not list(tmp_path.glob("~pcp_*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only folder semantics")
def test_output_folder_permission_error(pdfs, settings, no_ocr, tmp_path):
    """A write failure is reported per file; it does not crash the batch."""
    settings.output_format = "excel"
    blocker = settings.output_folder / "table.xlsx"
    blocker.mkdir()           # a folder with the output's name cannot be replaced by a file
    settings.conflict_policy = "overwrite"
    summary = BatchProcessor([pdfs["table"], pdfs["borderless"]], settings, no_ocr).run()
    first, second = summary.results
    assert first.status == "failed" and "Excel" in first.error
    assert second.status == "success"


def test_password_flow(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    attempts = []

    def ask(path, retry):
        attempts.append(retry)
        return "wrong" if len(attempts) == 1 else "secret123"

    res = BatchProcessor([pdfs["encrypted"]], settings, no_ocr, BatchCallbacks(ask_password=ask)).run().results[0]
    assert attempts == [False, True]
    assert res.status in ("success", "warning") and res.outputs


def test_password_not_supplied(pdfs, settings, no_ocr):
    res = BatchProcessor([pdfs["encrypted"]], settings, no_ocr).run().results[0]
    assert res.status == "failed" and "password" in res.error.lower()


def test_batch_continues_after_failures(pdfs, settings, no_ocr):
    files = [pdfs["corrupt"], pdfs["table"], pdfs["not_pdf"], pdfs["simple"], pdfs["twocol"]]
    summary = BatchProcessor(files, settings, no_ocr).run()
    statuses = [r.status for r in summary.results]
    assert statuses[0] == "failed" and statuses[2] == "failed"
    assert statuses[1] == "success" and statuses[3] in ("success", "warning")
    assert summary.succeeded == 3 and summary.failed == 2
    for r in summary.results:
        if r.status != "failed":
            assert len(r.outputs) == 2 and all(p.stat().st_size > 0 for p in r.outputs)
    assert "damaged" in summary.results[0].error and "not a valid PDF" in summary.results[2].error


def test_invalid_page_range_for_document(pdfs, settings, no_ocr):
    from app.convert.validators import parse_page_range
    settings.page_range = parse_page_range("2-3")
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.status == "failed" and "only 1 page" in res.error


def test_page_range_subset(pdfs, settings, no_ocr):
    from app.convert.validators import parse_page_range
    settings.output_format = "excel"
    settings.page_range = parse_page_range("2")
    res = BatchProcessor([pdfs["multipage"]], settings, no_ocr).run().results[0]
    assert res.pages_processed == 1
    ws = load_workbook(res.outputs[0])["Table_001"]
    assert {row[0].value for row in ws.iter_rows(min_row=2)} == {2}


# (test_report_export from PDF Converter Pro is not carried over: its CSV/TXT batch report
#  belonged to Converter Pro's results dialog; PDF Play Station shows results in its own panel.)


def test_cancellation_during_batch(pdfs, settings, no_ocr):
    cancel = threading.Event()
    started = []

    def on_page(page_no, done, total):
        if started and len(started) == 2:
            cancel.set()        # cancel while the second file is being read

    callbacks = BatchCallbacks(file_started=lambda i, p: started.append(p), page=on_page)
    files = [pdfs["table"], pdfs["multipage"], pdfs["simple"], pdfs["twocol"]]
    summary = BatchProcessor(files, settings, no_ocr, callbacks, cancel).run()
    statuses = [r.status for r in summary.results]
    assert statuses[0] == "success"
    assert statuses[1] == "cancelled" and not summary.results[1].outputs
    assert statuses[2:] == ["cancelled", "cancelled"]
    assert summary.cancelled
    assert not list(settings.output_folder.glob("multipage*"))
    assert not list(settings.output_folder.glob("~pcp_*"))
