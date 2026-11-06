"""Section 1 engines: merge, split, extract, page numbers, rearrange, rotate,
PDF <-> images and passwords. Ported from the earlier PDF Play Station (v1.1.0)
and extended (Rotate PDF, sideways-page detection, image orientation)."""

from __future__ import annotations

import io
import math
import secrets
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence

import pymupdf

from . import ocr
from .common import (Job, Result, UserError, open_pdf, page_runs, same_path, save_pdf, write_atomic)

POSITIONS = ["Bottom centre", "Bottom right", "Bottom left", "Top centre", "Top right", "Top left"]
NUMBER_FORMATS = ["1", "Page 1", "Page 1 of N", "1 / N"]
FULL_PERMISSIONS = (pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_COPY |
                    pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ACCESSIBILITY |
                    pymupdf.PDF_PERM_ASSEMBLE | pymupdf.PDF_PERM_PRINT_HQ)


def copy_pages(src: pymupdf.Document, pages: Sequence[int]) -> pymupdf.Document:
    out = pymupdf.open()
    for a, b in page_runs(pages):
        out.insert_pdf(src, from_page=a - 1, to_page=b - 1)
    return out


def _name(path) -> str:
    return Path(path).name


# ------------------------------------------------------------------ merge / split / extract

def merge(job: Job, inputs: list[tuple[str, str]], out_path, bookmarks: bool = True) -> Result:
    """inputs: [(path, password)] in the order to merge."""
    for path, _pw in inputs:
        if same_path(path, out_path):
            raise UserError(f"The output file is also one of the input files:\n{path}")
    out = pymupdf.open()
    toc: list[list] = []
    try:
        n = len(inputs)
        for i, (path, pw) in enumerate(inputs):
            job.step(i, n + 1, f"Adding {_name(path)}")
            src = open_pdf(path, pw)
            try:
                offset = out.page_count
                out.insert_pdf(src)
                if bookmarks:
                    toc.append([1, Path(path).stem, offset + 1])
                    for lvl, title, page in src.get_toc(simple=True):
                        if page > 0:
                            toc.append([lvl + 1, title, page + offset])
            finally:
                src.close()
        if toc:
            try:
                out.set_toc(toc)
            except Exception:
                out.set_toc([t for t in toc if t[0] == 1])
        job.step(n, n + 1, "Saving merged PDF")
        pages = out.page_count
        save_pdf(out, out_path)
    finally:
        out.close()
    return Result([str(out_path)], f"{len(inputs)} PDFs merged into one file of {pages} pages.")


def split(job: Job, src_path, password: str, groups: list[list[int]], out_paths: list) -> Result:
    src = open_pdf(src_path, password)
    try:
        for i, (grp, path) in enumerate(zip(groups, out_paths)):
            job.step(i, len(groups), f"Creating part {i + 1} of {len(groups)}")
            part = copy_pages(src, grp)
            try:
                save_pdf(part, path)
            finally:
                part.close()
    finally:
        src.close()
    return Result([str(p) for p in out_paths], f"'{_name(src_path)}' split into {len(out_paths)} file(s).")


def extract(job: Job, src_path, password: str, pages: list[int], out_path) -> Result:
    src = open_pdf(src_path, password)
    try:
        job.step(0, 2, "Extracting pages")
        out = copy_pages(src, pages)
        try:
            job.step(1, 2, "Saving")
            save_pdf(out, out_path)
        finally:
            out.close()
    finally:
        src.close()
    return Result([str(out_path)], f"{len(pages)} page(s) extracted from '{_name(src_path)}'.")


def rearrange(job: Job, src_path, password: str, order: list[tuple[int, int]], out_path) -> Result:
    """order: [(one-based page, extra clockwise rotation)] - pages left out are deleted."""
    if not order:
        raise UserError("Every page was removed - at least one page must remain.")
    src = open_pdf(src_path, password)
    try:
        total = src.page_count
        job.step(0, 2, "Rearranging pages")
        out = copy_pages(src, [p for p, _r in order])
        try:
            for i, (_p, turn) in enumerate(order):
                if turn % 360:
                    out[i].set_rotation((out[i].rotation + turn) % 360)
            job.step(1, 2, "Saving")
            save_pdf(out, out_path)
        finally:
            out.close()
    finally:
        src.close()
    removed = total - len({p for p, _r in order})
    turned = sum(1 for _p, r in order if r % 360)
    bits = [f"{len(order)} page(s) in the new order"]
    if removed:
        bits.append(f"{removed} removed")
    if turned:
        bits.append(f"{turned} rotated")
    return Result([str(out_path)], "Pages rearranged: " + ", ".join(bits) + ".")


