"""Mystery mosaics: the third engine, free and offline, for monochrome color-by-number pages.

The photo is turned to gray and divided into a grid of square cells, or of cells that may be
split along a diagonal into two triangles where that follows an edge better. Every cell (or
triangle) gets one of 2 to 5 tones, from black to white. The printed page shows the grid and a
number in every cell that is not white, both faint, and a legend that says how to fill each
number: a pencil tone, or a pattern from one of the ``PALETTES``. White cells have no number
unless the author asks (``number_white``), so the finished picture has no stray digits. Filled in,
the photo appears. Nothing is drawn by the AI.

The ``pen`` fill is a one-pen mosaic: every cell gets one of six marks (a filled square, a star,
a cross, a "\\", a "/" or nothing), chosen by error diffusion on the ink each mark leaves, which
is measured by drawing it; the single strokes follow the photo's edges. Its guide is a grid of
faint dots instead of lines. With ``remove_background``, ``background.subject_mask`` cuts the
subject out first and the rest is white paper.

A mosaic is stored as data, not as a picture: ``v<n>-raw.png`` is the grid, one pixel per cell
(red: the tone of the cell or of its first triangle, green: the tone of the second triangle,
blue: the split). The PDF draws it as vectors, so the faint lines and numbers print sharp at any
size. ``v<n>.png`` is the solution in 1 bit, for the workbench, the thumbnails and the cover; it
does not go through ``lineart.clean``, which would hollow out the black cells.
"""

from __future__ import annotations

import math
from collections import defaultdict
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageOps
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
# Numbers inside triangles are smaller, so diagonal cells need a coarser grid to stay legible.
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
SUBJECT_MARGIN = 0.04  # around the subject when the background is removed, share of its long side
EQUALIZE = 0.6  # share of histogram equalization in the tone mapping (see _adjust)
# A cell is split only when its two triangles bring the error down to this share of the
# whole cell's: flat areas stay whole squares, edges get a diagonal.
SPLIT_GAIN = 0.6
WHOLE, SLASH, BACKSLASH = 0, 1, 2  # blue channel of the grid: no split, "/" or "\"

# What each tone is called with pencil tones, from black to white.
TONE_NAMES = {
    2: ("black", "white"),
    3: ("black", "mid", "white"),
    4: ("black", "dark", "light", "white"),
    5: ("black", "dark", "mid", "light", "white"),
}
# Pen palettes: four patterns from darkest to lightest; white ("empty") is always the last tone.
PALETTES = {
    "classic": ("solid", "cross", "diag", "dots"),
    "lines": ("solid", "grid", "diag", "hlines"),
    "stipple": ("solid", "dots_dense", "dots", "dots_sparse"),
    "geometric": ("solid", "checker", "zigzag", "dashes"),
}
# Which of a palette's four patterns are used with fewer tones: always the darkest, spread out.
_PICK = {1: (0,), 2: (0, 2), 3: (0, 1, 3), 4: (0, 1, 2, 3)}

# The puzzle is printed faint, so the filled-in tones cover it.
FAINT_LINE = 0.72
FAINT_NUMBER = 0.6
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")
SOLUTION_PX = 2400  # long side of the stored solution, like a cleaned coloring page

# One pen: the marks from darkest to lightest (tone 0 to 5). The two single strokes leave the
# same ink; the photo's edge direction picks between them, so lines follow contours.
PEN_MARKS = ("square", "star", "cross", "backslash", "slash", "empty")
PEN_TONES = len(PEN_MARKS)
PEN_MAX_COLUMNS = 80
PEN_WIDTH = 0.1  # pen line as a share of the cell: a 0.4 mm fineliner in a 4 mm cell
PEN_GAMMA = 1.8  # above 1 keeps the mid-tones light: heavy marks only in the shadows
PEN_DIFFUSION = 0.75  # share of each cell's error passed on: smooth gradients without speckle
PEN_EDGE = 0.25  # edge coherence above which a single stroke follows the edge
_MARK_INSET = 0.2  # strokes stop this far from the cell's sides
_SQUARE_INSET = 0.11


# --- Settings ---------------------------------------------------------------------


def patterns(settings: MosaicSettings) -> tuple[str, ...]:
    """The pen pattern of each tone, from black to white (the last is always "empty")."""
    palette = PALETTES[settings.fill]
    return tuple(palette[i] for i in _PICK[settings.tones - 1]) + ("empty",)


