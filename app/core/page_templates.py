"""Page templates: a decorative design around a coloring page (a frame of stars, clouds and
grass, flowers in the corners...), chosen for the book and changed per page.

Predefined designs are drawn here as closed outlines, so the frame can be colored too, at the
proportions of the page they go on, so they never stretch. The author can also upload images:
they become 1-bit like any coloring page and are stored as ``page_templates/<id>.png``.

Every template has an *area*: the part of it (fractions of the template, left, top, right,
bottom) where the drawing and its caption box go. Predefined designs know theirs; for an
uploaded image it is found by itself as the largest empty rectangle, and the author can
adjust it. Templates are drawn only on coloring pages, not on mosaics or extra pages.
"""

from __future__ import annotations

import math
import uuid
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.core import books, lineart
from app.core.books import book_path, inside, now
from app.core.schema import Book, Page, PageTemplate

Box = tuple[float, float, float, float]
Area = tuple[float, float, float, float]

NO_TEMPLATE = "none"  # a page that wants no template even when the book has one
DPI = 300  # predefined designs are drawn at print resolution
UPLOAD_PX = 3000  # long side of a stored uploaded template
DEFAULT_AREA: Area = (0.1, 0.1, 0.9, 0.9)
MAX_INSET = 15  # percent of the area, per page

# Predefined designs and how far their drawing area stays from each edge (left, top, right,
# bottom), in units of the page's short side: every design is drawn in those units from the
# edges, so the clearance is the same on any page size.
PREDEFINED: dict[str, Area] = {
    "frame": (0.06, 0.06, 0.06, 0.06),
    "stars": (0.13, 0.13, 0.13, 0.13),
    "clouds": (0.04, 0.22, 0.04, 0.25),
    "flowers": (0.14, 0.14, 0.14, 0.14),
    "waves": (0.1, 0.05, 0.1, 0.22),
    "scallops": (0.1, 0.1, 0.1, 0.1),
}


# --- Drawing the predefined designs -----------------------------------------------------


