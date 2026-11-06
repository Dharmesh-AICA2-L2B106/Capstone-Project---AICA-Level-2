import io

import pymupdf
import pytest
from PIL import Image

from app.services import utilities as ut
from app.services.common import PasswordRequired, UserError, open_pdf
from helpers import LINE, make_pdf, page_markers, requires_tesseract, rotations


# ------------------------------------------------------------------ merge / split / extract

def test_merge_order_and_bookmarks(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 2, toc=True)
    b = make_pdf(tmp_path / "b.pdf", 3)
    out = tmp_path / "m.pdf"
    r = ut.merge(job, [(str(b), ""), (str(a), "")], out)
    assert page_markers(out) == ["MARKER-001", "MARKER-002", "MARKER-003", "MARKER-001", "MARKER-002"]
    with pymupdf.open(str(out)) as d:
        toc = d.get_toc()
    assert [t[1] for t in toc if t[0] == 1] == ["b", "a"]
    assert ["Chapter 1", 4] in [[t[1], t[2]] for t in toc if t[0] == 2]
    assert "5 pages" in r.message


def test_merge_refuses_to_overwrite_input(tmp_path, job):
    a = make_pdf(tmp_path / "a.pdf", 1)
    with pytest.raises(UserError):
        ut.merge(job, [(str(a), "")], a)


def test_split_and_extract(tmp_path, job, pdf5):
    outs = [tmp_path / "p1.pdf", tmp_path / "p2.pdf"]
    ut.split(job, pdf5, "", [[1, 2], [5, 4]], outs)
    assert page_markers(outs[0]) == ["MARKER-001", "MARKER-002"]
    assert page_markers(outs[1]) == ["MARKER-005", "MARKER-004"]
    ex = tmp_path / "ex.pdf"
    ut.extract(job, pdf5, "", [3, 1], ex)
    assert page_markers(ex) == ["MARKER-003", "MARKER-001"]


def test_rearrange_with_rotation_and_removal(tmp_path, job, pdf5):
    out = tmp_path / "r.pdf"
    r = ut.rearrange(job, pdf5, "", [(5, 0), (1, 90), (3, 270)], out)
    assert page_markers(out) == ["MARKER-005", "MARKER-001", "MARKER-003"]
    assert rotations(out) == [0, 90, 270]
    assert "2 removed" in r.message and "2 rotated" in r.message
    with pytest.raises(UserError):
        ut.rearrange(job, pdf5, "", [], tmp_path / "x.pdf")


# ------------------------------------------------------------------ page numbers

@pytest.mark.parametrize("position", ut.POSITIONS)
def test_page_numbers_position(tmp_path, job, pdf5, position):
    out = tmp_path / "n.pdf"
    ut.add_page_numbers(job, pdf5, "", out, [2, 3, 4], position, 7, "Page 1 of N", 10)
    with pymupdf.open(str(out)) as d:
        assert "Page" not in d[0].get_text().replace("Page 1", "")      # page 1 not numbered
        words = d[1].search_for("Page 7 of 5")
        assert words, d[1].get_text()
        r, rect = words[0], d[1].rect
        assert (r.y0 < rect.height / 2) == position.startswith("Top")
        if position.endswith("left"):
            assert r.x0 < rect.width / 3
        elif position.endswith("right"):
            assert r.x1 > rect.width * 2 / 3
        assert d[3].search_for("Page 9 of 5")


def test_page_numbers_on_rotated_page_read_upright(tmp_path, job):
    src = make_pdf(tmp_path / "rot.pdf", 1)
    with pymupdf.open(str(src)) as d:
        d[0].set_rotation(90)
        d.save(str(tmp_path / "rot90.pdf"))
    out = tmp_path / "n.pdf"
    ut.add_page_numbers(job, tmp_path / "rot90.pdf", "", out, [1], "Bottom right", 1, "1", 12)
    with pymupdf.open(str(out)) as d:
        page = d[0]
        hit = [l for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])
               if "".join(s["text"] for s in l["spans"]).strip() == "1"]
        assert hit
        # text direction in unrotated space equals the page rotation -> reads upright on screen
        dx, dy = hit[0]["dir"]
        assert (round(dx), round(dy)) == (0, -1)


# ------------------------------------------------------------------ rotate

