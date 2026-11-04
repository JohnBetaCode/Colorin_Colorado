"""PDF export of a coloring book (the interior, for home printing and for Amazon KDP).

One sheet per coloring page: the line art on top and, when the page has a caption or
the book shows reference photos, a rounded info box at the bottom with the color
photo and the caption. Line art is embedded losslessly, so every pixel of it stays
pure black or pure white, and never below ``PRINT_DPI``; reference photos are
re-encoded as bounded JPEGs. Every font is embedded, which KDP requires. No Gemini
calls are made.

Output goes to ``books/<slug>/exports/<slug>-<timestamp>.pdf``. The wraparound KDP
cover is built by ``cover.py``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pypdfium2 as pdfium
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

from app.core import extras, i18n, mosaic, page_templates, pages
from app.core.books import book_path
from app.core.schema import Book, MosaicSettings, Page

PAGE_SIZES = {"letter": LETTER, "a4": A4, "8x10": (8 * inch, 10 * inch), "square": (8.5 * inch, 8.5 * inch)}
MARGIN = 0.5 * inch  # also KDP's minimum inside margin up to 300 pages (kdp.MAX_PAGES)
FOOTER = 0.3 * inch
BOX_RATIO = 0.24  # share of the content height taken by the info box
GAP = 0.18 * inch
PAD = 0.14 * inch
RADIUS = 10
PRINT_DPI = 300  # KDP's minimum for images
PHOTO_MAX_PX = 1200
PHOTO_JPEG_QUALITY = 85
# Caption text shrinks in steps (body text 14 pt down to ~9 pt) before it overflows.
TEXT_SCALES = [1 - 0.05 * i for i in range(8)]

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")

# Andika (SIL) is designed for children learning to read; installed in the Docker image.
_ANDIKA_DIR = Path("/usr/share/fonts/truetype/andika")

# One page of the interior: "title", "legal", "owner", "blank", an extra (schema.EXTRAS) or a
# coloring page.
Sheet = str | Page


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
    extras_missing: list[str] = field(default_factory=list)  # chosen extras the pages cannot make


def load_fonts() -> Fonts:
    """Andika when installed (Docker), else Helvetica (Latin-1 only, and not embedded)."""
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


def fonts_embedded() -> bool:
    """Whether the PDF embeds its fonts: true with Andika, false with the Helvetica fallback."""
    return load_fonts().regular != Fonts().regular


# --- Geometry ---------------------------------------------------------------------


@dataclass
class Layout:
    width: float
    height: float

    @property
    def content(self) -> tuple[float, float, float, float]:
        """x, y, width, height of the area inside the margins, above the footer."""
        return MARGIN, MARGIN + FOOTER, self.width - 2 * MARGIN, self.height - 2 * MARGIN - FOOTER

    def boxes(
        self, with_info: bool, content: tuple[float, float, float, float] | None = None
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float] | None]:
        """Line-art box and info box (or None) for one coloring sheet, inside ``content``
        (a page template's area) or the whole content box."""
        x, y, w, h = content or self.content
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


# --- Text -------------------------------------------------------------------------

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


def plain_markup(text: str) -> str:
    """Escape typed text and keep its line breaks."""
    return "<br/>".join(escape(line.strip()) for line in text.strip().splitlines())


def _caption(book: Book, page: Page, scale: float, fonts: Fonts) -> list[Paragraph]:
    """The caption, and in a bilingual book its translation below it, smaller and muted."""

    def style(name: str, font: str, size: float, leading: float, color, space: float = 0) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=font, fontSize=size * scale, leading=leading * scale, textColor=color, spaceBefore=space * scale)

    items = []
    if page.title.strip():
        items.append(Paragraph(escape(page.title.strip()), style("title", fonts.bold, 22, 26, INK)))
    if page.subtitle.strip():
        items.append(Paragraph(escape(page.subtitle.strip()), style("subtitle", fonts.italic, 14, 17, MUTED, 1)))
    if page.info.strip():
        items.append(Paragraph(info_markup(page.info), style("info", fonts.regular, 14, 18, INK, 6 if items else 0)))
    other = page.translation
    if len(book.languages) > 1 and not other.is_empty:
        # The subtitle is often a scientific name or a date: print it once.
        if other.title.strip():
            items.append(Paragraph(escape(other.title.strip()), style("title2", fonts.bold, 16, 19, MUTED, 8)))
        if other.info.strip():
            items.append(Paragraph(info_markup(other.info), style("info2", fonts.italic, 12, 15, MUTED, 2)))
    return items


