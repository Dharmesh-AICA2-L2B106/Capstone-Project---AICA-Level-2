"""[EXE build, change 3] Hidden self-test:  "PDF Play Station 2.0.exe" --selftest [--workdir DIR]

Proves that the packaged program works on this computer: every tool of the three
sections is run through the same functions the screens use, on dummy files made on
the spot (no real data). Includes the bundled Tesseract (English / Hindi / Marathi /
orientation), a real worker-process job, file names with spaces and Devanagari
characters in nested folders, and error handling for bad input.

The report is written to <workdir>\\selftest_report.txt and to
%LOCALAPPDATA%\\PDF Play Station 2.0\\selftest_report.txt. Exit code 0 = all passed.
Never runs on a normal double-click.
"""

from __future__ import annotations

import io
import os
import platform
import sys
import tempfile
import time
import traceback
from pathlib import Path

LINE = "The quick brown fox jumps over the lazy dog."
KYC_LINES = ["Name: Ramesh Kumar", "PAN: ABCPK1234Q keep this", "Mobile +91 98765 43210",
             "Savings A/c No. 50100123456789", "Closing words stay here"]


class Check:
    def __init__(self, only: str = ""):
        self.rows: list[tuple[str, str, str, float]] = []
        self.only = [s.strip().lower() for s in only.split(",") if s.strip()]

    def run(self, name: str, fn):
        if self.only and not any(s in name.lower() for s in self.only):
            return
        t = time.time()
        try:
            detail = fn() or ""
            self.rows.append(("PASS", name, str(detail), time.time() - t))
        except AssertionError as exc:
            self.rows.append(("FAIL", name, f"check failed: {exc}", time.time() - t))
        except Exception as exc:
            self.rows.append(("FAIL", name, f"{type(exc).__name__}: {exc} | "
                              + traceback.format_exc(limit=3).replace("\n", " "), time.time() - t))

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r[0] == "FAIL")


# ------------------------------------------------------------------ dummy inputs