# ------------------------------------------------------------------ page numbers

def number_label(fmt: str, number: int, total: int) -> str:
    if fmt == "Page 1":
        return f"Page {number}"
    if fmt == "Page 1 of N":
        return f"Page {number} of {total}"
    if fmt == "1 / N":
        return f"{number} / {total}"
    return str(number)


def add_page_numbers(job: Job, src_path, password: str, out_path, pages: list[int], position: str,
                     start_no: int, fmt: str, font_size: float, margin: float = 24.0,
                     colour=(0, 0, 0), bold: bool = False) -> Result:
    """Running numbers on the chosen pages: shown number = start_no + position within
    the selection; N = total pages of the document. Works on rotated pages."""
    doc = open_pdf(src_path, password)
    try:
        total = doc.page_count
        font = "hebo" if bold else "helv"
        vpos, hpos = position.lower().split()
        for k, pno in enumerate(pages):
            if k % 10 == 0:
                job.step(k, len(pages) + 1, f"Numbering page {pno}")
            page = doc[pno - 1]
            try:
                if not page.is_wrapped:          # isolate the existing graphics state
                    page.wrap_contents()
            except Exception:
                pass
            text = number_label(fmt, start_no + k, total)
            r = page.rect                         # visible (rotation-adjusted) area
            width = pymupdf.get_text_length(text, fontname=font, fontsize=font_size)
            x = (r.x0 + margin if hpos == "left" else r.x1 - margin - width if hpos == "right"
                 else r.x0 + (r.width - width) / 2.0)
            y = r.y0 + margin + font_size * 0.8 if vpos == "top" else r.y1 - margin
            page.insert_text(pymupdf.Point(x, y) * page.derotation_matrix, text, fontsize=font_size,
                             fontname=font, color=colour, rotate=page.rotation)
        job.step(len(pages), len(pages) + 1, "Saving")
        save_pdf(doc, out_path)
    finally:
        doc.close()
    return Result([str(out_path)], f"Page numbers added to {len(pages)} page(s) of '{_name(src_path)}'.")


# ------------------------------------------------------------------ rotate

DIRECTIONS = {"90° clockwise": 90, "90° anticlockwise": 270, "180° (upside down)": 180}
TURN_WORDS = {90: "90° clockwise", 180: "180°", 270: "90° anticlockwise"}


def pages_for(which: str, total: int, selected: Optional[list[int]] = None) -> list[int]:
    if which == "All pages":
        return list(range(1, total + 1))
    if which == "Odd pages only":
        return list(range(1, total + 1, 2))
    if which == "Even pages only":
        return list(range(2, total + 1, 2))
    if which == "Selected pages":
        if not selected:
            raise UserError("Enter the page numbers to rotate, e.g. 2, 5-7, 10.")
        return selected
    raise UserError(f"Unknown page choice: {which}")


def apply_turns(job: Job, src_path, password: str, out_path, turns: dict[int, int]) -> Result:
    """turns: {one-based page: clockwise degrees}. Only the page's /Rotate value is
    changed - the content is not redrawn, so quality is untouched."""
    if not turns:
        raise UserError("There are no pages to rotate.")
    doc = open_pdf(src_path, password)
    try:
        n = len(turns)
        for i, (pno, deg) in enumerate(sorted(turns.items())):
            if i % 20 == 0:
                job.step(i, n + 1, f"Rotating page {pno}")
            page = doc[pno - 1]
            page.set_rotation((page.rotation + deg) % 360)
        job.step(n, n + 1, "Saving")
        save_pdf(doc, out_path)
    finally:
        doc.close()
    counts = Counter(turns.values())
    how = ", ".join(f"{c} page(s) {TURN_WORDS.get(d, f'{d}°')}" for d, c in sorted(counts.items()))
    return Result([str(out_path)], f"'{_name(src_path)}': {how}.")