def fit_text(make: Callable[[float], list[Paragraph]], width: float, height: float) -> tuple[list[Paragraph], float, bool]:
    """Largest of ``TEXT_SCALES`` whose paragraphs fit; returns (paragraphs, total height, fits)."""
    for scale in TEXT_SCALES:
        items = make(scale)
        total = sum(p.wrap(width, height)[1] + p.getSpaceBefore() for p in items)
        if total <= height:
            return items, total, True
    return items, total, False


def draw_text(c: Canvas, items: list[Paragraph], box: tuple[float, float, float, float], top: float) -> None:
    """Draw paragraphs downwards from ``top``, clipped to ``box``."""
    x, y, w, h = box
    c.saveState()
    clip = c.beginPath()
    clip.rect(x, y, w, h)
    c.clipPath(clip, stroke=0, fill=0)
    cursor = top
    for paragraph in items:
        cursor -= paragraph.getSpaceBefore()
        _, ph = paragraph.wrap(w, h)
        paragraph.drawOn(c, x, cursor - ph)
        cursor -= ph
    c.restoreState()


def content_box(book: Book) -> tuple[float, float, float, float]:
    """The page's printable box in points, inside the margins and above the page number."""
    return _layout(book).content


def sheet_area(book: Book, page: Page, layout: Layout) -> tuple[float, float, float, float]:
    """Where a coloring page's drawing and caption go: its template's area, or the content box."""
    template = page_templates.for_page(book, page)
    if template is None:
        return layout.content
    return page_templates.drawing_box(book, template, layout.content, page.template_inset)


def caption_fits(book: Book, page: Page, fonts: Fonts | None = None) -> bool:
    if not page.has_caption:
        return True
    layout = _layout(book)
    _, info = layout.boxes(True, sheet_area(book, page, layout))
    photo = _photo_box(info, pages.photo_size(book.slug, page)) if book.include_reference_photo else None
    _, _, tw, th = _text_box(info, photo)
    fonts = fonts or load_fonts()
    return fit_text(lambda scale: _caption(book, page, scale, fonts), tw, th)[2]


# --- Drawing ---------------------------------------------------------------------


def line_art_image(path: Path, box: tuple[float, float] | None = None) -> Image.Image:
    """The line art as 8-bit grayscale, which is embedded losslessly: it stays 0/255.

    When fitting it into ``box`` (width, height in points) would print it below
    ``PRINT_DPI``, it is upsampled smoothly and thresholded again, so curves stay
    smooth and every pixel is still pure black or pure white.
    """
    image = Image.open(path).convert("L")
    if box:
        points_per_px = min(box[0] / image.width, box[1] / image.height)
        factor = PRINT_DPI * points_per_px / 72
        if factor > 1:
            size = (math.ceil(image.width * factor), math.ceil(image.height * factor))
            image = image.resize(size, Image.Resampling.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    return image


def _photo_reader(image: Image.Image) -> tuple[ImageReader, tuple[int, int]]:
    image = image.convert("RGB")
    image.thumbnail((PHOTO_MAX_PX, PHOTO_MAX_PX))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True)
    buffer.seek(0)
    return ImageReader(buffer), image.size


def draw_fitted(c: Canvas, reader: ImageReader, size: tuple[int, int], box: tuple[float, float, float, float]) -> None:
    x, y, w, h = box
    scale = min(w / size[0], h / size[1])
    dw, dh = size[0] * scale, size[1] * scale
    c.drawImage(reader, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)


def draw_line_art(c: Canvas, path: Path, box: tuple[float, float, float, float]) -> None:
    image = line_art_image(path, box[2:])
    draw_fitted(c, ImageReader(image), image.size, box)


def centered(c: Canvas, text: str, style: ParagraphStyle, x: float, top: float, width: float) -> float:
    """Draw a centered paragraph whose top is at ``top``; returns its bottom."""
    paragraph = Paragraph(escape(text), style)
    _, h = paragraph.wrap(width, 10_000)
    paragraph.drawOn(c, x, top - h)
    return top - h


def _frame(c: Canvas, layout: Layout) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(2)
    c.roundRect(MARGIN, MARGIN, layout.width - 2 * MARGIN, layout.height - 2 * MARGIN, 18)


