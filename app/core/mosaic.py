"""Mystery mosaics: the third engine, free and offline, for monochrome color-by-number pages.

The photo is turned to gray and divided into a grid of square cells, or of cells that may be
split along a diagonal into two triangles where that follows an edge better. Every cell (or
triangle) gets one of 2 to 5 tones, from black to white. The printed page shows the grid and a
symbol in every cell, both faint, and a legend that says how to fill each symbol: a pencil tone
or a pen pattern. Filled in, the photo appears. Nothing is drawn by the AI.

A mosaic is stored as data, not as a picture: ``v<n>-raw.png`` is the grid, one pixel per cell
(red: the tone of the cell or of its first triangle, green: the tone of the second triangle,
blue: the split). The PDF draws it as vectors, so the faint lines and symbols print sharp at any
size. ``v<n>.png`` is the solution in 1 bit, for the workbench, the thumbnails and the cover; it
does not go through ``lineart.clean``, which would hollow out the black cells.
"""

from __future__ import annotations

import math
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas

from app.core import i18n
from app.core.schema import Book, MosaicSettings, Page

if TYPE_CHECKING:
    from app.core.export import Fonts

Box = tuple[float, float, float, float]
Point = tuple[float, float]

MIN_TONES, MAX_TONES = 2, 5
MIN_COLUMNS = 8
# Symbols inside triangles are smaller, so diagonal cells need a coarser grid to stay legible.
MAX_COLUMNS = {"square": 60, "diagonal": 40}
LIMIT = 50  # contrast and brightness, in percent either way

# Per age group: few big cells and tones for small children, a fine grid for adults.
AGE_DEFAULTS = {
    "3-5": {"columns": 14, "tones": 2},
    "6-8": {"columns": 22, "tones": 3},
    "9+": {"columns": 32, "tones": 4},
    "adult": {"columns": 45, "tones": 5},
}

SAMPLES = 8  # pixels per cell side when measuring tones
EQUALIZE = 0.6  # share of histogram equalization in the tone mapping (see _adjust)
# A cell is split only when its two triangles bring the error down to this share of the
# whole cell's: flat areas stay whole squares, edges get a diagonal.
SPLIT_GAIN = 0.6
WHOLE, SLASH, BACKSLASH = 0, 1, 2  # blue channel of the grid: no split, "/" or "\"

SYMBOLS = {"numbers": "12345", "letters": "ABCDE", "signs": "!?#&%"}
SHAPES = ("circle", "triangle", "square", "diamond", "plus")  # drawn, not typed
# What each tone is called (pencil) or how it is filled (pen), from black to white.
TONE_NAMES = {
    2: ("black", "white"),
    3: ("black", "mid", "white"),
    4: ("black", "dark", "light", "white"),
    5: ("black", "dark", "mid", "light", "white"),
}
PATTERNS = {
    2: ("solid", "empty"),
    3: ("solid", "lines", "empty"),
    4: ("solid", "cross", "lines", "empty"),
    5: ("solid", "cross", "lines", "dots", "empty"),
}

# The puzzle is printed faint, so the filled-in tones cover it.
FAINT_LINE = 0.72
FAINT_SYMBOL = 0.6
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")
SOLUTION_PX = 2400  # long side of the stored solution, like a cleaned coloring page


# --- Settings ---------------------------------------------------------------------


def default_settings(age_group: str) -> MosaicSettings:
    return MosaicSettings(**AGE_DEFAULTS[age_group])


def settings_for(book: Book, page: Page) -> MosaicSettings:
    """The page's own settings, else the book's, else the age group's."""
    return normalized(page.mosaic or book.mosaic or default_settings(book.age_group))


def normalized(settings: MosaicSettings) -> MosaicSettings:
    """``settings`` with every number inside its range."""

    def clamp(value: int, low: int, high: int) -> int:
        return max(low, min(high, int(value)))

    return settings.model_copy(
        update={
            "tones": clamp(settings.tones, MIN_TONES, MAX_TONES),
            "columns": clamp(settings.columns, MIN_COLUMNS, MAX_COLUMNS[settings.cells]),
            "contrast": clamp(settings.contrast, -LIMIT, LIMIT),
            "brightness": clamp(settings.brightness, -LIMIT, LIMIT),
        }
    )


# --- Grid -------------------------------------------------------------------------


