"""Markdown -> PDF and PDF -> Markdown, ported from the earlier PDF Play Station
(v1.1.0). New in 2.0: scanned pages can be read with OCR (English/Hindi/Marathi)
when converting PDF to Markdown."""

from __future__ import annotations

import html as html_lib
import io
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, unquote, urlparse

import pymupdf

from . import ocr
from .common import Job, Result, UserError, open_pdf, same_path, save_pdf, write_atomic

NAVY, GOLD = "#0B1E3D", "#B8966E"
TEXT_FLAGS = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES |
              getattr(pymupdf, "TEXT_MEDIABOX_CLIP", 0))


# ================================================================== Markdown -> PDF

class _SafeHTML(HTMLParser):
    """Whitelist sanitiser for the HTML produced by Python-Markdown (including raw
    inline HTML). Scripts, styles, event handlers, iframes, forms and javascript:
    URLs are dropped; images are resolved to local files only."""
    ALLOWED = {"p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "em", "i", "u", "del", "s",
               "strike", "ins", "mark", "sub", "sup", "code", "pre", "blockquote", "ul", "ol", "li", "table",
               "thead", "tbody", "tfoot", "tr", "th", "td", "a", "img", "span", "div", "dl", "dt", "dd", "abbr",
               "kbd", "small", "caption", "figure", "figcaption"}
    DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "form", "textarea", "select", "button",
                    "noscript", "svg", "math", "template", "head", "title", "link", "meta"}
    VOID = {"br", "hr", "img"}
    ATTRS = {"a": {"href", "title"}, "img": {"src", "alt", "title", "width", "height"},
             "th": {"align", "colspan", "rowspan", "style"}, "td": {"align", "colspan", "rowspan", "style"},
             "ol": {"start"}, "abbr": {"title"}}

    def __init__(self, image_resolver: Callable[[str, str], Optional[str]]):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.resolver = image_resolver
        self.removed: set = set()

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP_CONTENT:
            self.skip += 1
            self.removed.add(tag)
            return
        if self.skip or tag not in self.ALLOWED:
            if tag not in self.ALLOWED:
                self.removed.add(tag)
            return
        keep = []
        for name, value in attrs:
            value = value or ""
            if name not in self.ATTRS.get(tag, set()):
                continue
            if name == "style":
                m = re.fullmatch(r"\s*text-align\s*:\s*(left|right|center)\s*;?\s*", value)
                if not m:
                    continue
                value = f"text-align: {m.group(1)}"
            if tag == "a" and name == "href":
                scheme = urlparse(value).scheme.lower()
                if scheme not in ("http", "https", "mailto", "") or value.strip().lower().startswith("javascript"):
                    continue
            if tag == "img" and name == "src":
                alt = dict(attrs).get("alt") or ""
                resolved = self.resolver(value, alt)
                if resolved is None:
                    self.out.append('<span class="missing">[Image not included: %s]</span>'
                                    % html_lib.escape(alt or os.path.basename(value) or "image"))
                    return
                value = resolved
            keep.append('%s="%s"' % (name, html_lib.escape(value, quote=True)))
        self.out.append("<%s%s>" % (tag, (" " + " ".join(keep)) if keep else ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.ALLOWED or tag in self.VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html_lib.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self.out)


# (regular, bold, italic, bold-italic) file names in the Windows Fonts folder
FONT_FAMILIES = {
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Nirmala UI (Hindi / Marathi)": ("Nirmala.ttc", "NirmalaB.ttc", "Nirmala.ttc", "NirmalaB.ttc"),
}
MONO_FAMILIES = {"Consolas": ("consola.ttf", "consolab.ttf"), "Courier New": ("cour.ttf", "courbd.ttf")}
BUILTIN_FONTS = {"Helvetica (built-in)": "sans-serif", "Times (built-in)": "serif"}
SUPPORTED_IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")


def _font_dirs() -> list[str]:
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    return [d for d in dirs if os.path.isdir(d)]


def find_font(filename: str) -> Optional[str]:
    for d in _font_dirs():
        for cand in (filename, filename.lower()):
            p = os.path.join(d, cand)
            if os.path.isfile(p):
                return p
    return None


def available_font_families() -> list[str]:
    return [n for n, files in FONT_FAMILIES.items() if find_font(files[0])] + list(BUILTIN_FONTS)


def read_markdown(path) -> tuple[str, list[str]]:
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), ["The file is not valid UTF-8; it was read as Windows-1252."]


