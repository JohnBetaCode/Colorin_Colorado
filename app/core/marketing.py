"""Images for the Amazon product page and social media, made from the book's own PDFs.

``listing_images`` builds the interior and the cover into a temporary folder, renders
them with pdfium, and composes:
  - ``mockup.jpg``: the book standing at a slight angle, spine visible, with a shadow;
  - ``inside.jpg``: three coloring pages fanned out, a "look inside";
  - ``front.jpg``: the front cover alone.
Nothing is drawn by the AI, so the images show exactly what buyers get. The ZIP goes to
``exports/marketing/<slug>-images-<timestamp>.zip``.
"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter

from app.core import cover, export, kdp
from app.core.schema import Book, Page

RENDER_DPI = 150
SQUARE = 2000  # px, the mockup
INSIDE_SIZE = (2400, 1600)
FRONT_HEIGHT = 2400
JPEG_QUALITY = 90
INSIDE_PAGES = 3
BACKGROUND = ((252, 250, 246), (230, 226, 218))  # top and bottom of a soft gradient


def marketing_dir(book: Book) -> Path:
    return export.exports_dir(book) / "marketing"


def _render(path: Path, index: int, dpi: int = RENDER_DPI) -> Image.Image:
    pdf = pdfium.PdfDocument(str(path))
    try:
        return pdf[index].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()


def _background(size: tuple[int, int]) -> Image.Image:
    top, bottom = (np.array(c, dtype=float) for c in BACKGROUND)
    ramp = np.linspace(0, 1, size[1])[:, None, None]
    rows = (top + (bottom - top) * ramp).astype(np.uint8)
    return Image.fromarray(np.repeat(rows, size[0], axis=1))


def _coefficients(quad: list[tuple[float, float]], size: tuple[int, int]) -> list[float]:
    """PIL perspective coefficients that map the output ``quad`` onto the whole source image."""
    w, h = size
    source = [(0, 0), (w, 0), (w, h), (0, h)]
    rows = []
    for (x, y), (u, v) in zip(quad, source):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(rows, float), np.array(source, float).reshape(8)).tolist()


def _warp(image: Image.Image, quad: list[tuple[float, float]], size: tuple[int, int]) -> Image.Image:
    """``image`` drawn into ``quad`` on a transparent canvas of ``size``."""
    rgba = image.convert("RGBA")
    return rgba.transform(size, Image.Transform.PERSPECTIVE, _coefficients(quad, image.size), Image.Resampling.BICUBIC)


def _shadow(canvas: Image.Image, polygon: list[tuple[float, float]], offset: tuple[int, int], blur: int, alpha: int) -> None:
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).polygon([(x + offset[0], y + offset[1]) for x, y in polygon], fill=alpha)
    canvas.paste((40, 34, 28), (0, 0), mask.filter(ImageFilter.GaussianBlur(blur)))


def mockup(front: Image.Image, spine_color: tuple[int, int, int]) -> Image.Image:
    """The book standing slightly turned: front in perspective, spine on the left."""
    canvas = _background((SQUARE, SQUARE))
    h = int(SQUARE * 0.74)
    w = int(front.width * h / front.height)
    spine = max(int(w * 0.07), 24)
    left, top = (SQUARE - w - spine) // 2, (SQUARE - h) // 2 - int(SQUARE * 0.02)
    drop = h * 0.035  # how much the far edges shrink
    front_quad = [(left + spine, top), (left + spine + w, top + drop), (left + spine + w, top + h - drop), (left + spine, top + h)]
    spine_quad = [(left, top + drop * 0.6), (left + spine, top), (left + spine, top + h), (left, top + h - drop * 0.6)]
    _shadow(canvas, [front_quad[1], front_quad[2], spine_quad[3], (left, top + h)], (int(SQUARE * 0.025), int(SQUARE * 0.02)), 40, 120)
    darker = tuple(int(c * 0.72) for c in spine_color)
    ImageDraw.Draw(canvas).polygon(spine_quad, fill=darker)
    warped = _warp(front, front_quad, canvas.size)
    canvas.paste(warped, (0, 0), warped)
    # A soft highlight on the hinge where the cover bends.
    hinge = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(hinge).line([front_quad[0], front_quad[3]], fill=90, width=max(4, spine // 6))
    canvas.paste((255, 255, 255), (0, 0), hinge.filter(ImageFilter.GaussianBlur(3)))
    return canvas


def inside(pages_: list[Image.Image]) -> Image.Image:
    """A few interior pages fanned out on the background."""
    canvas = _background(INSIDE_SIZE)
    height = int(INSIDE_SIZE[1] * 0.8)
    angles = [-5, 0, 5][: len(pages_)] if len(pages_) == 3 else [0] * len(pages_)
    step = INSIDE_SIZE[0] / (len(pages_) + 1)
    for i, (page, angle) in enumerate(zip(pages_, angles)):
        page = page.resize((int(page.width * height / page.height), height), Image.Resampling.LANCZOS).convert("RGBA")
        rotated = page.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        cx, cy = int(step * (i + 1)), INSIDE_SIZE[1] // 2
        x, y = cx - rotated.width // 2, cy - rotated.height // 2
        shadow = Image.new("L", canvas.size, 0)
        shadow.paste(rotated.getchannel("A").point(lambda a: 110 if a else 0), (x + 18, y + 22))
        canvas.paste((40, 34, 28), (0, 0), shadow.filter(ImageFilter.GaussianBlur(22)))
        canvas.paste(rotated, (x, y), rotated)
    return canvas


def _jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def listing_images(book: Book, included: list[Page]) -> dict[str, bytes]:
    """The listing images as JPEG bytes by file name."""
    with tempfile.TemporaryDirectory() as folder:
        interior = export.export_book_pdf(book, Path(folder) / "interior.pdf")
        wrap = cover.export_cover_pdf(book, Path(folder) / "cover.pdf")
        sheets = export.sheets(book, included)
        coloring = [i for i, sheet in enumerate(sheets) if isinstance(sheet, Page)][:INSIDE_PAGES]
        inside_pages = [_render(interior, i, 110) for i in coloring]
        full = _render(wrap, 0)
    count = len(sheets)
    scale = RENDER_DPI
    trim_w, trim_h = kdp.TRIM[book.page_size]
    spine = kdp.spine_width(count, book.kdp_ink)
    x0 = round((kdp.BLEED + trim_w + spine) * scale)
    front = full.crop((x0, round(kdp.BLEED * scale), x0 + round(trim_w * scale), round((kdp.BLEED + trim_h) * scale)))
    # The spine's color, or the back cover's next to it when the spine is too thin to sample.
    sx = round((kdp.BLEED + trim_w) * scale)
    sample = full.crop((sx - 6, full.height // 3, sx + max(round(spine * scale), 2), full.height // 3 + 40))
    spine_color = tuple(int(c) for c in np.asarray(sample).reshape(-1, 3).mean(axis=0))
    front_big = front.resize((int(front.width * FRONT_HEIGHT / front.height), FRONT_HEIGHT), Image.Resampling.LANCZOS)
    return {
        "mockup.jpg": _jpeg(mockup(front, spine_color)),
        "inside.jpg": _jpeg(inside(inside_pages)),
        "front.jpg": _jpeg(front_big),
    }


def export_listing_images(book: Book, included: list[Page]) -> Path:
    """Build the listing images into a ZIP under ``exports/marketing/``; returns its path."""
    images = listing_images(book, included)
    folder = marketing_dir(book)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{book.slug}-images-{stamp}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in images.items():
            archive.writestr(name, data)
    return path