def _text_turn(page: pymupdf.Page) -> tuple[Optional[int], int]:
    """Clockwise turn that makes a page with a text layer upright, from the writing
    direction of its text (weighted by characters). (None, 0) without text.

    Text directions are reported in unrotated page space; text at angle t (anti-
    clockwise) reads upright when the page's /Rotate equals t."""
    weights: Counter = Counter()
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            n = sum(len(s["text"].strip()) for s in line["spans"])
            if not n:
                continue
            dx, dy = line["dir"]
            angle = int(round(math.degrees(math.atan2(-dy, dx)) / 90.0)) * 90 % 360
            weights[angle] += n
    if sum(weights.values()) < 20:
        return None, 0
    angle, n = weights.most_common(1)[0]
    if n < 0.6 * sum(weights.values()):
        return None, 0                       # mixed directions (e.g. a rotated table header)
    return (angle - page.rotation) % 360, n


def detect_sideways(job: Job, src_path, password: str) -> dict:
    """Find pages that are not upright. Returns {"turns": {page: cw}, "undecided": [pages],
    "methods": {page: text|ocr}}. Text pages use their text direction (exact);
    scanned pages use Tesseract's orientation check."""
    from PIL import Image
    doc = open_pdf(src_path, password)
    turns, methods, undecided = {}, {}, []
    try:
        n = doc.page_count
        for i in range(n):
            job.step(i, n, f"Checking page {i + 1} of {n}")
            page = doc[i]
            turn, _weight = _text_turn(page)
            method = "text"
            if turn is None:
                method = "ocr"
                pix = page.get_pixmap(dpi=150, alpha=False)          # as displayed (rotation applied)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                turn, conf = ocr.orientation(img, dpi=150)
                if turn is not None and conf < 2.0:
                    turn = None
            if turn is None:
                undecided.append(i + 1)
            elif turn:
                turns[i + 1] = turn
                methods[i + 1] = method
    finally:
        doc.close()
    return {"turns": turns, "undecided": undecided, "methods": methods, "pages": n}


# ------------------------------------------------------------------ images

def pdf_to_images(job: Job, src_path, password: str, pages: list[int], out_paths: list, img_format: str,
                  dpi: int, jpg_quality: int = 90) -> Result:
    doc = open_pdf(src_path, password)
    try:
        for i, (pno, path) in enumerate(zip(pages, out_paths)):
            job.step(i, len(pages), f"Page {pno} ({i + 1} of {len(pages)})")
            pix = doc[pno - 1].get_pixmap(dpi=dpi, alpha=False)
            data = pix.tobytes("jpg", jpg_quality=jpg_quality) if img_format == "JPEG" else pix.tobytes("png")
            write_atomic(Path(path), data)
            pix = None
    finally:
        doc.close()
    return Result([str(p) for p in out_paths],
                  f"{len(out_paths)} page(s) of '{_name(src_path)}' saved as {img_format} at {dpi} dpi.")


def _image_frames(path: str):
    """Yield (PNG/JPEG bytes, width, height) per frame, upright per the photo's EXIF
    orientation (phone photos) and with every page of a multi-page TIFF."""
    from PIL import Image, ImageOps, ImageSequence
    try:
        im = Image.open(path)
    except Exception as exc:
        raise UserError(f"'{_name(path)}' is not a supported image ({exc}).")
    with im:
        for frame in ImageSequence.Iterator(im):
            fr = ImageOps.exif_transpose(frame.copy())
            if fr.mode not in ("RGB", "L"):
                fr = fr.convert("RGB")
            buf = io.BytesIO()
            if fr.mode == "RGB" and Path(path).suffix.lower() in (".jpg", ".jpeg"):
                fr.save(buf, "JPEG", quality=92)
            else:
                fr.save(buf, "PNG")
            yield buf.getvalue(), fr.width, fr.height


def images_to_pdf(job: Job, paths: list[str], out_path, page_size: str = "A4",
                  orientation: str = "Automatic", margin: float = 28.0) -> Result:
    """page_size: A4 | Letter | Fit to image. The aspect ratio is always kept."""
    out = pymupdf.open()
    try:
        for i, path in enumerate(paths):
            job.step(i, len(paths) + 1, f"Adding {_name(path)}")
            for data, w_px, h_px in _image_frames(path):
                if page_size == "Fit to image":
                    w, h = w_px * 72.0 / 150, h_px * 72.0 / 150       # treated as 150 dpi
                    page = out.new_page(width=w, height=h)
                    page.insert_image(page.rect, stream=data)
                    continue
                paper = pymupdf.paper_rect("a4" if page_size == "A4" else "letter")
                w, h = paper.width, paper.height
                landscape = (w_px > h_px) if orientation == "Automatic" else orientation == "Landscape"
                if landscape:
                    w, h = h, w
                page = out.new_page(width=w, height=h)
                page.insert_image(pymupdf.Rect(margin, margin, w - margin, h - margin), stream=data,
                                  keep_proportion=True)
        job.step(len(paths), len(paths) + 1, "Saving")
        pages = out.page_count
        save_pdf(out, out_path)
    finally:
        out.close()
    return Result([str(out_path)], f"{len(paths)} image file(s) combined into a {pages}-page PDF.")