def _normalise_list_indent(text: str) -> str:
    """Python-Markdown needs 4-space nesting; many editors write 2 spaces."""
    out, fenced = [], False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        if not fenced:
            m = re.match(r"^( +)([-*+]|\d+[.)])\s", line)
            if m and len(m.group(1)) % 4 and len(m.group(1)) % 2 == 0:
                line = " " * (len(m.group(1)) * 2) + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def markdown_to_html(text: str, base_dir: str) -> tuple[str, list[str], dict[str, bytes]]:
    """(sanitised HTML, warnings, {archive name: image bytes})."""
    import markdown as markdown_lib
    from markdown.extensions import Extension
    from markdown.inlinepatterns import SimpleTagInlineProcessor

    class _Strike(Extension):
        def extendMarkdown(self, md):
            md.inlinePatterns.register(SimpleTagInlineProcessor(r"()~~(.+?)~~", "del"), "strike", 175)

    md = markdown_lib.Markdown(extensions=["tables", "fenced_code", "sane_lists", _Strike()], output_format="html")
    body = md.convert(_normalise_list_indent(text))
    warnings: list[str] = []
    images: dict[str, bytes] = {}

    def resolve(src: str, alt: str) -> Optional[str]:
        parsed = urlparse(src)
        if parsed.scheme in ("http", "https", "ftp", "data"):
            warnings.append(f"Remote/inline image not downloaded (offline): {src[:80]}")
            return None
        path = unquote(parsed.path if parsed.scheme == "file" else src)
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            warnings.append(f"Image not found: {path}")
            return None
        if not path.lower().endswith(SUPPORTED_IMG):
            warnings.append(f"Unsupported image format (skipped): {os.path.basename(path)}")
            return None
        name = "img_%03d%s" % (len(images) + 1, os.path.splitext(path)[1].lower())
        images[name] = Path(path).read_bytes()
        return name

    cleaner = _SafeHTML(resolve)
    cleaner.feed(body)
    cleaner.close()
    if cleaner.removed:
        warnings.append("HTML removed for safety: <%s>" % ">, <".join(sorted(cleaner.removed)))
    return cleaner.result(), warnings, images


def _css(fs: float, body_family: str, mono_family: str) -> str:
    return """
body { font-family: %(BODY)s; font-size: %(FS).1fpt; line-height: 1.45; color: #1A2333; }
h1, h2, h3, h4, h5, h6 { color: %(P)s; font-weight: bold; margin-top: 14pt; margin-bottom: 6pt; }
h1 { font-size: %(H1).1fpt; border-bottom: 1.5pt solid %(A)s; padding-bottom: 3pt; }
h2 { font-size: %(H2).1fpt; border-bottom: 0.6pt solid #C4C8D0; padding-bottom: 2pt; }
h3 { font-size: %(H3).1fpt; } h4 { font-size: %(H4).1fpt; } h5, h6 { font-size: %(FS).1fpt; }
h1.doctitle { font-size: %(T).1fpt; border-bottom: 2pt solid %(A)s; margin-top: 0; }
p { margin-top: 0; margin-bottom: 7pt; }
a { color: #1E3A6E; text-decoration: underline; }
ul, ol { margin-top: 0; margin-bottom: 7pt; padding-left: 18pt; }
li { margin-bottom: 2pt; }
blockquote { margin: 6pt 0 8pt 0; padding: 4pt 10pt; border-left: 3pt solid %(A)s;
             background-color: #F6F3EE; color: #3A4456; }
code { font-family: %(MONO)s; font-size: %(CS).1fpt; background-color: #EEF1F5; }
pre { font-family: %(MONO)s; font-size: %(CS).1fpt; white-space: pre-wrap; background-color: #F3F5F8;
      border: 0.6pt solid #D5DAE2; padding: 6pt; margin-bottom: 8pt; }
pre code { background-color: transparent; }
table { border-collapse: collapse; width: 100%%; margin-bottom: 9pt; }
th { background-color: %(P)s; color: #FFFFFF; font-weight: bold; padding: 4pt 6pt; border: 0.6pt solid %(P)s; }
td { padding: 4pt 6pt; border: 0.6pt solid #C4C8D0; vertical-align: top; }
hr { border: none; border-top: 0.8pt solid #C4C8D0; margin: 10pt 0; }
del { text-decoration: line-through; }
img { max-width: 100%%; }
.missing { color: #B42318; font-style: italic; }
""" % {"BODY": body_family, "MONO": mono_family, "FS": fs, "CS": fs * 0.9, "H1": fs * 1.9, "H2": fs * 1.5,
       "H3": fs * 1.25, "H4": fs * 1.1, "T": fs * 2.2, "P": NAVY, "A": GOLD}