def _outline(mask: np.ndarray, width: int) -> np.ndarray:
    """The outlines (outer and inner) of the filled shapes in ``mask``."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    ink = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(ink, contours, -1, 1, width)
    return ink.astype(bool)


def _rounded(mask: np.ndarray, x0: int, y0: int, x1: int, y1: int, r: int) -> None:
    cv2.rectangle(mask, (x0 + r, y0), (x1 - r, y1), 1, -1)
    cv2.rectangle(mask, (x0, y0 + r), (x1, y1 - r), 1, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(mask, (cx, cy), r, 1, -1)


def _frame_ring(shape: tuple[int, int], outer: float, inner: float) -> np.ndarray:
    """A rounded band between two insets, as fractions of the short side."""
    h, w = shape
    s = min(w, h)
    mask = np.zeros(shape, np.uint8)
    a, b = round(outer * s), round(inner * s)
    _rounded(mask, a, a, w - a, h - a, round(0.05 * s))
    hole = np.zeros(shape, np.uint8)
    _rounded(hole, b, b, w - b, h - b, round(0.035 * s))
    return mask & (1 - hole)


def _star(mask: np.ndarray, cx: float, cy: float, r: float, turn: float = 0.0) -> None:
    points = [
        (cx + (r if i % 2 == 0 else r * 0.45) * math.sin(turn + i * math.pi / 5), cy - (r if i % 2 == 0 else r * 0.45) * math.cos(turn + i * math.pi / 5))
        for i in range(10)
    ]
    cv2.fillPoly(mask, [np.array(points, np.int32)], 1)


def _along_edges(w: int, h: int, inset: float, step: float) -> list[tuple[float, float]]:
    """Points spread around a rectangle ``inset`` from the sides, about ``step`` apart."""
    x0, y0, x1, y1 = inset, inset, w - inset, h - inset
    points = []
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        n = max(1, round(math.hypot(bx - ax, by - ay) / step))
        points += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
    return points


def _draw(design: str, w: int, h: int) -> np.ndarray:
    """The ink of a predefined design at ``w`` × ``h`` pixels (bool)."""
    s = min(w, h)
    width = max(4, round(s * 0.0045))
    ink = np.zeros((h, w), bool)
    if design == "frame":
        ink |= _outline(_frame_ring((h, w), 0.012, 0.035), width)
    elif design == "stars":
        mask = np.zeros((h, w), np.uint8)
        r = 0.035 * s
        for i, (x, y) in enumerate(_along_edges(w, h, 0.055 * s, 0.11 * s)):
            _star(mask, x, y, r * (1.0 if i % 2 == 0 else 0.75), turn=0.3 * (i % 3 - 1))
        ink |= _outline(mask, width)
        ink |= _outline(_frame_ring((h, w), 0.1, 0.11), width)
    elif design == "clouds":
        clouds = np.zeros((h, w), np.uint8)
        for i, cx in enumerate(np.linspace(0.12 * w, 0.88 * w, 4)):
            cy = (0.09 + (0.02 if i % 2 else 0)) * s
            for dx, dy, rr in ((-0.07, 0.01, 0.045), (0, -0.015, 0.06), (0.07, 0.01, 0.045), (0, 0.025, 0.045)):
                cv2.circle(clouds, (round(cx + dx * s), round(cy + dy * s)), round(rr * s), 1, -1)
        hills = np.zeros((h, w), np.uint8)
        for cx, rr in ((0.15, 0.32), (0.55, 0.38), (0.95, 0.3)):
            cv2.circle(hills, (round(cx * w), round(h + rr * s * 0.55)), round(rr * s), 1, -1)
        grass = np.zeros((h, w), np.uint8)
        ink |= _outline(clouds, width) | _outline(hills, width)
        for k in range(9):  # little closed blades along the hills' top
            x = round((0.06 + k * 0.11) * w)
            top = int(np.argmax(hills[:, x])) if hills[:, x].any() else h
            blade = np.array([(x - 0.012 * s, top), (x, top - 0.05 * s), (x + 0.012 * s, top)], np.int32)
            cv2.fillPoly(grass, [blade], 1)
        ink |= _outline(grass, width)
    elif design == "flowers":
        mask = np.zeros((h, w), np.uint8)
        centers = np.zeros((h, w), np.uint8)
        d = 0.065 * s  # flower centers, from both edges of each corner
        for x, y in ((d, d), (w - d, d), (d, h - d), (w - d, h - d)):
            for k in range(6):
                angle = k * math.pi / 3
                cv2.circle(mask, (round(x + 0.032 * s * math.cos(angle)), round(y + 0.032 * s * math.sin(angle))), round(0.024 * s), 1, -1)
            cv2.circle(centers, (round(x), round(y)), round(0.018 * s), 1, -1)
        ink |= _outline(mask & (1 - centers), width) | _outline(centers, width)
        ring = _frame_ring((h, w), 0.075, 0.085)
        ink |= _outline(ring & (1 - mask), width)
    elif design == "waves":
        xs = np.arange(w)
        for rise, amp, phase in ((0.17, 0.018, 0.0), (0.1, 0.015, 1.7)):
            ys = (h - rise * s + amp * s * np.sin(xs / w * 6 * math.pi + phase)).astype(np.int32)
            poly = np.vstack([np.column_stack([xs, ys]), [[w - 1, h - 1], [0, h - 1]]]).astype(np.int32)
            layer = np.zeros((h, w), np.uint8)
            cv2.fillPoly(layer, [poly], 1)
            ink |= _outline(layer, width)
        bubbles = np.zeros((h, w), np.uint8)
        rng = np.random.default_rng(7)
        for x in (0.045 * s, w - 0.045 * s):
            for y in np.linspace(0.08 * s, h - 0.25 * s, 7):
                cv2.circle(bubbles, (round(x + rng.uniform(-0.01, 0.01) * s), round(y)), round(rng.uniform(0.012, 0.025) * s), 1, -1)
        ink |= _outline(bubbles, width)
    elif design == "scallops":
        mask = np.zeros((h, w), np.uint8)
        r = 0.035 * s
        for x, y in _along_edges(w, h, 0.045 * s, 1.6 * r):
            cv2.circle(mask, (round(x), round(y)), round(r), 1, -1)
        _rounded(mask, round(0.045 * s), round(0.045 * s), w - round(0.045 * s), h - round(0.045 * s), round(0.02 * s))
        hole = np.zeros((h, w), np.uint8)
        _rounded(hole, round(0.08 * s), round(0.08 * s), w - round(0.08 * s), h - round(0.08 * s), round(0.03 * s))
        ink |= _outline(mask & (1 - hole), width)
    return ink


@lru_cache(maxsize=16)
def _predefined(design: str, w: int, h: int) -> Image.Image:
    return Image.fromarray(np.where(_draw(design, w, h), 0, 255).astype(np.uint8)).convert("1")


# --- Uploaded templates ----------------------------------------------------------------


def _largest_rectangle(free: np.ndarray) -> tuple[int, int, int, int]:
    """Largest all-True rectangle of ``free``: top, left, bottom, right (exclusive)."""
    h, w = free.shape
    heights = np.zeros(w, int)
    best_area, best = 0, (0, 0, 0, 0)
    for r in range(h):
        heights = np.where(free[r], heights + 1, 0)
        stack: list[tuple[int, int]] = []
        for c in range(w + 1):
            current = int(heights[c]) if c < w else 0
            start = c
            while stack and stack[-1][1] > current:
                index, height = stack.pop()
                if height * (c - index) > best_area:
                    best_area, best = height * (c - index), (r - height + 1, index, r + 1, c)
                start = index
            stack.append((start, current))
    return best


def find_area(ink: np.ndarray) -> Area:
    """Where the drawing fits in an uploaded template: its largest empty rectangle, with a
    small margin, or ``DEFAULT_AREA`` when the empty part is too small."""
    h, w = ink.shape
    scale = 240 / max(h, w)
    small = cv2.resize(ink.astype(np.float32), (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    top, left, bottom, right = _largest_rectangle(small < 0.01)
    sh, sw = small.shape
    if (bottom - top) * (right - left) < 0.2 * sh * sw:
        return DEFAULT_AREA
    margin = 0.015
    return (left / sw + margin, top / sh + margin, right / sw - margin, bottom / sh - margin)


def uploaded_path(book: Book, template_id: str) -> Path:
    folder = book_path(book.slug) / "page_templates"
    return inside(folder, folder / f"{template_id}.png")


def add_upload(book: Book, data: bytes, name: str) -> Book:
    """Store an uploaded image as a 1-bit template with its area. Raises ``ValueError``."""
    try:
        image = lineart.load_image(data)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    image.thumbnail((UPLOAD_PX, UPLOAD_PX))
    gray = np.asarray(image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = binary < 128
    template = PageTemplate(
        id=f"u{uuid.uuid4().hex[:10]}", name=name.strip()[:60] or "Plantilla", area=find_area(ink), created_at=now()
    )
    path = uploaded_path(book, template.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).convert("1").save(path)
    book.page_templates.append(template)
    books.save_book(book)
    return book


def set_area(book: Book, template_id: str, area: Area) -> Book:
    left, top, right, bottom = (min(max(v, 0.0), 1.0) for v in area)
    if right - left < 0.1 or bottom - top < 0.1:
        raise ValueError("The area is too small.")
    for template in book.page_templates:
        if template.id == template_id:
            template.area = (left, top, right, bottom)
    books.save_book(book)
    return book


def delete_upload(book: Book, template_id: str) -> Book:
    """Remove an uploaded template; pages that used it fall back to the book's template."""
    uploaded_path(book, template_id).unlink(missing_ok=True)
    book.page_templates = [t for t in book.page_templates if t.id != template_id]
    if book.page_template == template_id:
        book.page_template = None
    books.save_book(book)
    return book