def default_settings(age_group: str) -> MosaicSettings:
    return MosaicSettings(**AGE_DEFAULTS[age_group])


def settings_for(book: Book, page: Page) -> MosaicSettings:
    """The page's own settings, else the book's, else the age group's."""
    return normalized(page.mosaic or book.mosaic or default_settings(book.age_group))


def normalized(settings: MosaicSettings) -> MosaicSettings:
    """``settings`` with every number inside its range. A one-pen mosaic always has square
    cells and its six marks."""

    def clamp(value: int, low: int, high: int) -> int:
        return max(low, min(high, int(value)))

    update = {
        "tones": clamp(settings.tones, MIN_TONES, MAX_TONES),
        "columns": clamp(settings.columns, MIN_COLUMNS, MAX_COLUMNS[settings.cells]),
        "contrast": clamp(settings.contrast, -LIMIT, LIMIT),
        "brightness": clamp(settings.brightness, -LIMIT, LIMIT),
    }
    if settings.fill == "pen":
        update |= {"tones": PEN_TONES, "cells": "square", "columns": clamp(settings.columns, MIN_COLUMNS, PEN_MAX_COLUMNS)}
    return settings.model_copy(update=update)


# --- Grid -------------------------------------------------------------------------


def _adjust(
    gray: np.ndarray, settings: MosaicSettings, sample: np.ndarray | None = None, equalize: float = EQUALIZE
) -> np.ndarray:
    """Spread the photo's tones over the full range, then apply contrast and brightness.

    A plain stretch leaves most photos in the middle tones (a bird in grass is all mid
    gray), so it is blended with histogram equalization, which gives every tone a fair
    share of the cells. The range is measured on ``sample`` (the subject's pixels, when the
    background is removed), else on the whole photo. One-pen mosaics use no equalization
    (``equalize=0``): their marks reproduce tones, and white paper must stay white.
    """
    sample = gray if sample is None or sample.size == 0 else sample
    low, high = np.percentile(sample, (1, 99))
    stretched = np.clip((gray - low) / max(float(high - low), 1e-3), 0, 1)
    ranked = np.sort(sample, axis=None)
    # Middle rank: equal values share the middle of their run (a flat subject stays mid, not light).
    equalized = (np.searchsorted(ranked, gray, side="left") + np.searchsorted(ranked, gray, side="right")) / (2 * ranked.size)
    value = equalize * equalized + (1 - equalize) * stretched
    value = (value - 0.5) * (1 + settings.contrast / 100) + 0.5 + settings.brightness / 100
    return np.clip(value, 0, 1)


def _quantize(value: np.ndarray, tones: int) -> np.ndarray:
    return np.clip((value * tones).astype(int), 0, tones - 1)


def _error(total: np.ndarray, squares: np.ndarray, weight: float, tone: np.ndarray, tones: int) -> np.ndarray:
    """Sum of squared differences between the pixels and the tone's middle value."""
    center = (tone + 0.5) / tones
    return squares - 2 * center * total + center * center * weight


def make_grid(photo: Image.Image, settings: MosaicSettings, subject: np.ndarray | None = None) -> np.ndarray:
    """The mosaic of a (cropped) photo: ``(rows, columns, 3)`` uint8, see the module docstring.

    With a ``subject`` mask (bool, photo size), the grid frames the subject (plus a small
    margin), so every cell goes to it, the tones are spread over the subject alone, and
    everything outside it is white paper.
    """
    settings = normalized(settings)
    if subject is not None and subject.any():
        ys, xs = np.nonzero(subject)
        pad = round(SUBJECT_MARGIN * max(np.ptp(xs), np.ptp(ys)))
        x0, x1 = max(int(xs.min()) - pad, 0), min(int(xs.max()) + pad + 1, subject.shape[1])
        y0, y1 = max(int(ys.min()) - pad, 0), min(int(ys.max()) + pad + 1, subject.shape[0])
        photo, subject = photo.crop((x0, y0, x1, y1)), subject[y0:y1, x0:x1]
    gray = np.asarray(photo.convert("L"), dtype=np.float32) / 255
    h, w = gray.shape
    cols = settings.columns
    rows = max(1, round(cols * h / w))
    k, tones = SAMPLES, settings.tones
    small = cv2.resize(gray, (cols * k, rows * k), interpolation=cv2.INTER_AREA)
    equalize = 0.0 if settings.fill == "pen" else EQUALIZE
    if subject is None:
        value = _adjust(small, settings, equalize=equalize)
    else:
        # Share of subject under each sample: edges blend into the white background.
        inside = cv2.resize(subject.astype(np.float32), (cols * k, rows * k), interpolation=cv2.INTER_AREA)
        value = _adjust(small, settings, small[inside > 0.5], equalize=equalize) * inside + (1 - inside)
    if settings.fill == "pen":
        return _pen_grid(value.astype(np.float32), rows, cols, k)
    cells = value.reshape(rows, k, cols, k).transpose(0, 2, 1, 3)

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