def markdown_to_pdf(job: Job, md_path, out_path, paper: str = "A4", landscape: bool = False,
                    margin_mm: float = 20.0, font_size: float = 10.5, font_family: str = "Segoe UI",
                    page_numbers: bool = True, title: str = "", header_text: str = "",
                    footer_text: str = "") -> Result:
    if same_path(md_path, out_path):
        raise UserError("The output cannot be the Markdown file itself.")
    job.step(0, 4, "Reading Markdown")
    text, warnings = read_markdown(md_path)
    body, w2, images = markdown_to_html(text, os.path.dirname(os.path.abspath(md_path)))
    warnings += w2
    if title.strip():
        body = '<h1 class="doctitle">%s</h1>\n%s' % (html_lib.escape(title.strip()), body)
    job.step(1, 4, "Laying out pages")

    archive = pymupdf.Archive()
    for name, data in images.items():
        archive.add((data, name))
    font_faces, body_family, footer_font = "", "sans-serif", None
    if font_family in FONT_FAMILIES:
        styles = [("normal", "normal"), ("bold", "normal"), ("normal", "italic"), ("bold", "italic")]
        for i, fname in enumerate(FONT_FAMILIES[font_family]):
            path = find_font(fname)
            if not path:
                continue
            ext = Path(path).suffix.lower()
            archive.add((Path(path).read_bytes(), f"font_{i}{ext}"))
            weight, style = styles[i]
            font_faces += (f"@font-face {{ font-family: DocBody; src: url(font_{i}{ext}); font-weight: {weight}; "
                           f"font-style: {style}; }}\n")
            if i == 0:
                footer_font = path
        if font_faces:
            body_family = "DocBody, sans-serif"
        else:
            warnings.append(f"Font '{font_family}' not found; the built-in font was used.")
    elif font_family in BUILTIN_FONTS:
        body_family = BUILTIN_FONTS[font_family]
    mono_family = "monospace"
    for mfiles in MONO_FAMILIES.values():
        mpath = find_font(mfiles[0])
        if mpath:
            archive.add((Path(mpath).read_bytes(), "mono_0.ttf"))
            font_faces += "@font-face { font-family: DocMono; src: url(mono_0.ttf); }\n"
            mono_family = "DocMono, monospace"
            break

    page_rect = pymupdf.paper_rect("a4" if paper == "A4" else "letter")
    if landscape:
        page_rect = pymupdf.Rect(0, 0, page_rect.height, page_rect.width)
    m = margin_mm * 72.0 / 25.4
    band = font_size * 1.6 if (header_text or footer_text or page_numbers) else 0
    where = pymupdf.Rect(m, m + (band if header_text else 0), page_rect.width - m,
                         page_rect.height - m - (band if (footer_text or page_numbers) else 0))
    if where.width < 100 or where.height < 100:
        raise UserError("The margins are too large for the selected page size.")
    story = pymupdf.Story(html=f"<html><body>{body}</body></html>",
                          user_css=font_faces + _css(font_size, body_family, mono_family), archive=archive)
    doc = story.write_with_links(lambda _n, _f: (page_rect, where, None))
    try:
        job.step(2, 4, "Adding header, footer and page numbers")
        total = doc.page_count
        fkw = {"fontfile": footer_font, "fontname": "DocFoot"} if footer_font and footer_font.endswith(".ttf") \
            else {"fontname": "helv"}
        small = max(7.0, font_size * 0.8)
        colour = (0.36, 0.39, 0.46)
        font = pymupdf.Font(fontfile=fkw["fontfile"]) if "fontfile" in fkw else pymupdf.Font("helv")
        for i, page in enumerate(doc):
            if header_text:
                page.insert_text((m, m * 0.6 + small), header_text, fontsize=small, color=colour, **fkw)
                page.draw_line((m, m * 0.6 + small + 4), (page_rect.width - m, m * 0.6 + small + 4),
                               color=(0.72, 0.59, 0.43), width=0.6)
            ybase = page_rect.height - m * 0.55
            if footer_text:
                page.insert_text((m, ybase), footer_text, fontsize=small, color=colour, **fkw)
            if page_numbers:
                label = f"Page {i + 1} of {total}"
                width = font.text_length(label, fontsize=small)
                page.insert_text((page_rect.width - m - width, ybase), label, fontsize=small, color=colour, **fkw)
        doc.set_metadata({"title": title or Path(md_path).stem, "creator": "PDF Play Station",
                          "producer": "PDF Play Station"})
        job.step(3, 4, "Saving PDF")
        save_pdf(doc, out_path)
        pages = doc.page_count
    finally:
        doc.close()
    return Result([str(out_path)], f"'{Path(md_path).name}' converted to a {pages}-page PDF.", warnings)