# --- Choosing and placing ---------------------------------------------------------------


def choices(book: Book) -> list[str]:
    """Every template the book can use: the predefined designs, then its uploads."""
    return [*PREDEFINED, *(t.id for t in book.page_templates)]


def name(book: Book, template_id: str, label) -> str:
    """Display name: ``label(key)`` translates predefined names; uploads keep theirs."""
    if template_id in PREDEFINED:
        return label(f"page_template.{template_id}")
    return next((t.name for t in book.page_templates if t.id == template_id), template_id)


def for_page(book: Book, page: Page) -> str | None:
    """The template a coloring page is printed with, or None."""
    chosen = book.page_template if page.page_template is None else page.page_template
    return chosen if chosen in choices(book) else None


def area_fractions(book: Book, template_id: str, size: tuple[float, float]) -> Area:
    """The template's drawing area for an image of ``size``: left, top, right, bottom, as
    fractions of it."""
    if template_id in PREDEFINED:
        w, h = size
        s = min(w, h)
        left, top, right, bottom = PREDEFINED[template_id]
        return left * s / w, top * s / h, 1 - right * s / w, 1 - bottom * s / h
    return next((t.area for t in book.page_templates if t.id == template_id), DEFAULT_AREA)


def image(book: Book, template_id: str, box: Box) -> Image.Image:
    """The template as a 1-bit image for ``box`` (points): predefined designs are drawn at the
    box's proportions, uploads keep their own."""
    if template_id in PREDEFINED:
        return _predefined(template_id, round(box[2] / 72 * DPI), round(box[3] / 72 * DPI))
    with Image.open(uploaded_path(book, template_id)) as stored:
        return stored.convert("1")