def _draw_title_page(c: Canvas, book: Book, cover: Page | None, layout: Layout, fonts: Fonts) -> None:
    """The first page: the cover when printing at home, the title page in a KDP paperback."""
    _frame(c, layout)
    x, w = MARGIN + PAD * 2, layout.width - 2 * (MARGIN + PAD * 2)
    top = layout.height - MARGIN - 0.6 * inch
    title = ParagraphStyle("cover_title", fontName=fonts.bold, fontSize=34, leading=40, alignment=TA_CENTER, textColor=INK)
    bottom = centered(c, book.title, title, x, top, w)
    if book.subtitle.strip():
        subtitle = ParagraphStyle("cover_subtitle", fontName=fonts.italic, fontSize=16, leading=20, alignment=TA_CENTER, textColor=MUTED)
        bottom = centered(c, book.subtitle.strip(), subtitle, x, bottom - 8, w)
    floor = MARGIN + 0.5 * inch
    if book.dedication.strip():
        dedication = ParagraphStyle("dedication", fontName=fonts.italic, fontSize=13, leading=17, alignment=TA_CENTER, textColor=MUTED)
        paragraph = Paragraph(escape(book.dedication.strip()), dedication)
        _, h = paragraph.wrap(w, 10_000)
        paragraph.drawOn(c, x, floor)
        floor += h + 0.2 * inch
    art = pages.selected_path(book.slug, cover) if cover else None
    if art:
        draw_line_art(c, art, (x, floor, w, bottom - 0.3 * inch - floor))
    c.showPage()


def _credits(included: list[Page]) -> list[tuple[int, Page]]:
    """Coloring pages with a photo credit, with their printed page number."""
    return [(n, page) for n, page in enumerate(included, start=1) if page.credit.strip()]


def _legal(book: Book, included: list[Page], scale: float, fonts: Fonts) -> list[Paragraph]:
    body = ParagraphStyle("legal", fontName=fonts.regular, fontSize=10 * scale, leading=13 * scale, textColor=INK)
    items = []
    if book.legal.strip():
        items.append(Paragraph(plain_markup(book.legal), body))
    credits = _credits(included)
    if credits:
        heading = ParagraphStyle("credits", parent=body, fontName=fonts.bold, spaceBefore=(16 if items else 0) * scale)
        items.append(Paragraph(escape(" / ".join(i18n.t_all("pdf.photo_credits", book.languages))), heading))
        for number, page in credits:
            line = i18n.t("pdf.credit_line", lang=book.language, n=number, title=page.title.strip() or page.original_name, credit=page.credit.strip())
            items.append(Paragraph(escape(line), body))
    return items


def has_legal_page(book: Book, included: list[Page]) -> bool:
    return bool(book.legal.strip() or _credits(included))


def _draw_legal_page(c: Canvas, book: Book, included: list[Page], layout: Layout, fonts: Fonts) -> None:
    """Copyright page: the book's legal text and the photo credits, at the foot of the page."""
    x, y, w, h = layout.content
    items, total, fits = fit_text(lambda scale: _legal(book, included, scale, fonts), w, h)
    draw_text(c, items, (x, y, w, h), y + total if fits else y + h)
    c.showPage()


def _draw_owner_page(c: Canvas, book: Book, layout: Layout, fonts: Fonts) -> None:
    _frame(c, layout)
    x, w = MARGIN + PAD * 2, layout.width - 2 * (MARGIN + PAD * 2)
    style = ParagraphStyle("owner", fontName=fonts.bold, fontSize=26, leading=32, alignment=TA_CENTER, textColor=INK)
    first, *others = i18n.t_all("pdf.owner", book.languages)
    bottom = centered(c, first, style, x, layout.height * 0.6, w)
    second = ParagraphStyle("owner2", fontName=fonts.italic, fontSize=18, leading=22, alignment=TA_CENTER, textColor=MUTED)
    for text in others:
        bottom = centered(c, text, second, x, bottom - 4, w)
    c.setStrokeColor(INK)
    c.setLineWidth(1.5)
    c.line(x + w * 0.12, bottom - 0.9 * inch, x + w * 0.88, bottom - 0.9 * inch)
    c.showPage()