# ================================================================== PDF -> Markdown

BULLET_RE = re.compile(r"^\s*([•●▪◦○■‣⁃∙·\-–\*])\s+")
NUMBER_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+")
ALPHA_RE = re.compile(r"^\s*(\(?[a-zA-Z]{1,4}\)|[a-z]\.)\s+")
LIST_LINE = re.compile(r"^\s*(- |\d{1,3}\. )")
MONO_HINTS = ("mono", "courier", "consol", "code", "menlo", "inconsolata")


def _list_start(text: str) -> bool:
    return bool(BULLET_RE.match(text) or NUMBER_RE.match(text))


def _style(span: dict) -> tuple[bool, bool, bool]:
    flags, font = span.get("flags", 0), span.get("font", "").lower()
    bold = bool(flags & 16) or "bold" in font or "black" in font or "heavy" in font
    italic = bool(flags & 2) or "italic" in font or "oblique" in font
    mono = bool(flags & 8) or any(h in font for h in MONO_HINTS)
    return bold, italic, mono


def _escape(text: str) -> str:
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text)


def _escape_line_start(text: str) -> str:
    """Stop plain text from being read as a heading, quote, list or rule."""
    if re.match(r"^\s*(#|>|[-+*]\s|\d+[.)]\s|={3,}|-{3,})", text):
        return "\\" + text.lstrip() if not re.match(r"^\s*\d", text) else re.sub(r"^(\s*\d+)([.)])", r"\1\\\2", text)
    return text