def _mark_segments(mark: str) -> list[tuple[Point, Point]]:
    """The strokes of a pen ``mark``, in cell units (0 to 1, y down)."""
    a, b, m = _MARK_INSET, 1 - _MARK_INSET, 0.5
    slash, backslash = ((a, b), (b, a)), ((a, a), (b, b))
    return {
        "slash": [slash],
        "backslash": [backslash],
        "cross": [slash, backslash],
        "star": [slash, backslash, ((m, a), (m, b)), ((a, m), (b, m))],
    }.get(mark, [])


@lru_cache(maxsize=1)
def pen_ink() -> tuple[float, ...]:
    """Share of a cell each pen mark inks, darkest first, measured by drawing it."""
    size = 64
    result = []
    for mark in PEN_MARKS:
        image = Image.new("L", (size, size), 255)
        draw = ImageDraw.Draw(image)
        for (u1, v1), (u2, v2) in _mark_segments(mark):
            draw.line([(u1 * size, v1 * size), (u2 * size, v2 * size)], fill=0, width=max(1, round(PEN_WIDTH * size)))
        if mark == "square":
            low, high = _SQUARE_INSET * size, (1 - _SQUARE_INSET) * size
            draw.rectangle([low, low, high, high], fill=0)
        result.append(float((np.asarray(image) < 128).mean()))
    return tuple(result)