def _adjust(gray: np.ndarray, settings: MosaicSettings) -> np.ndarray:
    """Spread the photo's tones over the full range, then apply contrast and brightness.

    A plain stretch leaves most photos in the middle tones (a bird in grass is all mid
    gray), so it is blended with histogram equalization, which gives every tone a fair
    share of the cells.
    """
    low, high = np.percentile(gray, (1, 99))
    stretched = np.clip((gray - low) / max(float(high - low), 1e-3), 0, 1)
    ranked = np.sort(gray, axis=None)
    equalized = np.searchsorted(ranked, gray, side="right") / ranked.size
    value = EQUALIZE * equalized + (1 - EQUALIZE) * stretched
    value = (value - 0.5) * (1 + settings.contrast / 100) + 0.5 + settings.brightness / 100
    return np.clip(value, 0, 1)


def _quantize(value: np.ndarray, tones: int) -> np.ndarray:
    return np.clip((value * tones).astype(int), 0, tones - 1)


def _error(total: np.ndarray, squares: np.ndarray, weight: float, tone: np.ndarray, tones: int) -> np.ndarray:
    """Sum of squared differences between the pixels and the tone's middle value."""
    center = (tone + 0.5) / tones
    return squares - 2 * center * total + center * center * weight


def make_grid(photo: Image.Image, settings: MosaicSettings) -> np.ndarray:
    """The mosaic of a (cropped) photo: ``(rows, columns, 3)`` uint8, see the module docstring."""
    settings = normalized(settings)
    gray = np.asarray(photo.convert("L"), dtype=np.float32) / 255
    h, w = gray.shape
    cols = settings.columns
    rows = max(1, round(cols * h / w))
    k, tones = SAMPLES, settings.tones
    small = cv2.resize(gray, (cols * k, rows * k), interpolation=cv2.INTER_AREA)
    cells = _adjust(small, settings).reshape(rows, k, cols, k).transpose(0, 2, 1, 3)

    total, squares = cells.sum(axis=(2, 3)), (cells * cells).sum(axis=(2, 3))
    whole = _quantize(total / (k * k), tones)
    grid = np.zeros((rows, cols, 3), np.uint8)
    grid[..., 0] = grid[..., 1] = whole
    if settings.cells == "square":
        return grid

    best = _error(total, squares, k * k, whole, tones) * SPLIT_GAIN
    i, j = np.indices((k, k))
    # Weight of each pixel in the first triangle; pixels on the diagonal count half.
    first = {
        SLASH: (i + j < k - 1) + 0.5 * (i + j == k - 1),  # "/": the upper-left triangle
        BACKSLASH: (j > i) + 0.5 * (j == i),  # "\": the upper-right triangle
    }
    for split, mask in first.items():
        mask = mask.astype(np.float32)
        weight_a = float(mask.sum())
        total_a = np.einsum("rcij,ij->rc", cells, mask)
        squares_a = np.einsum("rcij,ij->rc", cells * cells, mask)
        tone_a = _quantize(total_a / weight_a, tones)
        tone_b = _quantize((total - total_a) / (k * k - weight_a), tones)
        error = _error(total_a, squares_a, weight_a, tone_a, tones) + _error(
            total - total_a, squares - squares_a, k * k - weight_a, tone_b, tones
        )
        better = (error < best) & (tone_a != tone_b)
        grid[better] = np.stack([tone_a, tone_b, np.full_like(tone_a, split)], axis=-1)[better]
        best = np.where(better, error, best)
    return grid


