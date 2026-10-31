"""Wraparound paperback cover for Amazon KDP: back cover, spine and front cover in one PDF.

Sized from the interior's page count, ink and trim (``kdp.cover_size``), with bleed on
every edge. The front shows the book's color cover image (``cover_art``) to the edge
of the paper, with the title on a label over it; without one, the title over the
cover page's line art in a white panel. The back has the book's description and a few
more of its pages; the spine, the title once the book is thick enough to read it.
Everything is CMYK, as KDP asks: line art is black on the K plate only, and the lower
right of the back cover is left empty for the barcode KDP prints there.

Output goes to ``books/<slug>/exports/covers/<slug>-cover-<pages>p-<timestamp>.pdf``:
a cover only fits an interior with the same page count.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.colors import CMYKColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from app.core import cover_art, export, kdp, pages
from app.core.export import Fonts
from app.core.schema import Book, CoverColor, Page

SAFE = 0.375 * inch  # text and art stay this far inside the trim (KDP asks for at least 0.125")
GAP = 0.25 * inch
PANEL_PAD = 0.2 * inch
PANEL_RADIUS = 16
BACK_TEXT_SHARE = 0.4  # of the back cover's height, at most, for the description
BACK_PAGES = 4  # coloring pages shown on the back
SPINE_MAX_FONT = 16
SPINE_MIN_FONT = 5  # below this the spine is left blank
ART_MAX_PPI = 400  # cover images are downscaled to this; KDP needs 300
ART_JPEG_QUALITY = 92

COLORS: dict[CoverColor, CMYKColor] = {
    "blue": CMYKColor(0.85, 0.45, 0, 0),
    "green": CMYKColor(0.75, 0.10, 0.85, 0.10),
    "orange": CMYKColor(0, 0.65, 0.95, 0),
    "purple": CMYKColor(0.60, 0.85, 0, 0),
    "pink": CMYKColor(0, 0.85, 0.30, 0),
    "teal": CMYKColor(0.90, 0.15, 0.45, 0.10),
}
WHITE = CMYKColor(0, 0, 0, 0)

_PAGES_IN_NAME = re.compile(r"-cover-(\d+)p-")

Box = tuple[float, float, float, float]


def covers_dir(book: Book) -> Path:
    return export.exports_dir(book) / "covers"


def cover_pages(path: Path) -> int | None:
    """Interior page count a built cover was sized for, read from its file name."""
    match = _PAGES_IN_NAME.search(path.name)
    return int(match.group(1)) if match else None


def _inset(box: Box, d: float) -> Box:
    x, y, w, h = box
    return x + d, y + d, w - 2 * d, h - 2 * d


def _draw_art(c: Canvas, path: Path, box: Box) -> None:
    """A white rounded panel with the line art inside, black on the K plate only."""
    c.setFillColor(WHITE)
    c.roundRect(*box, PANEL_RADIUS, stroke=0, fill=1)
    inner = _inset(box, PANEL_PAD)
    gray = export.line_art_image(path, inner[2:])
    empty = Image.new("L", gray.size, 0)
    cmyk = Image.merge("CMYK", (empty, empty, empty, ImageOps.invert(gray)))
    export.draw_fitted(c, ImageReader(cmyk), cmyk.size, inner)


def _fill(c: Canvas, path: Path, box: Box) -> None:
    """Draw a color image covering ``box``, centered and cropped to it, as a CMYK JPEG."""
    x, y, w, h = box
    with Image.open(path) as image:
        image = image.convert("RGB")
    width, height = image.size
    if width / height > w / h:
        crop = round(height * w / h)
        image = image.crop(((width - crop) // 2, 0, (width - crop) // 2 + crop, height))
    else:
        crop = round(width * h / w)
        image = image.crop((0, (height - crop) // 2, width, (height - crop) // 2 + crop))
    limit = (math.ceil(w / 72 * ART_MAX_PPI), math.ceil(h / 72 * ART_MAX_PPI))
    if image.width > limit[0]:
        image = image.resize(limit, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    cover_art.to_cmyk(image).save(buffer, format="JPEG", quality=ART_JPEG_QUALITY)
    buffer.seek(0)
    c.drawImage(ImageReader(buffer), x, y, w, h)


def _paragraph(c: Canvas, markup: str, style: ParagraphStyle, x: float, top: float, width: float) -> float:
    """Draw a paragraph whose top is at ``top``; returns its bottom."""
    paragraph = Paragraph(markup, style)
    _, h = paragraph.wrap(width, 10_000)
    paragraph.drawOn(c, x, top - h)
    return top - h


def _title_styles(fonts: Fonts) -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    title = ParagraphStyle("front_title", fontName=fonts.bold, fontSize=44, leading=50, alignment=TA_CENTER, textColor=WHITE)
    subtitle = ParagraphStyle("front_subtitle", fontName=fonts.italic, fontSize=20, leading=25, alignment=TA_CENTER, textColor=WHITE, spaceBefore=6)
    dedication = ParagraphStyle("front_dedication", fontName=fonts.italic, fontSize=16, leading=20, alignment=TA_CENTER, textColor=WHITE)
    return title, subtitle, dedication


def _label(c: Canvas, items: list[Paragraph], x: float, width: float, color: CMYKColor, top: float | None = None, bottom: float | None = None) -> None:
    """A rounded label in the cover color holding ``items``, hanging from ``top`` or standing on ``bottom``."""
    inner = width - 2 * PANEL_PAD
    total = sum(p.wrap(inner, 10_000)[1] + p.getSpaceBefore() for p in items)
    height = total + 2 * PANEL_PAD
    y = top - height if top is not None else bottom
    c.setFillColor(color)
    c.roundRect(x, y, width, height, PANEL_RADIUS, stroke=0, fill=1)
    export.draw_text(c, items, (x + PANEL_PAD, y + PANEL_PAD, inner, total), y + PANEL_PAD + total)


def _draw_front_with_art(c: Canvas, book: Book, art: Path, trim: Box, bleed_box: Box, fonts: Fonts) -> None:
    _fill(c, art, bleed_box)
    x, y, w, h = _inset(trim, SAFE)
    title, subtitle, dedication = _title_styles(fonts)
    items = [Paragraph(export.plain_markup(book.title), title)]
    if book.subtitle.strip():
        items.append(Paragraph(export.plain_markup(book.subtitle), subtitle))
    color = COLORS[book.cover_color]
    _label(c, items, x, w, color, top=y + h)
    if book.dedication.strip():
        _label(c, [Paragraph(export.plain_markup(book.dedication), dedication)], x, w, color, bottom=y)


def _draw_front(c: Canvas, book: Book, page: Page, trim: Box, fonts: Fonts) -> None:
    x, y, w, h = _inset(trim, SAFE)
    title, subtitle, dedication = _title_styles(fonts)
    bottom = _paragraph(c, export.plain_markup(book.title), title, x, y + h, w)
    if book.subtitle.strip():
        bottom = _paragraph(c, export.plain_markup(book.subtitle), subtitle, x, bottom - subtitle.spaceBefore, w)
    floor = y
    if book.dedication.strip():
        paragraph = Paragraph(export.plain_markup(book.dedication), dedication)
        _, ph = paragraph.wrap(w, 10_000)
        paragraph.drawOn(c, x, floor)
        floor += ph + GAP
    _draw_art(c, pages.selected_path(book.slug, page), (x, floor, w, bottom - GAP - floor))


def _draw_back(c: Canvas, book: Book, others: list[Page], trim: Box, fonts: Fonts) -> None:
    x, y, w, h = _inset(trim, SAFE)
    top = y + h
    if book.back_text.strip():
        text_h = h * BACK_TEXT_SHARE

        def make(scale: float) -> list[Paragraph]:
            style = ParagraphStyle("back", fontName=fonts.regular, fontSize=15 * scale, leading=20 * scale, textColor=WHITE)
            return [Paragraph(export.plain_markup(book.back_text), style)]

        items, total, _ = export.fit_text(make, w, text_h)
        export.draw_text(c, items, (x, top - text_h, w, text_h), top)
        top -= min(total, text_h) + GAP

    # A grid of pages above the barcode box, which keeps the lower right empty.
    floor = trim[1] + (kdp.BARCODE_INSET + kdp.BARCODE[1]) * inch + GAP
    shown = others[:BACK_PAGES]
    if not shown or top - floor < inch:
        return
    cols = 2 if len(shown) > 1 else 1
    rows = math.ceil(len(shown) / cols)
    cell_w = (w - GAP * (cols - 1)) / cols
    cell_h = (top - floor - GAP * (rows - 1)) / rows
    for i, page in enumerate(shown):
        row, col = divmod(i, cols)
        _draw_art(c, pages.selected_path(book.slug, page), (x + col * (cell_w + GAP), top - (row + 1) * cell_h - row * GAP, cell_w, cell_h))


def _draw_spine(c: Canvas, book: Book, spine: Box, fonts: Fonts) -> None:
    """The title, top to bottom, when the spine is wide enough to read it."""
    x, y, w, h = spine
    size = min(SPINE_MAX_FONT, (w - 2 * kdp.SPINE_TEXT_CLEARANCE * inch) * 0.8)
    length = h - 2 * SAFE
    size = min(size, size * length / max(stringWidth(book.title, fonts.bold, size), 1))
    if size < SPINE_MIN_FONT:
        return
    c.saveState()
    c.translate(x + w / 2, y + h / 2)
    c.rotate(-90)
    c.setFillColor(WHITE)
    c.setFont(fonts.bold, size)
    c.drawCentredString(0, -size * 0.35, book.title)
    c.restoreState()


def export_cover_pdf(book: Book) -> Path:
    """Build the wraparound cover for the interior the book exports now; returns its path."""
    included = export.preflight(book).included
    if not included:
        raise ValueError("No coloring pages to put on the cover yet.")
    count = len(export.sheets(book, included))
    width, height = (v * inch for v in kdp.cover_size(count, book.kdp_ink, book.page_size))
    trim_w, trim_h = (v * inch for v in kdp.TRIM[book.page_size])
    spine = kdp.spine_width(count, book.kdp_ink) * inch
    bleed = kdp.BLEED * inch
    fonts = export.load_fonts()
    front_page = next((p for p in included if p.id == book.cover_page_id), included[0])

    folder = covers_dir(book)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{book.slug}-cover-{count}p-{stamp}.pdf"

    c = Canvas(str(path), pagesize=(width, height), initialFontName=fonts.regular)
    c.setTitle(book.title)
    c.setCreator("Colorín Colorado")
    c.setFillColor(COLORS[book.cover_color])
    c.rect(0, 0, width, height, stroke=0, fill=1)
    _draw_back(c, book, [p for p in included if p.id != front_page.id], (bleed, bleed, trim_w, trim_h), fonts)
    if count >= kdp.SPINE_TEXT_MIN_PAGES:
        _draw_spine(c, book, (bleed + trim_w, bleed, spine, trim_h), fonts)
    front = (bleed + trim_w + spine, bleed, trim_w, trim_h)
    art = cover_art.selected_path(book)
    if art:
        _draw_front_with_art(c, book, art, front, (front[0], 0, trim_w + bleed, height), fonts)
    else:
        _draw_front(c, book, front_page, front, fonts)
    c.showPage()
    c.save()
    return path