def _pdf(path: Path, pages: int, text: str = "Page {n}") -> Path:
    import pymupdf
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        p = doc.new_page()
        p.insert_text((72, 100), text.format(n=n), fontsize=14)
        p.insert_text((72, 130), f"MARKER-{n:03d}", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def _kyc(path: Path) -> Path:
    import pymupdf
    doc = pymupdf.open()
    p = doc.new_page()
    for i, t in enumerate(KYC_LINES):
        p.insert_text((60, 90 + i * 24), t, fontsize=12)
    doc.set_metadata({"author": "Ramesh Kumar"})
    doc.save(str(path))
    return path


def _scan_of(src_page_lines: list[str], path: Path, turn: int = 0) -> Path:
    """An image-only PDF page (as from a scanner), optionally turned by `turn` degrees clockwise."""
    import pymupdf
    from PIL import Image
    src = pymupdf.open()
    p = src.new_page()
    for i, t in enumerate(src_page_lines):
        p.insert_text((60, 90 + i * 30), t, fontsize=16)
    img = Image.open(io.BytesIO(p.get_pixmap(dpi=200).tobytes("png")))
    if turn:
        img = img.rotate(-turn, expand=True)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    sp = doc.new_page(width=img.width * 72 / 200, height=img.height * 72 / 200)
    sp.insert_image(sp.rect, stream=buf.getvalue())
    doc.save(str(path))
    return path


def _markers(path) -> list[str]:
    import pymupdf
    with pymupdf.open(str(path)) as d:
        return [next((w[4] for w in pg.get_text("words") if w[4].startswith("MARKER-")), "") for pg in d]


def _rotations(path) -> list[int]:
    import pymupdf
    with pymupdf.open(str(path)) as d:
        return [pg.rotation for pg in d]


def _worker_probe(path: str) -> None:            # runs in a spawned worker process
    Path(path).write_text(f"worker ok, frozen={getattr(sys, 'frozen', False)}", encoding="utf-8")


# ------------------------------------------------------------------ the test

def run_selftest(argv: list[str]) -> int:
    from . import APP_NAME, APP_VERSION, logger
    logger.setup()
    work = None
    if "--workdir" in argv and argv.index("--workdir") + 1 < len(argv):
        work = Path(argv[argv.index("--workdir") + 1])
    work = (work or Path(tempfile.mkdtemp(prefix="pps_selftest_"))) / "PDF Play Station selftest"
    inputs = work / "inputs" / "Client files 2026" / "उप फ़ोल्डर"          # spaces + Devanagari, nested
    out = work / "outputs"
    for d in (inputs, out):
        d.mkdir(parents=True, exist_ok=True)
    only = argv[argv.index("--only") + 1] if "--only" in argv and argv.index("--only") + 1 < len(argv) else ""
    c = Check(only)
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"

    from .services.common import Job, UserError
    from . import runners
    job = Job()

    def env():
        import pymupdf, PySide6
        return (f"{APP_NAME} {APP_VERSION}; frozen={getattr(sys, 'frozen', False)}; exe={sys.executable}; "
                f"Python {platform.python_version()}; Windows {platform.version()}; PyMuPDF {pymupdf.__version__}; "
                f"PySide6 {PySide6.__version__}")
    c.run("Environment", env)

    def screens():
        from PySide6.QtWidgets import QApplication
        from . import theme
        from .catalog import ALL_TOOLS
        from .icons import app_icon
        from .shell import MainWindow
        app = QApplication.instance() or QApplication([])
        assert (assets / "check.svg").is_file() and (assets / "chevron-down.svg").is_file(), "theme images missing"
        app.setStyleSheet(theme.stylesheet(str(assets / "check.svg")))
        assert not app_icon().isNull(), "application icon not loaded"
        w = MainWindow()
        for tool_id in ALL_TOOLS:
            w.show_tool(tool_id)
        n = len(ALL_TOOLS)
        # dispose of the hidden window completely, as closing the real application does
        from PySide6.QtCore import QCoreApplication, QEvent
        w.close()
        w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        return f"{n} tool pages built; icons and theme images loaded"
    c.run("Screens, icons and theme", screens)

    def tesseract():
        from .services import ocr
        st = ocr.status()
        assert st.available, st.message
        missing = {"eng", "hin", "mar", "osd"} - set(st.languages)
        assert not missing, f"language data missing: {missing}"
        if getattr(sys, "frozen", False):
            assert str(Path(sys._MEIPASS)) in st.path, f"not the bundled Tesseract: {st.path}"
        return f"{st.message} at {st.path}; languages {', '.join(st.languages)}"
    c.run("Bundled Tesseract OCR", tesseract)

    a = _pdf(inputs / "Invoice A (1).pdf", 3)
    b = _pdf(inputs / "बिल B.pdf", 2)

    def merge():
        o = out / "merge"
        o.mkdir(exist_ok=True)
        r = runners.merge(job, [str(a), str(b)], {"Output file name": "Merged.pdf",
                                                    "Add a bookmark for each original file": True}, str(o), {})
        assert _markers(r["files"][0]) == ["MARKER-001", "MARKER-002", "MARKER-003", "MARKER-001", "MARKER-002"]
        return r["message"]
    c.run("Merge PDF (names with spaces / Devanagari)", merge)

    def split():
        o = out / "split"
        o.mkdir(exist_ok=True)
        r = runners.split(job, [str(a)], {"Split by": "Every page", "N (pages per file)": 1, "Page ranges": ""},
                          str(o), {})
        assert len(r["files"]) == 3
        return r["message"]
    c.run("Split PDF", split)

    def rotate():
        o = out / "rotate"
        o.mkdir(exist_ok=True)
        r = runners.rotate(job, [str(a)], {"Rotate which pages": "Odd pages only", "Direction": "90° clockwise",
                                           "Page numbers": ""}, str(o), {})
        assert _rotations(r["files"][0]) == [90, 0, 90]
        return r["message"]
    c.run("Rotate PDF (odd pages)", rotate)

    def sideways_scan():
        o = out / "rotate"
        o.mkdir(exist_ok=True)
        import pymupdf
        parts = [_scan_of([LINE] * 12, work / f"scan{i}.pdf", t) for i, t in enumerate((0, 90))]
        merged = pymupdf.open()
        for p in parts:
            merged.insert_pdf(pymupdf.open(str(p)))
        src = inputs / "Scanned mix.pdf"
        merged.save(str(src))
        opts = {"Rotate which pages": "Sideways pages (detected automatically)", "Direction": "", "Page numbers": ""}
        first = runners.rotate(job, [str(src)], opts, str(o), {})
        plan = first["confirm"]["plans"]
        assert plan == {str(src): {2: 270}}, f"plan {plan}"
        opts["_plan"] = plan
        done = runners.rotate(job, [str(src)], opts, str(o), {})
        assert _rotations(done["files"][0]) == [0, 270]
        return "page 2 found sideways by OCR and turned upright"
    c.run("Rotate: sideways scanned page (OCR orientation)", sideways_scan)

    def numbers_and_passwords():
        o = out / "utilities"
        o.mkdir(exist_ok=True)
        r = runners.numbering(job, [str(a)], {"Position": "Bottom centre", "Format": "Page 1 of N", "Start at": 1,
                                              "Font size": 10, "Pages": ""}, str(o), {})
        import pymupdf
        with pymupdf.open(r["files"][0]) as d:
            assert d[1].search_for("Page 2 of 3")
        p = runners.protect(job, [str(a)], {"Password": "Test@123", "Confirm password": "Test@123",
                                            "Allow": ["Printing", "Copying text", "Editing"],
                                            "Permissions password (optional)": ""}, str(o), {})
        prot = p["files"][0]
        u = runners.unprotect(job, [prot], {"Current password": ""}, str(o), {prot: "Test@123"})
        with pymupdf.open(u["files"][0]) as d:
            assert not d.needs_pass
        return "page numbers, AES-256 protect and remove password"
    c.run("Page numbers and passwords", numbers_and_passwords)

    def images():
        from PIL import Image
        o = out / "images"
        o.mkdir(exist_ok=True)
        photo = Image.new("RGB", (400, 200), "white")
        exif = Image.Exif()
        exif[0x0112] = 6
        photo.save(inputs / "phone photo.jpg", exif=exif)
        frames = [Image.new("RGB", (200, 300), col) for col in ("red", "green")]
        frames[0].save(inputs / "multi.tif", save_all=True, append_images=frames[1:])
        r = runners.img2pdf(job, [str(inputs / "phone photo.jpg"), str(inputs / "multi.tif")],
                            {"Output file name": "Images.pdf", "Page size": "A4", "Orientation": "Automatic"},
                            str(o), {})
        import pymupdf
        with pymupdf.open(r["files"][0]) as d:
            assert d.page_count == 3 and d[0].rect.height > d[0].rect.width
        r2 = runners.pdf2img(job, [str(a)], {"Format": "PNG", "Resolution": "150 dpi", "Pages": "2"}, str(o), {})
        assert Image.open(r2["files"][0]).size[0] > 1000
        return "images to PDF (EXIF, TIFF) and PDF to PNG"
    c.run("Images to PDF / PDF to Images", images)

    def markdown():
        o = out / "markdown"
        o.mkdir(exist_ok=True)
        md = inputs / "notes.md"
        md.write_text("# सूचना\n\nखातेदाराचे नाव - Board **notes**\n\n| Year | Amount |\n| --- | --- |\n"
                      "| 2025 | 1,00,000 |\n", encoding="utf-8")
        r = runners.md2pdf(job, [str(md)], {"Page size": "A4", "Orientation": "Portrait", "Font": "Segoe UI",
                                            "Font size": "10.5", "Page numbers (Page 1 of N)": True}, str(o), {})
        import pymupdf
        with pymupdf.open(r["files"][0]) as d:
            text = d[0].get_text()
        assert "खातेदाराचे" in text and "1,00,000" in text
        r2 = runners.pdf2md(job, [r["files"][0]], {"OCR for scanned pages": "Off", "Pages": ""}, str(o), {})
        assert "1,00,000" in Path(r2["files"][0]).read_text(encoding="utf-8")
        return "Markdown to PDF (Hindi/Marathi) and back"
    c.run("Markdown to PDF / PDF to Markdown", markdown)

    conv_opts = {"Worksheets": "Combine continued tables", "Word mode": "Editable document",
                 "Indian number format (1,00,000)": True, "OCR for scanned pages": "Automatic (recommended)",
                 "OCR language": "English", "Pages": "", "One workbook for all PDFs": False}

    def to_excel_word():
        o = out / "convert"
        o.mkdir(exist_ok=True)
        src = inputs / "selftest.pdf"
        src.write_bytes((assets / "selftest.pdf").read_bytes())
        r = runners.to_both(job, [str(src)], conv_opts, str(o), {})
        xlsx = next(f for f in r["files"] if f.endswith(".xlsx"))
        docx = next(f for f in r["files"] if f.endswith(".docx"))
        from openpyxl import load_workbook
        from docx import Document
        assert any(ws.max_row > 1 for ws in load_workbook(xlsx).worksheets)
        assert Document(docx).paragraphs or Document(docx).tables
        return "; ".join(r["details"])
    c.run("PDF to Excel & Word", to_excel_word)

    def bank():
        o = out / "convert"
        o.mkdir(exist_ok=True)
        src = inputs / "selftest_statement.pdf"
        src.write_bytes((assets / "selftest_statement.pdf").read_bytes())
        r = runners.bank(job, [str(src)], conv_opts, str(o), {})
        assert "21 transactions" in r["details"][0] and "every row proven" in r["details"][0], r["details"]
        return r["details"][0]
    c.run("Bank Statement to Excel (balance-checked)", bank)

    def redaction_text():
        from .services import redaction as rd
        o = out / "redaction"
        o.mkdir(exist_ok=True)
        src = _kyc(inputs / "Client KYC.pdf")
        found = rd.scan(job, src, "", rd.CATEGORIES)
        vals = sorted(r["text"] for r in found["results"])
        assert vals == ["+91 98765 43210", "50100123456789", "ABCPK1234Q"], vals
        res = rd.apply(job, src, "", {0: [r["rect"] for r in found["results"]]}, o / "Client KYC_redacted.pdf",
                       terms=vals)
        assert not res["failed"], [x for x in res["checks"] if x[0] == "FAIL"]
        return f"{len(vals)} items found, removed and verified ({len(res['checks'])} checks)"
    c.run("Secure Redaction (text PDF)", redaction_text)

    def redaction_scan_in_worker():
        """Same path as the screen: a heavy job in a spawned worker process via the JobRunner."""
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        from .jobs import JobRunner
        from .services import redaction as rd
        QApplication.instance() or QApplication([])
        src = _scan_of(KYC_LINES, inputs / "Scanned KYC.pdf")
        runner = JobRunner()
        loop = QEventLoop()
        box = {}
        runner.finished.connect(lambda s, p: (box.update(status=s, payload=p), loop.quit()))
        runner.start(rd.scan, {"path": str(src), "password": "", "categories": ["PAN", "Bank account numbers"],
                               "ocr_lang": "eng+hin+mar"}, heavy=True)
        QTimer.singleShot(300000, loop.quit)
        loop.exec()
        assert box.get("status") == "ok", f"worker: {box}"
        found = box["payload"]
        vals = {r["text"] for r in found["results"]}
        assert {"ABCPK1234Q", "50100123456789"} <= vals, vals
        o = out / "redaction"
        o.mkdir(exist_ok=True)
        res = rd.apply(Job(), src, "", {0: [r["rect"] for r in found["results"]]}, o / "Scanned KYC_redacted.pdf",
                       terms=sorted(vals), ocr_lang="eng")
        oc = [x for x in res["checks"] if "OCR" in x[1]]
        assert not res["failed"] and oc and oc[0][0] == "PASS", res["checks"]
        QCoreApplication.processEvents()
        return "OCR in a worker process found PAN and account number; redacted; OCR re-check PASS"
    c.run("Secure Redaction (scanned PDF, worker process)", redaction_scan_in_worker)

    def hindi_ocr():
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QImage, QPainter, QColor
        from PySide6.QtWidgets import QApplication
        from PIL import Image
        from .services import ocr
        QApplication.instance() or QApplication([])
        img = QImage(1400, 200, QImage.Format.Format_RGB888)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setFont(QFont("Nirmala UI", 40))
        p.setPen(QColor("black"))
        p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "खाते विवरण भारत सरकार")
        p.end()
        buf = io.BytesIO()
        ba = img.bits().tobytes() if hasattr(img.bits(), "tobytes") else bytes(img.constBits())
        pil = Image.frombuffer("RGB", (img.width(), img.height()), ba, "raw", "RGB", img.bytesPerLine(), 1)
        pil.save(buf, "PNG")
        text = ocr.image_to_text(Image.open(io.BytesIO(buf.getvalue())), lang="hin+mar", psm=6)
        assert "भारत" in text or "सरकार" in text, repr(text)
        return f"read: {text.strip()[:40]}"
    c.run("Hindi / Marathi OCR", hindi_ocr)

    def worker_process():
        import multiprocessing as mp
        flag = work / "worker_probe.txt"
        ctx = mp.get_context("spawn")
        pr = ctx.Process(target=_worker_probe, args=(str(flag),))
        pr.start()
        pr.join(120)
        assert flag.is_file(), f"worker did not run (exit code {pr.exitcode})"
        return flag.read_text(encoding="utf-8")
    c.run("Worker process start", worker_process)

    def bad_input():
        msgs = []
        for fn, args in ((runners.extract, ([str(a)], {"Pages": "9"})),
                         (runners.extract, ([str(inputs / "missing file.pdf")], {"Pages": "1"}))):
            try:
                fn(job, args[0], args[1], str(out), {})
                raise AssertionError("no error for bad input")
            except UserError as exc:
                msgs.append(str(exc).splitlines()[0])
        fake = inputs / "not really.pdf"
        fake.write_text("hello", encoding="utf-8")
        try:
            runners.split(job, [str(fake)], {"Split by": "Every page"}, str(out), {})
            raise AssertionError("no error for a non-PDF file")
        except UserError as exc:
            msgs.append(str(exc).splitlines()[0])
        return " | ".join(msgs)
    c.run("Clear messages for bad input", bad_input)

    def large_pdf():
        o = out / "large"
        o.mkdir(exist_ok=True)
        big = _pdf(inputs / "Large 300 pages.pdf", 300)
        r = runners.rotate(job, [str(big)], {"Rotate which pages": "Even pages only", "Direction": "180° (upside down)",
                                             "Page numbers": ""}, str(o), {})
        rots = _rotations(r["files"][0])
        assert len(rots) == 300 and rots[1] == 180 and rots[0] == 0
        s = runners.split(job, [str(big)], {"Split by": "Every N pages", "N (pages per file)": 50, "Page ranges": ""},
                          str(o), {})
        assert len(s["files"]) == 6
        return "300-page PDF rotated and split into 6 parts"
    c.run("Large PDF (300 pages)", large_pdf)

    def protected_folder():
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return "skipped - running as administrator (would be able to write to C:\\Windows)"
        from .jobs import run_function
        target = os.environ.get("SystemRoot", r"C:\Windows")
        status, msg = run_function(runners.extract, {"files": [str(a)], "opts": {"Pages": "1"}, "out_dir": target,
                                                     "passwords": {}}, lambda *x: None, lambda: False)
        written = list(Path(target).glob("Invoice A (1)_extract*.pdf")) + list(Path(target).glob(".Invoice A*.part"))
        assert status == "error" and not written, f"status={status}, files={written}"
        assert "denied" in str(msg).lower(), msg
        return f"refused, nothing written; message shown: {str(msg).splitlines()[0][:110]}"
    c.run("Folder without write permission", protected_folder)

    lines = [f"{APP_NAME} {APP_VERSION} - self-test {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Work folder: {work}", ""]
    for status, name, detail, secs in c.rows:
        lines.append(f"{status:<5} {name}  ({secs:.1f} s)")
        if detail:
            lines.append(f"      {detail}")
    lines += ["", f"RESULT: {len(c.rows) - c.failed} of {len(c.rows)} passed"
              + (" - ALL PASSED" if not c.failed else f" - {c.failed} FAILED")]
    report = "\n".join(lines)
    for target in (work / "selftest_report.txt",
                   Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PDF Play Station 2.0" / "selftest_report.txt"):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report, encoding="utf-8")
        except OSError:
            pass
    if sys.stdout is not None:
        try:
            print(report)
        except Exception:
            pass
    code = 0 if not c.failed else 1
    # Close the self-test's hidden Qt windows, then end the process directly. A frozen
    # EXE otherwise tears Qt down during interpreter shutdown in arbitrary order, which
    # can end in a crash *after* the report has been written (seen as 0xC0000409).
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            for w in app.topLevelWidgets():
                w.close()
                w.deleteLater()
            app.processEvents()
    except Exception:
        pass
    import logging
    logging.shutdown()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(code)