def _body_size(doc, pages: list[int]) -> float:
    counts: dict[float, int] = {}
    for pno in pages[:60]:
        for block in doc[pno].get_text("dict", flags=TEXT_FLAGS)["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    n = len(span["text"].strip())
                    if n:
                        key = round(span["size"], 1)
                        counts[key] = counts.get(key, 0) + n
    return max(counts, key=counts.get) if counts else 11.0


def _norm_edge(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", text.strip().lower()))


def _repeating_edges(doc, pages: list[int]) -> set:
    """Normalised text of lines in the top/bottom 8% that repeat on >= 50% of pages."""
    if len(pages) < 3:
        return set()
    seen: dict[str, int] = {}
    for pno in pages:
        page = doc[pno]
        h = page.rect.height
        found = set()
        for block in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]:
            for line in block.get("lines", []):
                y0, y1 = line["bbox"][1], line["bbox"][3]
                if y1 <= h * 0.08 or y0 >= h * 0.92:
                    t = _norm_edge("".join(s["text"] for s in line["spans"]))
                    if t:
                        found.add(t)
        for t in found:
            seen[t] = seen.get(t, 0) + 1
    return {t for t, n in seen.items() if n >= max(2, len(pages) * 0.5)}


def _is_page_number(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(page\s*)?[-–(]?\s*\d+\s*(of\s*\d+)?\s*[-–)]?\s*", text, re.I))


def _table_md(rows: list[list]) -> str:
    def cell(v) -> str:
        return re.sub(r"\s+", " ", str(v if v is not None else "")).replace("|", "\\|").strip()
    width = max(len(r) for r in rows)
    rows = [[cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join([" --- "] * width) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _save_image(block: dict, img_dir: Path, name: str) -> Optional[Path]:
    data, ext = block.get("image"), (block.get("ext") or "png").lower()
    if not data:
        return None
    if ext not in ("png", "jpg", "jpeg"):
        pix = pymupdf.Pixmap(data)
        if pix.n - pix.alpha >= 4:                       # CMYK -> RGB
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        data, ext = pix.tobytes("png"), "png"
    img_dir.mkdir(parents=True, exist_ok=True)
    path = img_dir / f"{name}.{ext}"
    path.write_bytes(data)
    return path


def _url(url: str) -> str:
    return url.replace(" ", "%20").replace(")", "%29")


def _render_spans(spans: list[dict], links: list) -> str:
    """Inline Markdown for one line: bold / italic / code and [text](url)."""
    parts: list[tuple[str, str, Optional[str]]] = []
    for s in spans:
        text = s["text"]
        if not text:
            continue
        bold, italic, mono = _style(s)
        style = "code" if mono else ("bi" if bold and italic else "b" if bold else "i" if italic else "")
        url = None
        r = pymupdf.Rect(s["bbox"])
        for lr, uri, _anchor in links:
            inter = r & lr
            if not inter.is_empty and inter.get_area() > 0.5 * max(r.get_area(), 1e-6):
                url = uri
                break
        if parts and parts[-1][0] == style and parts[-1][2] == url:
            parts[-1] = (style, parts[-1][1] + text, url)
        else:
            parts.append((style, text, url))
    out = []
    for style, text, url in parts:
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        if not core:
            out.append(text)
            continue
        if style == "code":
            tick = "``" if "`" in core else "`"
            core = f"{tick}{core}{tick}"
        else:
            core = _escape(core)
            wrap = {"b": "**", "i": "*", "bi": "***"}.get(style, "")
            core = wrap + core + wrap
        if url:
            core = f"[{core}]({_url(url)})"
        out.append(lead + core + trail)
    text = "".join(out)
    line_rect = pymupdf.Rect(spans[0]["bbox"]) if spans else pymupdf.Rect()
    for s in spans[1:]:
        line_rect |= pymupdf.Rect(s["bbox"])
    for lr, uri, anchor in links:            # a link covering only part of a span
        target = _escape(anchor)
        if anchor and lr.intersects(line_rect) and f"({_url(uri)})" not in text and target in text:
            text = text.replace(target, f"[{target}]({_url(uri)})", 1)
    prev = None                                # adjacent links to the same URL -> one link
    while prev != text:
        prev = text
        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)(\s+)\[([^\]]+)\]\(\2\)", r"[\1\3\4](\2)", text)
    return text


def _strip_prefix(rendered: str, raw_prefix: str) -> str:
    target = raw_prefix.strip()
    pos = rendered.find(target)
    if pos != -1:
        rendered = rendered[:pos] + rendered[pos + len(target):]
        rendered = re.sub(r"^(\*{1,3})\s+", r"\1", rendered.lstrip())
    return re.sub(r"^\*{1,3}\s*\*{1,3}", "", rendered.strip()).strip()


def _join(parts: list[str]) -> str:
    text = ""
    for p in parts:
        p = p.strip()
        if not text:
            text = p
        elif re.search(r"[A-Za-z]-$", text) and re.match(r"^[a-z]", p):
            text = text[:-1] + p                     # de-hyphenate line breaks
        else:
            text += " " + p
    return text


def _block_md(lines: list, body: float, links, list_base: Optional[float] = None) -> str:
    spans_all = [s for ln, _r, _b in lines for s in ln["spans"] if s["text"].strip()]
    if not spans_all:
        return ""
    chars = sum(len(s["text"].strip()) for s in spans_all)
    size = sum(s["size"] * len(s["text"].strip()) for s in spans_all) / chars
    styles = [_style(s) for s in spans_all]
    all_bold = all(b for b, _i, _m in styles)
    all_mono = all(m for _b, _i, m in styles)
    plain = " ".join(r.strip() for _ln, r, _b in lines)
    if all_mono:                                     # code block keeps its lines
        code = "\n".join(r.rstrip() for _ln, r, _b in lines)
        fence = "````" if "```" in code else "```"
        return f"{fence}\n{code}\n{fence}"
    ratio = size / body if body else 1.0
    level = 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3 if ratio >= 1.12 else 0
    if (not level and all_bold and len(plain) <= 90 and len(lines) <= 2
            and not plain.rstrip().endswith((".", ":", ";", ","))):
        level = 4 if ratio < 1.0 else 3
    if level and len(plain) <= 200:
        return "#" * level + " " + _escape(re.sub(r"\s+", " ", plain).strip())
    base_x = list_base if list_base is not None else min(b.x0 for _ln, _r, b in lines)
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(_join(para))
            para.clear()

    for ln, raw, lb in lines:
        rendered = _render_spans(ln["spans"], links)
        m_b, m_n, m_a = BULLET_RE.match(raw), NUMBER_RE.match(raw), ALPHA_RE.match(raw)
        if m_b or m_n or m_a:
            flush()
            indent = "  " * max(0, min(4, int(round((lb.x0 - base_x) / 16.0))))
            if m_b:
                out.append(f"{indent}- {_strip_prefix(rendered, raw[:m_b.end()])}")
            elif m_n:
                out.append(f"{indent}{m_n.group(1)}. {_strip_prefix(rendered, raw[:m_n.end()])}")
            else:
                out.append(f"{indent}- {rendered.strip()}")
        elif out and not para and re.match(r"^\s*(- |\d+\. )", out[-1].lstrip()):
            out[-1] = _join([out[-1], rendered])     # continuation of a list item
        else:
            para.append(rendered)
    flush()
    if out and not any(re.match(r"^\s*(- |\d+\. )", o) for o in out):
        out = [_escape_line_start(o) for o in out]
    return "\n".join(out)


def _assemble(chunks: list[Optional[str]]) -> str:
    """Join blocks: consecutive list blocks form one list; a paragraph ending without
    sentence punctuation followed by one starting in lower case (e.g. across a page
    break) is merged. None marks a hard boundary."""
    out: list[str] = []
    kinds: list[str] = []
    boundary = True
    for chunk in chunks:
        if chunk is None:
            boundary = True
            continue
        kind = ("list" if LIST_LINE.match(chunk) else
                "para" if not re.match(r"^(#|```|\||!\[|<!--)", chunk) else "other")
        if out and not boundary and kind == "list" and kinds[-1] == "list":
            out[-1] += "\n" + chunk
        elif (out and not boundary and kind == "para" and kinds[-1] == "para"
              and not re.search(r"[.!?:;)\]\"']\s*$", out[-1]) and re.match(r"^[a-z(]", chunk)):
            out[-1] = _join([out[-1], chunk])
        else:
            out.append(chunk)
            kinds.append(kind)
        boundary = False
    return "\n\n".join(out)


def _tidy(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)([ \t]+)\[([^\]\n]+)\]\(\2\)", r"[\1\3\4](\2)", text)
    text = re.sub(r"\*\*\s*\*\*", "", text)
    text = re.sub(r"(?<!\*)\*\*(\s+)\*\*(?!\*)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _ocr_page_md(page: pymupdf.Page, lang: str) -> str:
    """Text of a scanned page as Markdown paragraphs (blank-line separated)."""
    from PIL import Image
    pix = page.get_pixmap(dpi=300, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = ocr.image_to_text(img, lang=lang, psm=3)
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(_escape_line_start(_escape(p)) for p in paras if p)


def pdf_to_markdown(job: Job, src_path, password: str, out_path, pages: list[int], detect_tables: bool = True,
                    extract_images: bool = True, remove_edges: bool = True, page_markers: bool = False,
                    ocr_mode: str = "Automatic (recommended)", ocr_lang: str = "eng") -> Result:
    if same_path(src_path, out_path):
        raise UserError("The output cannot be the PDF itself.")
    out_path = Path(out_path)
    img_dir = out_path.with_name(out_path.stem + "_images")
    doc = open_pdf(src_path, password)
    warnings: list[str] = []
    images_saved: list[str] = []
    no_text: list[int] = []
    ocr_pages: list[int] = []
    chunks: list[Optional[str]] = []
    try:
        idx = [p - 1 for p in pages]
        job.step(0, len(idx) + 2, "Analysing fonts and layout")
        body = _body_size(doc, idx)
        edges = _repeating_edges(doc, idx) if remove_edges else set()
        for k, pno in enumerate(idx):
            job.step(k + 1, len(idx) + 2, f"Converting page {pno + 1} ({k + 1} of {len(idx)})")
            page = doc[pno]
            if page_markers:
                chunks += [f"<!-- Page {pno + 1} -->", None]
            has_text = bool(page.get_text("text").strip())
            if ocr_mode == "Always run OCR" or (not has_text and ocr_mode != "Off"):
                try:
                    md = _ocr_page_md(page, ocr_lang)
                except ocr.OcrError as exc:
                    raise UserError(str(exc))
                ocr_pages.append(pno + 1)
                if md:
                    chunks += [None, md, None]
                else:
                    no_text.append(pno + 1)
                continue
            elements: list[tuple[float, float, str]] = []
            table_rects: list[pymupdf.Rect] = []
            if detect_tables:
                try:
                    for tab in page.find_tables().tables:
                        rows = tab.extract()
                        if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                            r = pymupdf.Rect(tab.bbox)
                            table_rects.append(r)
                            elements.append((r.y0, r.x0, _table_md(rows)))
                except Exception as exc:
                    warnings.append(f"Table detection skipped on page {pno + 1} ({exc}).")
            links = []
            for ln in page.get_links():
                if ln.get("kind") == pymupdf.LINK_URI and ln.get("uri"):
                    lr = pymupdf.Rect(ln["from"])
                    try:
                        anchor = re.sub(r"\s+", " ", page.get_textbox(lr)).strip()
                    except Exception:
                        anchor = ""
                    links.append((lr, ln["uri"], anchor))
            data = page.get_text("dict", flags=TEXT_FLAGS | pymupdf.TEXT_PRESERVE_IMAGES, sort=True)
            h = page.rect.height
            list_xs = [l["bbox"][0] for b in data["blocks"] if b.get("type") == 0 for l in b["lines"]
                       if _list_start("".join(s["text"] for s in l["spans"]))]
            list_base = min(list_xs) if list_xs else None
            page_has_text = False
            img_no = 0
            for block in data["blocks"]:
                bb = pymupdf.Rect(block["bbox"])
                if block.get("type") == 1:
                    if extract_images and block.get("width", 0) >= 24 and block.get("height", 0) >= 24:
                        img_no += 1
                        try:
                            path = _save_image(block, img_dir, "page%03d_img%02d" % (pno + 1, img_no))
                        except Exception as exc:
                            warnings.append(f"Image {img_no} on page {pno + 1} not saved ({exc}).")
                            path = None
                        if path:
                            images_saved.append(str(path))
                            rel = os.path.relpath(path, out_path.parent).replace(os.sep, "/")
                            elements.append((bb.y0, bb.x0, f"![Image {img_no}, page {pno + 1}]({quote(rel)})"))
                    continue
                lines = []
                for line in block.get("lines", []):
                    lb = pymupdf.Rect(line["bbox"])
                    centre = pymupdf.Point((lb.x0 + lb.x1) / 2, (lb.y0 + lb.y1) / 2)
                    if any(centre in tr for tr in table_rects):
                        continue
                    raw = "".join(s["text"] for s in line["spans"])
                    if not raw.strip():
                        continue
                    page_has_text = True
                    if remove_edges and (lb.y1 <= h * 0.08 or lb.y0 >= h * 0.92):
                        if _norm_edge(raw) in edges or _is_page_number(raw):
                            continue
                    lines.append((line, raw, lb))
                if lines:
                    md = _block_md(lines, body, links, list_base)
                    if md.strip():
                        elements.append((bb.y0, bb.x0, md))
            if not page_has_text and not table_rects:
                no_text.append(pno + 1)
            elements.sort(key=lambda e: (round(e[0], 0), e[1]))
            if page_markers:
                chunks.append(None)
            chunks.extend(e[2] for e in elements)
        job.step(len(idx) + 1, len(idx) + 2, "Writing Markdown")
        text = _tidy(_assemble(chunks))
        write_atomic(out_path, text.encode("utf-8"))
    finally:
        doc.close()
    if ocr_pages:
        warnings.insert(0, f"Page(s) {', '.join(map(str, ocr_pages[:20]))} read with OCR ({ocr_lang}) - "
                           "please check names and figures.")
    if no_text:
        warnings.insert(0, f"No text found on page(s) {', '.join(map(str, no_text[:20]))}"
                           + (" (OCR is off)." if ocr_mode == "Off" else "."))
    extra = f" with {len(images_saved)} image(s)" if images_saved else ""
    return Result([str(out_path)] + images_saved,
                  f"'{Path(src_path).name}': {len(pages)} page(s) converted to Markdown{extra}.", warnings)
