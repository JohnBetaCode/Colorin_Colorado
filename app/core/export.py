"""PDF export of a coloring book.

One sheet per coloring page: the line art on top and, when the page has a caption or
the book shows reference photos, a rounded info box at the bottom with the color
photo and the caption. Line art is embedded losslessly, so every pixel of it stays
pure black or pure white; reference photos are re-encoded as bounded JPEGs. No
Gemini calls are made.

Output goes to ``books/<slug>/exports/<slug>-<timestamp>.pdf``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from app.core import i18n, pages
from app.core.books import book_path
from app.core.schema import Book, Page

PAGE_SIZES = {"letter": LETTER, "a4": A4}
MARGIN = 0.5 * inch
FOOTER = 0.3 * inch
BOX_RATIO = 0.24  # share of the content height taken by the info box
GAP = 0.18 * inch
PAD = 0.14 * inch
RADIUS = 10
PHOTO_MAX_PX = 1200
PHOTO_JPEG_QUALITY = 85
# Caption text shrinks in steps (body text 14 pt down to ~9 pt) before it overflows.
TEXT_SCALES = [1 - 0.05 * i for i in range(8)]

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")

# Andika (SIL) is designed for children learning to read; installed in the Docker image.
_ANDIKA_DIR = Path("/usr/share/fonts/truetype/andika")


@dataclass
class Fonts:
    regular: str = "Helvetica"
    bold: str = "Helvetica-Bold"
    italic: str = "Helvetica-Oblique"


@dataclass
class Preflight:
    """What the next export will contain, computed without building it."""

    included: list[Page] = field(default_factory=list)
    without_version: list[Page] = field(default_factory=list)
    not_approved: list[Page] = field(default_factory=list)
    overflowing: list[Page] = field(default_factory=list)


def _fonts() -> Fonts:
    """Andika when installed (Docker), else Helvetica (Latin-1 only)."""
    names = ["Andika", "Andika-Bold", "Andika-Italic"]
    files = [_ANDIKA_DIR / f"Andika-{style}.ttf" for style in ("Regular", "Bold", "Italic")]
    if not all(f.exists() for f in files):
        return Fonts()
    registered = pdfmetrics.getRegisteredFontNames()
    for name, file in zip(names, files):
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, str(file)))
    pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1], italic=names[2], boldItalic=names[1])
    return Fonts(*names)


# --- Geometry ---------------------------------------------------------------------


@dataclass
class Layout:
    width: float
    height: float

    @property
    def content(self) -> tuple[float, float, float, float]:
        """x, y, width, height of the area inside the margins, above the footer."""
        return MARGIN, MARGIN + FOOTER, self.width - 2 * MARGIN, self.height - 2 * MARGIN - FOOTER

    def boxes(self, with_info: bool) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float] | None]:
        """Line-art box and info box (or None) for one coloring sheet."""
        x, y, w, h = self.content
        if not with_info:
            return (x, y, w, h), None
        box_h = h * BOX_RATIO
        return (x, y + box_h + GAP, w, h - box_h - GAP), (x, y, w, box_h)


def _layout(book: Book) -> Layout:
    return Layout(*PAGE_SIZES[book.page_size])


def _shows_info(book: Book, page: Page) -> bool:
    return page.has_caption or book.include_reference_photo


def _photo_box(info: tuple[float, float, float, float], photo_size: tuple[int, int] | None) -> tuple[float, float, float, float] | None:
    """Where the reference photo goes inside the info box (left side), keeping its aspect."""
    if photo_size is None:
        return None
    x, y, w, h = info
    max_h = h - 2 * PAD
    max_w = min(max_h * 1.5, w * 0.4)
    pw, ph = photo_size
    scale = min(max_w / pw, max_h / ph)
    return x + PAD, y + (h - ph * scale) / 2, pw * scale, ph * scale


def _text_box(info: tuple[float, float, float, float], photo: tuple[float, float, float, float] | None) -> tuple[float, float, float, float]:
    x, y, w, h = info
    left = (photo[0] + photo[2] + PAD * 1.4) if photo else x + PAD * 1.4
    return left, y + PAD, x + w - PAD * 1.4 - left, h - 2 * PAD


# --- Caption text -------------------------------------------------------------------

_LABEL_LINE = re.compile(r"^([^:]{1,32}):\s*(.*)$")


def info_markup(text: str) -> str:
    """Escape the info text, keep line breaks, and bold ``Label:`` at the start of a line."""
    lines = []
    for line in text.strip().splitlines():
        match = _LABEL_LINE.match(line.strip())
        if match and match.group(2):
            lines.append(f"<b>{escape(match.group(1))}:</b> {escape(match.group(2))}")
        else:
            lines.append(escape(line.strip()))
    return "<br/>".join(lines)


def _caption(page: Page, scale: float, fonts: Fonts) -> list[Paragraph]:
    def style(name: str, font: str, size: float, leading: float, color, space: float = 0) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=font, fontSize=size * scale, leading=leading * scale, textColor=color, spaceBefore=space * scale)

    items = []
    if page.title.strip():
        items.append(Paragraph(escape(page.title.strip()), style("title", fonts.bold, 22, 26, INK)))
    if page.subtitle.strip():
        items.append(Paragraph(escape(page.subtitle.strip()), style("subtitle", fonts.italic, 14, 17, MUTED, 1)))
    if page.info.strip():
        items.append(Paragraph(info_markup(page.info), style("info", fonts.regular, 14, 18, INK, 6 if items else 0)))
    return items


def _fit_caption(page: Page, width: float, height: float, fonts: Fonts) -> tuple[list[Paragraph], float, bool]:
    """Largest text scale whose caption fits; returns (paragraphs, total height, fits)."""
    for scale in TEXT_SCALES:
        items = _caption(page, scale, fonts)
        total = sum(p.wrap(width, height)[1] + p.getSpaceBefore() for p in items)
        if total <= height:
            return items, total, True
    return items, total, False


def caption_fits(book: Book, page: Page, fonts: Fonts | None = None) -> bool:
    if not page.has_caption:
        return True
    _, info = _layout(book).boxes(True)
    photo = _photo_box(info, pages.photo_size(book.slug, page)) if book.include_reference_photo else None
    _, _, tw, th = _text_box(info, photo)
    return _fit_caption(page, tw, th, fonts or _fonts())[2]


# --- Drawing ---------------------------------------------------------------------


def _line_art_reader(path: Path) -> tuple[ImageReader, tuple[int, int]]:
    image = Image.open(path).convert("L")  # lossless: stays 0/255
    return ImageReader(image), image.size


def _photo_reader(image: Image.Image) -> tuple[ImageReader, tuple[int, int]]:
    image = image.convert("RGB")
    image.thumbnail((PHOTO_MAX_PX, PHOTO_MAX_PX))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True)
    buffer.seek(0)
    return ImageReader(buffer), image.size


def _draw_fitted(c: Canvas, reader: ImageReader, size: tuple[int, int], box: tuple[float, float, float, float]) -> None:
    x, y, w, h = box
    scale = min(w / size[0], h / size[1])
    dw, dh = size[0] * scale, size[1] * scale
    c.drawImage(reader, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)


def _centered(c: Canvas, text: str, style: ParagraphStyle, x: float, top: float, width: float) -> float:
    """Draw a centered paragraph whose top is at ``top``; returns its bottom."""
    paragraph = Paragraph(escape(text), style)
    _, h = paragraph.wrap(width, 10_000)
    paragraph.drawOn(c, x, top - h)
    return top - h


def _frame(c: Canvas, layout: Layout) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(2)
    c.roundRect(MARGIN, MARGIN, layout.width - 2 * MARGIN, layout.height - 2 * MARGIN, 18)


def _draw_cover(c: Canvas, book: Book, cover: Page | None, layout: Layout, fonts: Fonts) -> None:
    _frame(c, layout)
    x, w = MARGIN + PAD * 2, layout.width - 2 * (MARGIN + PAD * 2)
    top = layout.height - MARGIN - 0.6 * inch
    title = ParagraphStyle("cover_title", fontName=fonts.bold, fontSize=34, leading=40, alignment=TA_CENTER, textColor=INK)
    bottom = _centered(c, book.title, title, x, top, w)
    if book.subtitle.strip():
        subtitle = ParagraphStyle("cover_subtitle", fontName=fonts.italic, fontSize=16, leading=20, alignment=TA_CENTER, textColor=MUTED)
        bottom = _centered(c, book.subtitle.strip(), subtitle, x, bottom - 8, w)
    floor = MARGIN + 0.5 * inch
    if book.dedication.strip():
        dedication = ParagraphStyle("dedication", fontName=fonts.italic, fontSize=13, leading=17, alignment=TA_CENTER, textColor=MUTED)
        paragraph = Paragraph(escape(book.dedication.strip()), dedication)
        _, h = paragraph.wrap(w, 10_000)
        paragraph.drawOn(c, x, floor)
        floor += h + 0.2 * inch
    art = pages.selected_path(book.slug, cover) if cover else None
    if art:
        reader, size = _line_art_reader(art)
        _draw_fitted(c, reader, size, (x, floor, w, bottom - 0.3 * inch - floor))
    c.showPage()


def _draw_owner_page(c: Canvas, book: Book, layout: Layout, fonts: Fonts) -> None:
    _frame(c, layout)
    x, w = MARGIN + PAD * 2, layout.width - 2 * (MARGIN + PAD * 2)
    style = ParagraphStyle("owner", fontName=fonts.bold, fontSize=26, leading=32, alignment=TA_CENTER, textColor=INK)
    bottom = _centered(c, i18n.t("pdf.owner", lang=book.language), style, x, layout.height * 0.6, w)
    c.setStrokeColor(INK)
    c.setLineWidth(1.5)
    c.line(x + w * 0.12, bottom - 0.9 * inch, x + w * 0.88, bottom - 0.9 * inch)
    c.showPage()


def _draw_sheet(c: Canvas, book: Book, page: Page, number: int, layout: Layout, fonts: Fonts) -> None:
    art_box, info = layout.boxes(_shows_info(book, page))
    reader, size = _line_art_reader(pages.selected_path(book.slug, page))
    _draw_fitted(c, reader, size, art_box)

    if info:
        c.setStrokeColor(INK)
        c.setLineWidth(1.2)
        c.roundRect(*info, RADIUS)
        photo = None
        if book.include_reference_photo:
            photo_reader, photo_size = _photo_reader(pages.cropped_photo(book.slug, page))
            photo = _photo_box(info, photo_size)
            c.drawImage(photo_reader, *photo)
            c.setLineWidth(0.6)
            c.rect(*photo)
        if page.has_caption:
            tx, ty, tw, th = _text_box(info, photo)
            items, total, fits = _fit_caption(page, tw, th, fonts)
            c.saveState()
            clip = c.beginPath()
            clip.rect(tx, ty, tw, th)
            c.clipPath(clip, stroke=0, fill=0)
            cursor = ty + th - (th - total) / 2 if fits else ty + th
            for paragraph in items:
                cursor -= paragraph.getSpaceBefore()
                _, h = paragraph.wrap(tw, th)
                paragraph.drawOn(c, tx, cursor - h)
                cursor -= h
            c.restoreState()

    c.setFont(fonts.regular, 10)
    c.setFillColor(MUTED)
    c.drawCentredString(layout.width / 2, MARGIN, str(number))
    c.showPage()


# --- Public API ---------------------------------------------------------------------


def exports_dir(book: Book) -> Path:
    return book_path(book.slug) / "exports"


def preflight(book: Book) -> Preflight:
    report = Preflight()
    fonts = _fonts()
    for page in pages.load_pages(book.slug):
        if not page.in_book:
            continue
        if pages.selected_path(book.slug, page) is None:
            report.without_version.append(page)
            continue
        report.included.append(page)
        if page.status != "approved":
            report.not_approved.append(page)
        if not caption_fits(book, page, fonts):
            report.overflowing.append(page)
    return report


def export_book_pdf(book: Book) -> Path:
    """Build the PDF and return its path. Pages without a coloring page are skipped."""
    included = preflight(book).included
    if not included:
        raise ValueError("No coloring pages to export yet.")
    layout = _layout(book)
    fonts = _fonts()
    cover = next((p for p in included if p.id == book.cover_page_id), included[0])

    folder = exports_dir(book)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{book.slug}-{stamp}.pdf"

    c = Canvas(str(path), pagesize=(layout.width, layout.height))
    c.setTitle(book.title)
    c.setCreator("Colorín Colorado")

    def blank_back() -> None:
        if book.blank_backs:
            c.showPage()

    _draw_cover(c, book, cover, layout, fonts)
    blank_back()
    if book.include_owner_page:
        _draw_owner_page(c, book, layout, fonts)
        blank_back()
    for number, page in enumerate(included, start=1):
        _draw_sheet(c, book, page, number, layout, fonts)
        blank_back()
    c.save()
    return path