@pytest.mark.parametrize("which,expected", [
    ("All pages", [90, 90, 90, 90, 90]),
    ("Odd pages only", [90, 0, 90, 0, 90]),
    ("Even pages only", [0, 90, 0, 90, 0]),
])
def test_rotate_page_sets(tmp_path, job, pdf5, which, expected):
    out = tmp_path / "r.pdf"
    ut.apply_turns(job, pdf5, "", out, {p: 90 for p in ut.pages_for(which, 5)})
    assert rotations(out) == expected


def test_rotate_selected_and_directions(tmp_path, job, pdf5):
    out = tmp_path / "r.pdf"
    ut.apply_turns(job, pdf5, "", out, {p: ut.DIRECTIONS["90° anticlockwise"] for p in
                                        ut.pages_for("Selected pages", 5, [2, 4])})
    assert rotations(out) == [0, 270, 0, 270, 0]
    out2 = tmp_path / "r2.pdf"
    ut.apply_turns(job, out, "", out2, {2: 180, 3: 180})          # adds to the existing rotation
    assert rotations(out2) == [0, 90, 180, 270, 0]
    with pytest.raises(UserError):
        ut.pages_for("Selected pages", 5, [])


def test_rotate_keeps_content_untouched(tmp_path, job, pdf5):
    out = tmp_path / "r.pdf"
    ut.apply_turns(job, pdf5, "", out, {1: 90})
    assert page_markers(out) == page_markers(pdf5)


def _sideways_doc(path, page_specs):
    """page_specs: list of (text rotate angle, page /Rotate)."""
    doc = pymupdf.open()
    for text_rot, page_rot in page_specs:
        p = doc.new_page()
        for i in range(12):
            if text_rot == 0:
                p.insert_text((60, 80 + i * 18), LINE, fontsize=11)
            elif text_rot == 90:
                p.insert_text((80 + i * 18, 700), LINE, fontsize=11, rotate=90)
            elif text_rot == 270:
                p.insert_text((520 - i * 18, 100), LINE, fontsize=11, rotate=270)
            else:
                p.insert_text((520, 700 - i * 18), LINE, fontsize=11, rotate=180)
        p.set_rotation(page_rot)
    doc.save(str(path))
    return path


def test_detect_sideways_text_pages(tmp_path, job):
    src = _sideways_doc(tmp_path / "s.pdf", [(0, 0), (90, 0), (0, 90), (180, 0), (270, 0), (90, 90)])
    found = ut.detect_sideways(job, src, "")
    assert found["turns"] == {2: 90, 3: 270, 4: 180, 5: 270}
    assert found["undecided"] == []
    out = tmp_path / "fixed.pdf"
    ut.apply_turns(job, src, "", out, found["turns"])
    again = ut.detect_sideways(job, out, "")
    assert again["turns"] == {}


@requires_tesseract
def test_detect_sideways_scanned_pages(tmp_path, job):
    """Image-only pages (no text layer) are checked with Tesseract's orientation data."""
    text_pdf = _sideways_doc(tmp_path / "t.pdf", [(0, 0)] * 4)
    scan = pymupdf.open()
    with pymupdf.open(str(text_pdf)) as d:
        for i, page in enumerate(d):
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).rotate(-90 * i, expand=True)   # 0, 90cw, 180, 270cw
            buf = io.BytesIO()
            img.save(buf, "PNG")
            p = scan.new_page(width=img.width * 72 / 150, height=img.height * 72 / 150)
            p.insert_image(p.rect, stream=buf.getvalue())
    scan.save(str(tmp_path / "scan.pdf"))
    found = ut.detect_sideways(job, tmp_path / "scan.pdf", "")
    assert found["turns"] == {2: 270, 3: 180, 4: 90}
    assert set(found["methods"].values()) == {"ocr"}


# ------------------------------------------------------------------ images

def test_pdf_to_images(tmp_path, job, pdf5):
    outs = [tmp_path / "a.png", tmp_path / "b.jpg"]
    ut.pdf_to_images(job, pdf5, "", [1, 5], outs[:1], "PNG", 72)
    ut.pdf_to_images(job, pdf5, "", [5], outs[1:], "JPEG", 100)
    assert Image.open(outs[0]).size == (595, 842)                  # A4 at 72 dpi
    assert Image.open(outs[1]).format == "JPEG"