def grid_png(grid: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(np.ascontiguousarray(grid, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def load_grid(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def shapes(grid: np.ndarray) -> list[tuple[int, list[Point]]]:
    """Every cell or triangle as (tone, corners), in cell units from the top left, y down.

    All polygons wind the same way, so one path can hold many of them.
    """
    result = []
    rows, cols, _ = grid.shape
    for r in range(rows):
        for c in range(cols):
            a, b, split = (int(v) for v in grid[r, c])
            tl, tr, br, bl = (c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)
            if split == SLASH:
                result += [(a, [tl, tr, bl]), (b, [tr, br, bl])]
            elif split == BACKSLASH:
                result += [(a, [tl, tr, br]), (b, [tl, br, bl])]
            else:
                result.append((a, [tl, tr, br, bl]))
    return result


# --- Drawing ----------------------------------------------------------------------


class _Place:
    """Where a grid lands in a box: square cells of ``size`` points, centered."""

    def __init__(self, grid: np.ndarray, box: Box) -> None:
        x, y, w, h = box
        self.rows, self.cols = grid.shape[:2]
        self.size = min(w / self.cols, h / self.rows)
        self.left = x + (w - self.size * self.cols) / 2
        self.top = y + (h + self.size * self.rows) / 2

    def point(self, u: float, v: float) -> Point:
        return self.left + u * self.size, self.top - v * self.size

    @property
    def bounds(self) -> Box:
        return self.left, self.top - self.rows * self.size, self.cols * self.size, self.rows * self.size


def _path(c: Canvas, polygons: list[list[Point]], place: _Place):
    path = c.beginPath()
    for polygon in polygons:
        path.moveTo(*place.point(*polygon[0]))
        for corner in polygon[1:]:
            path.lineTo(*place.point(*corner))
        path.close()
    return path


def _fill(c: Canvas, settings: MosaicSettings, tone: int, path, bounds: Box, cell: float) -> None:
    """Fill ``path`` the way the legend says for ``tone``: a gray, or a pattern in black ink."""
    tones = settings.tones
    if settings.fill == "tones":
        gray = tone / (tones - 1)
        if gray < 1:
            c.setFillGray(gray)
            c.drawPath(path, stroke=0, fill=1)
        return
    pattern = PATTERNS[tones][tone]
    if pattern == "empty":
        return
    if pattern == "solid":
        c.setFillGray(0)
        c.drawPath(path, stroke=0, fill=1)
        return
    x, y, w, h = bounds
    gap = max(cell / 3.5, 1.5)
    c.saveState()
    c.clipPath(path, stroke=0, fill=0)
    c.setStrokeGray(0)
    lines = c.beginPath()
    if pattern == "dots":
        c.setLineCap(1)
        c.setLineWidth(max(cell * 0.14, 0.6))
        c.setDash([0, gap])
        for row, yy in enumerate(np.arange(y + gap / 2, y + h, gap)):
            lines.moveTo(x - gap + (gap / 2 if row % 2 else 0), yy)
            lines.lineTo(x + w + gap, yy)
    else:
        c.setLineWidth(max(cell * 0.07, 0.35))
        step = gap * math.sqrt(2)  # perpendicular distance ``gap`` between 45° lines
        for offset in np.arange(-h, w + step, step):
            lines.moveTo(x + offset, y)
            lines.lineTo(x + offset + h, y + h)
            if pattern == "cross":
                lines.moveTo(x + offset, y + h)
                lines.lineTo(x + offset + h, y)
    c.drawPath(lines, stroke=1, fill=0)
    c.restoreState()


def draw_solution(c: Canvas, grid: np.ndarray, settings: MosaicSettings, box: Box) -> None:
    """The mosaic filled in, fitted in ``box``, with a thin frame."""
    place = _Place(grid, box)
    by_tone: dict[int, list[list[Point]]] = defaultdict(list)
    for tone, polygon in shapes(grid):
        by_tone[tone].append(polygon)
    for tone, polygons in sorted(by_tone.items()):
        _fill(c, settings, tone, _path(c, polygons, place), place.bounds, place.size)
    c.setStrokeGray(0)
    c.setLineWidth(0.6)
    c.rect(*place.bounds)


def _shape(c: Canvas, name: str, cx: float, cy: float, r: float) -> None:
    """One of ``SHAPES``, outlined, centered on (cx, cy) with radius ``r``."""
    if name == "circle":
        c.circle(cx, cy, r * 0.85, stroke=1, fill=0)
        return
    path = c.beginPath()
    if name == "plus":
        path.moveTo(cx - r, cy)
        path.lineTo(cx + r, cy)
        path.moveTo(cx, cy - r)
        path.lineTo(cx, cy + r)
    else:
        corners = {
            "triangle": [(0, 1), (0.87, -0.5), (-0.87, -0.5)],
            "square": [(-0.75, 0.75), (0.75, 0.75), (0.75, -0.75), (-0.75, -0.75)],
            "diamond": [(0, 1), (1, 0), (0, -1), (-1, 0)],
        }[name]
        path.moveTo(cx + corners[0][0] * r, cy + corners[0][1] * r)
        for dx, dy in corners[1:]:
            path.lineTo(cx + dx * r, cy + dy * r)
        path.close()
    c.drawPath(path, stroke=1, fill=0)


def _symbol(c: Canvas, settings: MosaicSettings, tone: int, cx: float, cy: float, size: float, font: str) -> None:
    """The tone's symbol centered on (cx, cy), ``size`` points tall, in the current colors."""
    if settings.symbols == "shapes":
        c.setLineWidth(max(size * 0.08, 0.3))
        _shape(c, SHAPES[tone], cx, cy, size * 0.42)
    else:
        c.setFont(font, size)
        c.drawCentredString(cx, cy - size * 0.35, SYMBOLS[settings.symbols][tone])


def draw_puzzle(c: Canvas, grid: np.ndarray, settings: MosaicSettings, box: Box, font: str) -> None:
    """The faint grid with a faint symbol in every cell or triangle, fitted in ``box``."""
    place = _Place(grid, box)
    s, rows, cols = place.size, place.rows, place.cols
    c.saveState()
    c.setStrokeGray(FAINT_LINE)
    c.setLineWidth(max(0.25, min(0.6, s * 0.03)))
    lines = c.beginPath()
    for r in range(rows + 1):
        lines.moveTo(*place.point(0, r))
        lines.lineTo(*place.point(cols, r))
    for col in range(cols + 1):
        lines.moveTo(*place.point(col, 0))
        lines.lineTo(*place.point(col, rows))
    for r, col in zip(*np.nonzero(grid[..., 2] == SLASH)):
        lines.moveTo(*place.point(col, r + 1))
        lines.lineTo(*place.point(col + 1, r))
    for r, col in zip(*np.nonzero(grid[..., 2] == BACKSLASH)):
        lines.moveTo(*place.point(col, r))
        lines.lineTo(*place.point(col + 1, r + 1))
    c.drawPath(lines, stroke=1, fill=0)

    c.setFillGray(FAINT_SYMBOL)
    c.setStrokeGray(FAINT_SYMBOL)
    for tone, polygon in shapes(grid):
        u = sum(p[0] for p in polygon) / len(polygon)
        v = sum(p[1] for p in polygon) / len(polygon)
        size = s * (0.5 if len(polygon) == 4 else 0.3)
        _symbol(c, settings, tone, *place.point(u, v), size, font)
    c.restoreState()


def legend_labels(settings: MosaicSettings, languages: list[str]) -> list[list[str]]:
    """What each tone means, from black to white, one line per language."""
    if settings.fill == "tones":
        keys = [f"pdf.mosaic_tone.{name}" for name in TONE_NAMES[settings.tones]]
    else:
        keys = [f"pdf.mosaic_pattern.{name}" for name in PATTERNS[settings.tones]]
    return [i18n.t_all(key, languages) for key in keys]


def draw_legend(c: Canvas, settings: MosaicSettings, box: Box, fonts: Fonts, languages: list[str]) -> None:
    """One item per tone across ``box``: the symbol, an arrow, a swatch, and its name below."""
    x, y, w, h = box
    labels = legend_labels(settings, languages)
    item = w / settings.tones
    swatch = min(0.32 * 72, item * 0.3)
    label_size = 8.5
    top = y + h
    for tone in range(settings.tones):
        center = x + item * (tone + 0.5)
        cell_x, swatch_x = center - swatch * 1.25, center + swatch * 0.25
        bottom = top - swatch
        c.setStrokeColor(INK)
        c.setFillColor(INK)
        c.setLineWidth(0.6)
        c.rect(cell_x, bottom, swatch, swatch)
        _symbol(c, settings, tone, cell_x + swatch / 2, bottom + swatch / 2, swatch * 0.55, fonts.bold)
        c.setFont(fonts.regular, swatch * 0.5)
        c.drawCentredString(center, bottom + swatch * 0.32, "→")
        path = c.beginPath()
        path.rect(swatch_x, bottom, swatch, swatch)
        _fill(c, settings, tone, path, (swatch_x, bottom, swatch, swatch), swatch)
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.rect(swatch_x, bottom, swatch, swatch)
        c.setFillColor(MUTED)
        for line, text in enumerate(labels[tone]):
            c.setFont(fonts.bold if line == 0 else fonts.italic, label_size)
            c.drawCentredString(center, bottom - (line + 1) * (label_size + 2.5), text)


def legend_height(languages: list[str]) -> float:
    return 0.32 * 72 + len(languages) * 11 + 6


def render_solution(grid: np.ndarray, settings: MosaicSettings) -> Image.Image:
    """The solution as a 1-bit image: pencil tones dithered, pen patterns as drawn."""
    rows, cols = grid.shape[:2]
    cell = 24.0
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=(cols * cell, rows * cell))
    draw_solution(c, grid, settings, (0, 0, cols * cell, rows * cell))
    c.save()
    pdf = pdfium.PdfDocument(buffer.getvalue())
    try:
        image = pdf[0].render(scale=SOLUTION_PX / (max(rows, cols) * cell), grayscale=True).to_pil().convert("L")
    finally:
        pdf.close()
    dither = Image.Dither.FLOYDSTEINBERG if settings.fill == "tones" else Image.Dither.NONE
    image = image.convert("1", dither=dither)
    return ImageOps.expand(image, border=round(SOLUTION_PX * 0.03), fill=1)