def _pen_grid(value: np.ndarray, rows: int, cols: int, k: int) -> np.ndarray:
    """One mark per cell: error diffusion on the marks' ink, then each single stroke turned
    along the edge it sits on."""
    ink = np.array(pen_ink())
    levels = ink[[0, 1, 2, 3, 5]]  # one level per darkness: both single strokes share one
    level_tone = np.array([0, 1, 2, 3, 5])
    cells = value.reshape(rows, k, cols, k).mean(axis=(1, 3))
    target = (1 - cells.astype(np.float64)) ** PEN_GAMMA * ink[0]
    choice = np.empty((rows, cols), int)
    # Floyd–Steinberg, serpentine: gradients become mixes of neighbouring marks, not bands.
    for r in range(rows):
        step = 1 if r % 2 == 0 else -1
        for c in range(cols) if step == 1 else range(cols - 1, -1, -1):
            i = int(np.abs(levels - target[r, c]).argmin())
            choice[r, c] = i
            error = (target[r, c] - levels[i]) * PEN_DIFFUSION
            if 0 <= c + step < cols:
                target[r, c + step] += error * 7 / 16
            if r + 1 < rows:
                if 0 <= c - step < cols:
                    target[r + 1, c - step] += error * 3 / 16
                target[r + 1, c] += error * 5 / 16
                if 0 <= c + step < cols:
                    target[r + 1, c + step] += error / 16
    tone = level_tone[choice]

    # Each cell's edge direction from the structure tensor; "/" runs at -45° (y down), "\"
    # at +45°. Where there is no clear edge, they alternate in a checkerboard.
    gx = cv2.Sobel(value, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(value, cv2.CV_32F, 0, 1, ksize=3)

    def per_cell(a: np.ndarray) -> np.ndarray:
        return a.reshape(rows, k, cols, k).sum(axis=(1, 3))

    jxx, jyy, jxy = per_cell(gx * gx), per_cell(gy * gy), per_cell(gx * gy)
    edge = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2
    coherence = np.sqrt((jxx - jyy) ** 2 + 4 * jxy**2) / (jxx + jyy + 1e-6)
    along_slash = np.abs(np.cos(edge + np.pi / 4)) > np.abs(np.cos(edge - np.pi / 4))
    checker = np.indices((rows, cols)).sum(axis=0) % 2 == 0
    slash = np.where(coherence > PEN_EDGE, along_slash, checker)
    tone = np.where((tone == 3) & slash, 4, tone)

    grid = np.zeros((rows, cols, 3), np.uint8)
    grid[..., 0] = grid[..., 1] = tone
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


def _draw_pattern(c: Canvas, name: str, bounds: Box, cell: float) -> None:
    """Stroke pattern ``name`` in black over ``bounds``; the caller clips it to the shapes.

    Rows are separate subpaths, and a dash pattern restarts at each one, so shifting a row's
    start staggers its dots, dashes or checker squares.
    """
    x, y, w, h = bounds
    gap = max(cell / 3.5, 1.5)  # about three and a half pattern steps per cell
    lines = c.beginPath()

    def diagonals(rising: bool) -> None:
        step = gap * math.sqrt(2)  # perpendicular distance ``gap`` between 45° lines
        for offset in np.arange(-h, w + step, step):
            lines.moveTo(x + offset, y if rising else y + h)
            lines.lineTo(x + offset + h, y + h if rising else y)

    def rows(step: float, shift: float = 0.0) -> None:
        for row, yy in enumerate(np.arange(y + step / 2, y + h + step, step)):
            lines.moveTo(x - 2 * step + (shift if row % 2 else 0), yy)
            lines.lineTo(x + w + 2 * step, yy)

    c.setStrokeGray(0)
    c.setLineWidth(max(cell * 0.07, 0.35))
    if name == "cross":
        diagonals(True)
        diagonals(False)
    elif name == "diag":
        diagonals(True)
    elif name == "grid":
        rows(gap)
        for xx in np.arange(x + gap / 2, x + w, gap):
            lines.moveTo(xx, y - gap)
            lines.lineTo(xx, y + h + gap)
    elif name == "hlines":
        rows(gap * 1.5)
    elif name in ("dots_dense", "dots", "dots_sparse"):
        step, size = {"dots_dense": (0.75, 0.17), "dots": (1.0, 0.14), "dots_sparse": (1.6, 0.13)}[name]
        step *= gap
        c.setLineCap(1)
        c.setLineWidth(max(cell * size, 0.6))
        c.setDash([0, step])
        rows(step, shift=step / 2)
    elif name == "checker":
        c.setLineWidth(gap)
        c.setDash([gap, gap])
        rows(gap, shift=gap)
    elif name == "zigzag":
        for yy in np.arange(y, y + h + gap, gap * 1.3):
            lines.moveTo(x - gap, yy)
            for k, xx in enumerate(np.arange(x - gap, x + w + gap, gap / 2)):
                lines.lineTo(xx, yy + (gap * 0.45 if k % 2 else 0))
    elif name == "dashes":
        c.setDash([gap * 0.6, gap * 0.6])
        rows(gap * 1.2, shift=gap * 0.6)
    c.drawPath(lines, stroke=1, fill=0)


def _draw_marks(c: Canvas, marks: list[tuple[str, Box]], width: float) -> None:
    """Draw pen ``marks`` (mark, cell box in points) with a pen line of ``width``."""
    lines, squares = c.beginPath(), c.beginPath()
    for mark, (x, y, w, h) in marks:
        for (u1, v1), (u2, v2) in _mark_segments(mark):
            lines.moveTo(x + u1 * w, y + h - v1 * h)
            lines.lineTo(x + u2 * w, y + h - v2 * h)
        if mark == "square":
            i = _SQUARE_INSET
            squares.rect(x + i * w, y + i * h, (1 - 2 * i) * w, (1 - 2 * i) * h)
    c.saveState()
    c.setStrokeGray(0)
    c.setFillGray(0)
    c.setLineWidth(width)
    c.setLineCap(1)
    c.drawPath(lines, stroke=1, fill=0)
    c.drawPath(squares, stroke=0, fill=1)
    c.restoreState()


def _fill(c: Canvas, settings: MosaicSettings, tone: int, path, bounds: Box, cell: float) -> None:
    """Fill ``path`` the way the legend says for ``tone``: a gray, a pattern in black ink, or
    (one pen) the tone's mark drawn in ``bounds``."""
    if settings.fill == "pen":
        _draw_marks(c, [(PEN_MARKS[tone], bounds)], bounds[2] * PEN_WIDTH)
        return
    if settings.fill == "tones":
        gray = tone / (settings.tones - 1)
        if gray < 1:
            c.setFillGray(gray)
            c.drawPath(path, stroke=0, fill=1)
        return
    name = patterns(settings)[tone]
    if name == "empty":
        return
    if name == "solid":
        c.setFillGray(0)
        c.drawPath(path, stroke=0, fill=1)
        return
    c.saveState()
    c.clipPath(path, stroke=0, fill=0)
    _draw_pattern(c, name, bounds, cell)
    c.restoreState()


def draw_solution(c: Canvas, grid: np.ndarray, settings: MosaicSettings, box: Box) -> None:
    """The mosaic filled in, fitted in ``box``, with a thin frame."""
    place = _Place(grid, box)
    if settings.fill == "pen":
        s = place.size
        marks = [
            (PEN_MARKS[int(grid[r, col, 0])], (*place.point(col, r + 1), s, s))
            for r in range(place.rows)
            for col in range(place.cols)
        ]
        _draw_marks(c, marks, s * PEN_WIDTH)
    by_tone: dict[int, list[list[Point]]] = defaultdict(list)
    for tone, polygon in shapes(grid) if settings.fill != "pen" else []:
        by_tone[tone].append(polygon)
    for tone, polygons in sorted(by_tone.items()):
        _fill(c, settings, tone, _path(c, polygons, place), place.bounds, place.size)
    c.setStrokeGray(0)
    c.setLineWidth(0.6)
    c.rect(*place.bounds)


def numbered(grid: np.ndarray, settings: MosaicSettings) -> list[tuple[str, list[Point]]]:
    """The number printed in each cell or triangle: its tone counted from 1 (black). White
    ones have none unless ``number_white``, so the finished picture has no stray digits."""
    white = None if settings.number_white else settings.tones - 1
    return [(str(tone + 1), polygon) for tone, polygon in shapes(grid) if tone != white]


def draw_puzzle(c: Canvas, grid: np.ndarray, settings: MosaicSettings, box: Box, font: str) -> None:
    """The faint grid with a faint number in every cell or triangle that is not white. A
    one-pen mosaic gets faint dots at the cells' corners instead of lines, so the marks stay
    clean."""
    place = _Place(grid, box)
    s, rows, cols = place.size, place.rows, place.cols
    c.saveState()
    if settings.fill == "pen":
        c.setFillGray(FAINT_LINE)
        dots = c.beginPath()
        radius = max(0.35, s * 0.045)
        for r in range(rows + 1):
            for col in range(cols + 1):
                dots.circle(*place.point(col, r), radius)
        c.drawPath(dots, stroke=0, fill=1)
        _draw_numbers(c, grid, settings, place, font)
        c.restoreState()
        return
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
    _draw_numbers(c, grid, settings, place, font)
    c.restoreState()


def _draw_numbers(c: Canvas, grid: np.ndarray, settings: MosaicSettings, place: _Place, font: str) -> None:
    s = place.size
    c.setFillGray(FAINT_NUMBER)
    for number, polygon in numbered(grid, settings):
        u = sum(p[0] for p in polygon) / len(polygon)
        v = sum(p[1] for p in polygon) / len(polygon)
        size = s * (0.5 if len(polygon) == 4 else 0.3)
        cx, cy = place.point(u, v)
        c.setFont(font, size)
        c.drawCentredString(cx, cy - size * 0.35, number)


def legend_labels(settings: MosaicSettings, languages: list[str]) -> list[list[str]]:
    """What each tone means, from black to white, one line per language."""
    if settings.fill == "pen":
        keys = [f"pdf.mosaic_mark.{mark}" for mark in PEN_MARKS]
    elif settings.fill == "tones":
        keys = [f"pdf.mosaic_tone.{name}" for name in TONE_NAMES[settings.tones]]
    else:
        keys = [f"pdf.mosaic_pattern.{name}" for name in patterns(settings)]
    return [i18n.t_all(key, languages) for key in keys]


def draw_legend(c: Canvas, settings: MosaicSettings, box: Box, fonts: Fonts, languages: list[str]) -> None:
    """One item per tone across ``box``: its number (white has none unless numbered), an
    arrow, a swatch, and its name below."""
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
        if tone < settings.tones - 1 or settings.number_white:
            size = swatch * 0.55
            c.setFont(fonts.bold, size)
            c.drawCentredString(cell_x + swatch / 2, bottom + swatch / 2 - size * 0.35, str(tone + 1))
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