# ------------------------------------------------------------------ passwords

def protect(job: Job, src_path, password: str, out_path, open_pw: str, owner_pw: str = "",
            allow_print: bool = True, allow_copy: bool = False, allow_edit: bool = False) -> Result:
    if not open_pw:
        raise UserError("Enter a password.")
    if same_path(src_path, out_path):
        raise UserError("The output must be a new file.")
    restricted = not (allow_print and allow_copy and allow_edit)
    doc = open_pdf(src_path, password)
    try:
        job.step(0, 3, "Encrypting with AES-256")
        if restricted:
            perms = pymupdf.PDF_PERM_ACCESSIBILITY
            if allow_print:
                perms |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
            if allow_copy:
                perms |= pymupdf.PDF_PERM_COPY
            if allow_edit:
                perms |= (pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ASSEMBLE | pymupdf.PDF_PERM_ANNOTATE |
                          pymupdf.PDF_PERM_FORM)
            # restrictions need a different owner password, or anyone who opens the file could lift them
            owner = owner_pw if owner_pw and owner_pw != open_pw else secrets.token_urlsafe(24)
        else:
            perms, owner = FULL_PERMISSIONS, owner_pw or open_pw
        save_pdf(doc, out_path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=owner, user_pw=open_pw,
                 permissions=perms)
    finally:
        doc.close()
    job.step(2, 3, "Verifying the protected file")
    with pymupdf.open(str(out_path)) as check:
        if not check.needs_pass:
            raise UserError("Verification failed: the output opens without a password.")
        if not check.authenticate(open_pw):
            raise UserError("Verification failed: the output does not open with the password.")
    warn = []
    if restricted and not (owner_pw and owner_pw != open_pw):
        warn.append("No separate permissions password was given, so a random one was used: the "
                    "restrictions cannot be lifted later (the open password still works).")
    allowed = [n for n, a in (("printing", allow_print), ("copying", allow_copy), ("editing", allow_edit)) if a]
    return Result([str(out_path)], f"'{_name(src_path)}' protected with AES-256 and verified. "
                  f"Allowed: {', '.join(allowed) or 'nothing beyond viewing'}.", warn)


def remove_password(job: Job, src_path, out_path, password: str) -> Result:
    """Uses a known password only (no recovery or cracking). Owner password -> all
    security removed. Open password only -> open password removed, restrictions kept."""
    if same_path(src_path, out_path):
        raise UserError("The output must be a new file.")
    try:
        doc = pymupdf.open(str(src_path))
    except Exception as exc:
        raise UserError(f"'{_name(src_path)}' could not be opened ({exc}).")
    try:
        protected = doc.needs_pass or doc.is_encrypted or bool((doc.metadata or {}).get("encryption"))
        if not protected:
            raise UserError(f"'{_name(src_path)}' is not password-protected.")
        job.step(0, 2, "Checking password")
        rc = doc.authenticate(password or "")
        if rc == 0:
            raise UserError(f"The password for '{_name(src_path)}' is incorrect.")
        job.step(1, 2, "Saving decrypted copy")
        if rc & 4 or (doc.permissions & FULL_PERMISSIONS) == FULL_PERMISSIONS:
            save_pdf(doc, out_path, encryption=pymupdf.PDF_ENCRYPT_NONE)
            msg = f"'{_name(src_path)}': password protection removed. The new PDF is not encrypted."
        elif rc & 2 and password:
            save_pdf(doc, out_path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=secrets.token_urlsafe(24),
                     user_pw="", permissions=doc.permissions)
            msg = (f"'{_name(src_path)}': open password removed. Print/copy/edit restrictions were kept "
                   "because the password entered is not the owner (permissions) password.")
        else:
            raise UserError(f"'{_name(src_path)}' has permission restrictions only. Enter its owner "
                            "(permissions) password to remove them.")
    finally:
        doc.close()
    return Result([str(out_path)], msg)
