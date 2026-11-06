"""Synthetic test PDFs (no real client data) built with ReportLab and Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STYLES = getSampleStyleSheet()

FINANCIAL_ROWS = [
    ["Particulars", "Account No", "Amount", "Change", "Date"],
    ["Opening balance", "000123", "1,25,000.50", "12.5%", "01/04/2024"],
    ["Interest earned", "004567", "2,345.75", "-3.25%", "15/05/2024"],
    ["Bank charges", "000089", "(1,200.00)", "0%", "30/06/2024"],
    ["Refund", "123456789012", "-450.10", "100%", "31-Mar-2025"],
    ["PAN ABCDE1234F", "27ABCDE1234F1Z5", "0", "", "31/02/2024"],
]


def simple_text_pdf(path: Path) -> Path:
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = [
        Paragraph("Annual Compliance Note", STYLES["Title"]),
        Paragraph("Introduction", STYLES["Heading2"]),
        Paragraph("This synthetic document is used to test text extraction. It contains <b>bold words</b>, "
                  "<i>italic words</i> and a link to <a href='https://example.com' color='blue'>example.com</a>. "
                  "The paragraph is long enough to wrap across several lines so that line joining can be "
                  "verified by the automated tests in this project.", STYLES["BodyText"]),
        Spacer(1, 12),
        ListFlowable([ListItem(Paragraph("First bullet point", STYLES["BodyText"])),
                      ListItem(Paragraph("Second bullet point", STYLES["BodyText"]))], bulletType="bullet"),
        Paragraph("Conclusion", STYLES["Heading2"]),
        Paragraph("No tables appear in this document. The end.", STYLES["BodyText"]),
    ]
    doc.build(story)
    return path


def table_pdf(path: Path) -> Path:
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    table = Table(FINANCIAL_ROWS)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    doc.build([Paragraph("Statement of Account", STYLES["Heading1"]), table,
               Paragraph("Figures are synthetic.", STYLES["BodyText"])])
    return path


def multipage_table_pdf(path: Path, rows: int = 120) -> Path:
    data = [["Sr", "Description", "Debit", "Credit"]]
    for i in range(1, rows + 1):
        data.append([str(i), f"Transaction {i:03d}", f"{i * 10:,}.00", f"{i * 3}.50"])
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([table])
    return path


def borderless_table_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, 27 * cm, "Bank Statement (synthetic)")
    c.setFont("Helvetica", 10)
    xs = [2 * cm, 5 * cm, 12 * cm, 15 * cm, 18.5 * cm]
    header = ["Date", "Narration", "Debit", "Credit", "Balance"]
    rows = [["01/04/2024", "Opening", "", "", "10,000.00"],
            ["02/04/2024", "NEFT ACME LTD", "", "5,000.00", "15,000.00"],
            ["05/04/2024", "ATM WDL", "2,500.00", "", "12,500.00"],
            ["09/04/2024", "CHQ 000456", "1,234.56", "", "11,265.44"]]
    y = 25 * cm
    for ci, h in enumerate(header):
        c.drawRightString(xs[ci] + 2 * cm, y, h) if ci >= 2 else c.drawString(xs[ci], y, h)
    for row in rows:
        y -= 0.7 * cm
        for ci, v in enumerate(row):
            if ci >= 2:
                c.drawRightString(xs[ci] + 2 * cm, y, v)
            else:
                c.drawString(xs[ci], y, v)
    c.drawString(2 * cm, y - 2 * cm, "This statement is computer generated and synthetic.")
    c.save()
    return path


def wide_rows(ncols: int, nrows: int) -> list[list[str]]:
    rows = [["Account"] + [f"M{i:02d}" for i in range(1, ncols)]]
    for r in range(1, nrows + 1):
        rows.append([f"ACC{r:04d}"] + [f"{(r * c * 137) % 99999:,}.{c:02d}" if c % 4 else f"({r * c}.50)"
                                       for c in range(1, ncols)])
    return rows


def wide_ruled_pdf(path: Path, ncols: int = 22, nrows: int = 60) -> Path:
    table = Table(wide_rows(ncols, nrows), repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 6)]))
    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=15, rightMargin=15).build([table])
    return path


def wide_borderless_pdf(path: Path, ncols: int = 24, nrows: int = 30) -> Path:
    """Dense statement: 6.5 pt font, right-aligned amounts only ~0.5 em apart."""
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    c.setFont("Helvetica", 6.5)
    for ri, row in enumerate(wide_rows(ncols, nrows)):
        y = 560 - ri * 11
        for ci, v in enumerate(row):
            if ci == 0:
                c.drawString(20, y, v)
            else:
                c.drawRightString(50 + ci * 33.5, y, v)
    c.save()
    return path


def indian(n) -> str:
    """12345678.5 -> '1,23,45,678.50'"""
    s = f"{n:.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{whole}.{frac}"


def statement_transactions(n: int = 46, seed: int = 7):
    """Deterministic synthetic transactions: (date, particulars, chq, withdrawal, deposit, balance)."""
    import random
    from datetime import date, timedelta
    rnd = random.Random(seed)
    names = ["NEFT/ACME TRADERS PVT LTD", "IMPS/912345678901/ALPHA SUPPLIES", "CASH RECEIPT",
             "IB/GST/ANDB19042700160526/31718600", "Inst26782 Clg STATE BANK OF INDIA",
             "IB/BILLDESK/QADB7426953807/FKPAYMENTS", "BY INT FOR THE PERIOD", "SMS Charges for Quarter",
             "NEFT/ANDBN19234167933 / Office Rent", "UPI/925413341470/CR/VENDOR"]
    bal = 62740.16
    rows = [("", "B/F", "", None, bal, bal)]
    day = date(2019, 4, 2)
    for i in range(n):
        day += timedelta(days=rnd.randint(0, 4))
        deposit = rnd.random() < 0.45
        amt = round(rnd.choice([rnd.uniform(1, 999), rnd.uniform(1000, 99999), rnd.uniform(100000, 900000)]), 2)
        if not deposit and amt > bal:
            deposit = True
        bal = round(bal + amt if deposit else bal - amt, 2)
        chq = str(40 + i) if rnd.random() < 0.1 else ""
        rows.append((day.strftime("%d-%m-%Y"), rnd.choice(names), chq, None if deposit else amt,
                     amt if deposit else None, bal))
    return rows


def bank_statement_pdf(path: Path, rows=None, offset: bool = True, per_page: int = 24) -> Path:
    """Finacle-style statement: amounts printed slightly above their description
    (offset=True), 'Cumulative Totals' after every page, header repeated."""
    rows = rows or statement_transactions()
    c = canvas.Canvas(str(path), pagesize=A4)
    x_date, x_part, x_chq, x_w, x_d, x_b = 40, 110, 360, 435, 510, 585
    pitch = 17
    tw = td = 0.0

    def header(y):
        c.setFont("Courier", 7.5)
        c.drawString(x_date, y, "DATE")
        c.drawString(x_part, y, "PARTICULARS")
        c.drawString(x_chq - 10, y, "CHQ.NO.")
        c.drawRightString(x_w, y, "WITHDRAWALS")
        c.drawRightString(x_d, y, "DEPOSITS")
        c.drawRightString(x_b - 15, y, "BALANCE")
        c.line(x_date, y - 4, x_b + 5, y - 4)

    def page_start(first):
        c.setFont("Courier", 7.5)
        if first:
            c.drawString(200, 800, "SYNTHETIC BANK OF TESTING")
            c.drawString(40, 780, "TO: M/S EXAMPLE TRADING COMPANY")
            c.drawString(40, 768, "STATEMENT OF ACCOUNT FOR THE PERIOD FROM 01-04-2019 to 31-03-2020")
        header(740)
        return 715

    y = page_start(True)
    for k, (dt, part, chq, w, d, b) in enumerate(rows):
        if k and k % per_page == 0:
            c.setFont("Courier", 7.5)
            c.drawString(x_part - 40, y - 4, "Cumulative Totals:")
            c.drawRightString(x_w, y + (4 if offset else 0), indian(tw))
            c.drawRightString(x_d, y + (4 if offset else 0), indian(td))
            c.drawRightString(x_b, y + (4 if offset else 0), indian(b_prev) + "Cr")
            c.drawString(40, y - 30, "08-03-2022")
            c.showPage()
            y = page_start(False)
        c.setFont("Courier", 7.5)
        dy = 6 if offset else 0
        c.drawString(x_date, y, dt)
        c.drawString(x_part if dt else x_part + 30, y, part)
        if chq:
            c.drawString(x_chq, y, chq)
        if w is not None:
            c.drawRightString(x_w, y + dy, indian(w))
            tw += w
        if d is not None:
            c.drawRightString(x_d, y + dy, indian(d))
            td += d
        c.drawRightString(x_b, y + dy, indian(b) + "Cr")
        b_prev = b
        y -= pitch
    c.setFont("Courier", 7.5)
    c.drawString(x_part - 40, y - 4, "Cumulative Totals:")
    c.drawRightString(x_w, y + 4, indian(tw))
    c.drawRightString(x_d, y + 4, indian(td))
    c.drawRightString(x_b, y + 4, indian(b_prev) + "Cr")
    c.save()
    return path


def scanned_copy(src: Path, dst: Path, dpi: int = 200, seed: int = 3) -> Path:
    """Render a PDF to greyscale images with light noise and a slight blur,
    and save them as an image-only PDF (simulates a scan)."""
    import random
    import pypdfium2 as pdfium
    from PIL import ImageFilter
    rnd = random.Random(seed)
    pdf = pdfium.PdfDocument(str(src))
    images = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=dpi / 72).to_pil().convert("L").filter(ImageFilter.GaussianBlur(0.5))
        px = img.load()
        for _ in range(img.width * img.height // 1500):
            px[rnd.randrange(img.width), rnd.randrange(img.height)] = rnd.choice((0, 200))
        images.append(img.convert("RGB"))
    images[0].save(dst, save_all=True, append_images=images[1:], resolution=dpi)
    return dst


def _text_image(lines: list[str], size=(1654, 2339)) -> Image.Image:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    y = 150
    for line in lines:
        draw.text((150, y), line, fill="black", font=font)
        y += 80
    return img


def scanned_pdf(path: Path, tmp_dir: Path) -> Path:
    img_path = tmp_dir / "scan_page.png"
    _text_image(["SCANNED INVOICE", "Invoice number 4521", "Total amount 1,234.50"]).save(img_path)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(str(img_path), 0, 0, width=A4[0], height=A4[1])
    c.save()
    return path


def mixed_pdf(path: Path, tmp_dir: Path) -> Path:
    img_path = tmp_dir / "mixed_page.png"
    _text_image(["SCANNED SECOND PAGE"]).save(img_path)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 750, "This first page has real, extractable text content for testing.")
    c.showPage()
    c.drawImage(str(img_path), 0, 0, width=A4[0], height=A4[1])
    c.save()
    return path


def landscape_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    c.drawString(72, 500, "A landscape page used to test page orientation in Word output.")
    c.save()
    return path


def encrypted_pdf(path: Path, password: str = "secret123") -> Path:
    enc = StandardEncryption(password, ownerPassword="owner-" + password, strength=128)
    c = canvas.Canvas(str(path), pagesize=A4, encrypt=enc)
    c.drawString(72, 750, "Confidential synthetic content behind a password.")
    c.save()
    return path


def corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n%garbage that is not a real PDF structure\n" + b"\x00" * 200)
    return path


def not_a_pdf(path: Path) -> Path:
    path.write_text("This is a plain text file renamed to .pdf", encoding="utf-8")
    return path


def two_column_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 790, "Two Column Newsletter")
    c.setFont("Helvetica", 10)
    left = [f"Left column sentence number {i} continues here." for i in range(1, 16)]
    right = [f"Right column line {i} has other words." for i in range(1, 16)]
    y = 750
    for l, r in zip(left, right):
        c.drawString(56, y, l)
        c.drawString(310, y, r)
        y -= 14
    c.save()
    return path