def _draw_template(c: Canvas, book: Book, page: Page, layout: Layout) -> None:
    """The page's template, behind everything, embedded losslessly like line art."""
    template = page_templates.for_page(book, page)
    if template is None:
        return
    image_box, _ = page_templates.placement(book, template, layout.content)
    art = page_templates.image(book, template, layout.content).convert("L")
    draw_fitted(c, ImageReader(art), art.size, image_box)


def _draw_sheet(c: Canvas, book: Book, page: Page, number: int, layout: Layout, fonts: Fonts) -> None:
    _draw_template(c, book, page, layout)
    art_box, info = layout.boxes(_shows_info(book, page), sheet_area(book, page, layout))
    draw_line_art(c, pages.selected_path(book.slug, page), art_box)

    if info:
        c.setStrokeColor(INK)
        c.setLineWidth(1.2)
        c.roundRect(*info, RADIUS)
        photo = None
        if book.include_reference_photo:
            # The real photo for the reader: with its curve, without the color grouping.
            photo_reader, photo_size = _photo_reader(pages.cropped_photo(book.slug, page, group=False))
            photo = _photo_box(info, photo_size)
            c.drawImage(photo_reader, *photo)
            c.setLineWidth(0.6)
            c.rect(*photo)
        if page.has_caption:
            tx, ty, tw, th = _text_box(info, photo)
            items, total, fits = fit_text(lambda scale: _caption(book, page, scale, fonts), tw, th)
            draw_text(c, items, (tx, ty, tw, th), ty + th - (th - total) / 2 if fits else ty + th)

    c.setFont(fonts.regular, 10)
    c.setFillColor(MUTED)
    c.drawCentredString(layout.width / 2, MARGIN, str(number))
    c.showPage()


def mosaic_of(book: Book, page: Page) -> tuple[np.ndarray, MosaicSettings]:
    """The grid and settings of the page's selected (mosaic) version."""
    version = page.selected_version
    grid = mosaic.load_grid(pages.version_path(book.slug, page.id, version.n, raw=True))
    return grid, version.mosaic or mosaic.default_settings(book.age_group)


MOSAIC_HEADING = 44  # points: the mosaic page's number and how to play, above the grid


def mosaic_grid_box(book: Book) -> tuple[float, float, float, float]:
    """Where a mosaic page puts its grid, in points: the cell size depends on it."""
    x, y, w, h = _layout(book).content
    legend_h = mosaic.legend_height(book.languages)
    return x, y + legend_h + GAP, w, h - MOSAIC_HEADING - legend_h - 2 * GAP


def mosaic_cell_mm(book: Book, rows: int, cols: int) -> float:
    """Side of a mosaic cell as printed, in millimeters."""
    _, _, w, h = mosaic_grid_box(book)
    return min(w / cols, h / rows) / inch * 25.4


def _draw_mosaic_sheet(
    c: Canvas, book: Book, grid: np.ndarray, settings: MosaicSettings, number: int, mystery: int, layout: Layout, fonts: Fonts
) -> None:
    """A mystery mosaic: its number and how to play, the faint grid, and the legend.

    No title and no reference photo, which would give the picture away: both are on the
    solutions page.
    """
    x, y, w, h = layout.content
    top = y + h
    c.setFillColor(INK)
    c.setFont(fonts.bold, 18)
    c.drawCentredString(x + w / 2, top - 18, extras.label("pdf.mosaic_title", book, n=mystery))
    c.setFillColor(MUTED)
    c.setFont(fonts.italic, 11)
    c.drawCentredString(x + w / 2, top - 36, extras.label("pdf.mosaic_hint", book))
    legend_h = mosaic.legend_height(book.languages)
    mosaic.draw_puzzle(c, grid, settings, mosaic_grid_box(book), fonts.regular)
    mosaic.draw_legend(c, settings, (x, y, w, legend_h), fonts, book.languages)

    if number:  # the workbench preview has none
        c.setFont(fonts.regular, 10)
        c.setFillColor(MUTED)
        c.drawCentredString(layout.width / 2, MARGIN, str(number))
    c.showPage()


# --- Public API ---------------------------------------------------------------------


def exports_dir(book: Book) -> Path:
    return book_path(book.slug) / "exports"