def test_images_to_pdf_exif_and_tiff(tmp_path, job):
    # a landscape-stored photo whose EXIF says 'rotate 90' -> portrait page
    photo = Image.new("RGB", (400, 200), "white")
    exif = Image.Exif()
    exif[0x0112] = 6
    photo.save(tmp_path / "phone.jpg", exif=exif)
    frames = [Image.new("RGB", (200, 300), c) for c in ("red", "green", "blue")]
    frames[0].save(tmp_path / "multi.tif", save_all=True, append_images=frames[1:])
    out = tmp_path / "imgs.pdf"
    r = ut.images_to_pdf(job, [str(tmp_path / "phone.jpg"), str(tmp_path / "multi.tif")], out, "A4", "Automatic")
    with pymupdf.open(str(out)) as d:
        assert d.page_count == 4
        assert d[0].rect.height > d[0].rect.width                 # upright portrait from EXIF
    assert "4-page" in r.message
    fit = tmp_path / "fit.pdf"
    ut.images_to_pdf(job, [str(tmp_path / "multi.tif")], fit, "Fit to image")
    with pymupdf.open(str(fit)) as d:
        assert round(d[0].rect.width) == 96 and round(d[0].rect.height) == 144


def test_images_to_pdf_bad_file(tmp_path, job):
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(UserError):
        ut.images_to_pdf(job, [str(bad)], tmp_path / "o.pdf")


# ------------------------------------------------------------------ passwords

def test_protect_and_remove_full_access(tmp_path, job, pdf5):
    prot = tmp_path / "p.pdf"
    ut.protect(job, pdf5, "", prot, "open123")
    with pytest.raises(PasswordRequired):
        open_pdf(prot, "")
    assert page_markers(prot, "open123")[0] == "MARKER-001"
    plain = tmp_path / "u.pdf"
    ut.remove_password(job, prot, plain, "open123")
    with pymupdf.open(str(plain)) as d:
        assert not d.needs_pass and not d.is_encrypted


def test_protect_with_restrictions(tmp_path, job, pdf5):
    prot = tmp_path / "p.pdf"
    r = ut.protect(job, pdf5, "", prot, "open123", "owner456", allow_print=True, allow_copy=False,
                   allow_edit=False)
    assert not r.warnings
    with pymupdf.open(str(prot)) as d:
        assert d.authenticate("open123") == 2                    # user, not owner
        assert d.permissions & pymupdf.PDF_PERM_PRINT
        assert not d.permissions & pymupdf.PDF_PERM_COPY
    # open password only: restrictions are kept
    kept = tmp_path / "k.pdf"
    msg = ut.remove_password(job, prot, kept, "open123").message
    assert "kept" in msg
    with pymupdf.open(str(kept)) as d:
        assert not d.needs_pass and not d.permissions & pymupdf.PDF_PERM_COPY
    # owner password: everything removed
    free = tmp_path / "f.pdf"
    ut.remove_password(job, prot, free, "owner456")
    with pymupdf.open(str(free)) as d:
        assert not d.is_encrypted


def test_protect_restrictions_without_owner_password_warns(tmp_path, job, pdf5):
    r = ut.protect(job, pdf5, "", tmp_path / "p.pdf", "open123", allow_copy=False)
    assert r.warnings


def test_remove_password_errors(tmp_path, job, pdf5):
    with pytest.raises(UserError):
        ut.remove_password(job, pdf5, tmp_path / "o.pdf", "x")      # not protected
    prot = tmp_path / "p.pdf"
    ut.protect(job, pdf5, "", prot, "right")
    with pytest.raises(UserError):
        ut.remove_password(job, prot, tmp_path / "o.pdf", "wrong")


def test_password_protected_input_needs_password(tmp_path, job, pdf5):
    prot = tmp_path / "p.pdf"
    ut.protect(job, pdf5, "", prot, "pw")
    with pytest.raises(PasswordRequired):
        ut.extract(job, prot, "", [1], tmp_path / "e.pdf")
    ut.extract(job, prot, "pw", [2], tmp_path / "e.pdf")
    assert page_markers(tmp_path / "e.pdf") == ["MARKER-002"]