def placement(book: Book, template_id: str, box: Box) -> tuple[Box, Box]:
    """Where the template lands in ``box`` (fitted, centered) and its area there, in points."""
    x, y, w, h = box
    if template_id in PREDEFINED:
        image_box = box
    else:
        iw, ih = image(book, template_id, box).size
        scale = min(w / iw, h / ih)
        image_box = (x + (w - iw * scale) / 2, y + (h - ih * scale) / 2, iw * scale, ih * scale)
    ix, iy, iw_, ih_ = image_box
    left, top, right, bottom = area_fractions(book, template_id, (iw_, ih_))
    area = (ix + left * iw_, iy + (1 - bottom) * ih_, (right - left) * iw_, (bottom - top) * ih_)
    return image_box, area


def drawing_box(book: Book, template_id: str, box: Box, inset: int = 0) -> Box:
    """The part of ``box`` the drawing and caption use with this template and page inset."""
    _, (x, y, w, h) = placement(book, template_id, box)
    d = min(max(inset, 0), MAX_INSET) / 100 * min(w, h)
    return x + d, y + d, w - 2 * d, h - 2 * d


def thumbnail(book: Book, template_id: str, size: tuple[float, float], px: int = 360) -> Image.Image:
    """A small picture of the template with its area shaded, for choosing it."""
    w, h = size
    scale = px / max(w, h)
    box = (0.0, 0.0, w, h)
    art = image(book, template_id, box).convert("L")
    canvas = Image.new("RGB", (round(w * scale), round(h * scale)), "white")
    image_box, area = placement(book, template_id, box)
    ix, iy, iw, ih = (v * scale for v in image_box)
    canvas.paste(art.resize((max(1, round(iw)), max(1, round(ih))), Image.Resampling.LANCZOS).convert("RGB"), (round(ix), round(canvas.height - iy - ih)))
    ax, ay, aw, ah = (v * scale for v in area)
    shade = Image.new("RGB", (max(1, round(aw)), max(1, round(ah))), (226, 238, 250))
    canvas.paste(shade, (round(ax), round(canvas.height - ay - ah)))
    return canvas