def preflight(book: Book) -> Preflight:
    report = Preflight()
    fonts = load_fonts()
    for page in pages.load_pages(book.slug):
        if not page.in_book:
            continue
        if pages.selected_path(book.slug, page) is None:
            report.without_version.append(page)
            continue
        report.included.append(page)
        if page.status != "approved":
            report.not_approved.append(page)
        if not page.is_mosaic and not caption_fits(book, page, fonts):
            report.overflowing.append(page)
    ready = extras.available(book, report.included)
    report.extras_missing = [extra for extra in book.extras if extra not in ready]
    return report


def sheets(book: Book, included: list[Page]) -> list[Sheet]:
    """Every page of the interior, in print order.

    The copyright page, when there is one, is the back of the title page. With blank
    backs every coloring page is a right-hand page with nothing printed behind it.
    """
    back = ["blank"] if book.blank_backs else []
    ready = extras.available(book, included)
    order: list[Sheet] = ["title"]
    order += ["legal"] if has_legal_page(book, included) else back
    if book.include_owner_page:
        order += ["owner", *back]
    if "color_test" in ready:
        order += ["color_test", *back]
    for page in included:
        order += [page, *back]
    # The mystery mosaics' solutions go after the activities, before the diploma and closing page.
    after = [extra for extra in ready if extra != "color_test"]
    split = next((i for i, extra in enumerate(after) if extra in ("diploma", "closing")), len(after))
    for extra in after[:split] + extras.mosaic_solution_sheets(included) + after[split:]:
        order += [extra, *back]
    return order


def export_book_pdf(book: Book, path: Path | None = None) -> Path:
    """Build the PDF and return its path. Pages without a coloring page are skipped.

    Without ``path`` it is a new file under ``exports/``.
    """
    included = preflight(book).included
    if not included:
        raise ValueError("No coloring pages to export yet.")
    layout = _layout(book)
    fonts = load_fonts()
    cover = next((p for p in included if p.id == book.cover_page_id), included[0])

    if path is None:
        folder = exports_dir(book)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = folder / f"{book.slug}-{stamp}.pdf"

    # ReportLab sets the initial font on every page; the default (Helvetica) is never embedded.
    c = Canvas(str(path), pagesize=(layout.width, layout.height), initialFontName=fonts.regular)
    c.setTitle(book.title)
    c.setCreator("Colorín Colorado")

    mysteries = {page.id: n for n, page in enumerate(extras.mysteries(included), start=1)}
    number = 0
    for sheet in sheets(book, included):
        if isinstance(sheet, Page):
            number += 1
            if sheet.is_mosaic:
                _draw_mosaic_sheet(c, book, *mosaic_of(book, sheet), number, mysteries[sheet.id], layout, fonts)
            else:
                _draw_sheet(c, book, sheet, number, layout, fonts)
        elif sheet == "title":
            _draw_title_page(c, book, cover, layout, fonts)
        elif sheet == "legal":
            _draw_legal_page(c, book, included, layout, fonts)
        elif sheet == "owner":
            _draw_owner_page(c, book, layout, fonts)
        elif sheet == "blank":
            c.showPage()
        else:
            extras.draw(sheet, c, book, included, fonts, layout.content)
            c.showPage()
    c.save()
    return path


def page_preview(book: Book, page: Page, dpi: int = 60) -> Image.Image:
    """A coloring page as it will print, template included, for the workbench."""
    layout = _layout(book)
    fonts = load_fonts()
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=(layout.width, layout.height), initialFontName=fonts.regular)
    _draw_sheet(c, book, page, 1, layout, fonts)
    c.save()
    pdf = pdfium.PdfDocument(buffer.getvalue())
    try:
        return pdf[0].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()


def mosaic_preview(book: Book, page: Page, grid: np.ndarray, settings: MosaicSettings, dpi: int = 100) -> Image.Image:
    """A mystery mosaic of the page as it will print, for the workbench: its stored grid or
    one not saved yet."""
    layout = _layout(book)
    fonts = load_fonts()
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=(layout.width, layout.height), initialFontName=fonts.regular)
    included = [p for p in pages.load_pages(book.slug) if p.in_book and (p.is_mosaic or p.id == page.id)]
    mystery = next((n for n, p in enumerate(included, start=1) if p.id == page.id), 1)
    _draw_mosaic_sheet(c, book, grid, settings, 0, mystery, layout, fonts)
    c.save()
    pdf = pdfium.PdfDocument(buffer.getvalue())
    try:
        return pdf[0].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
