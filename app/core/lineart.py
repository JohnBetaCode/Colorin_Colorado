"""Black-and-white guarantee for coloring pages.

The image model is asked for pure line art but is never trusted to deliver it.
``clean`` turns any image into a 1-bit page: every pixel pure black or pure white,
colored areas dropped, large black fills hollowed out to their outline, specks
removed, lines at least as thick as the age group needs, cropped to the drawing
with a white margin. When the model returns a photo of a printed page instead of
the artwork, the page is cut out of the photo first. ``draft`` is the free, offline engine: it
flattens the photo into a few color areas (mean shift and k-means) whose borders become the lines,
cleaned the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

AGE_GROUPS = ("3-5", "6-8", "9+")

# Work resolution: the long side of every cleaned page. A coloring page prints about
# 7.5 in on its long side, so 2400 px is ~320 DPI and 13 px is ~1 mm.
WORK_SIZE = 2400
MIN_STROKE_PX = {"3-5": 16, "6-8": 10, "9+": 6}

# Ink is anything darker than this (or Otsu's threshold, if lower), so light gray
# shading drops out instead of turning into black blobs. Saturated pixels are color
# the model copied from the photo, not line work, unless they are nearly black.
MAX_THRESHOLD = 150
COLOR_SATURATION = 90
NEAR_BLACK = 60

# A black area that still contains a disk FILL_DIAMETER strokes wide, and covers at
# least FILL_MIN_AREA of the page, is a fill, not a line: keep only its outline.
# Smaller fills (pupils, nostrils) stay black.
FILL_DIAMETER = 3
FILL_MIN_AREA = 0.002

# Thin lines are grown one pixel per side at a time toward MIN_STROKE_PX, stopping
# before neighboring lines merge (areas to color disappear) or the page gets dark.
# Only areas big enough to color at that age count: young kids lose nothing when
# tiny areas close up.
THICKEN_MAX_BLACK = 0.22
THICKEN_MAX_LOST = 2
THICKEN_LOST_SHARE = 0.15
THICKEN_REGION_AREA = {"3-5": 0.004, "6-8": 0.002, "9+": 0.0005}

# A raw image whose outer strip is mostly not white paper is a photo of a printed
# page (a "mockup"): keep only the sheet of paper.
PAPER_BORDER = 0.02
PAPER_MIN_WHITE = 0.5

# Frames and paper edges: ink that lives entirely in the outer FRAME_RING of the image
# and runs along at least FRAME_MIN_SPAN of a side. Drawing that reaches into the page
# (grass, ground) is kept.
FRAME_RING = 0.05
FRAME_MIN_SPAN = 0.3

# Quality warnings. They suggest regenerating; they never block.
TOO_DARK_RATIO = 0.30  # share of black inside the drawing's bounding box
MIN_REGIONS = 5  # white areas big enough to color
SHADING_RATIO = 0.02  # share of flat dark-gray area (it would print black) in the raw image
COLOR_RATIO = 0.01  # share of saturated pixels in the raw image
FILLED_RATIO = 0.005  # share of the page hollowed out
WARNINGS = ("was_mockup", "had_color", "had_shading", "filled_areas", "too_dark", "too_few_regions")

MARGIN_RATIO = 0.03


@dataclass
class CleanResult:
    image: Image.Image  # mode "1"
    warnings: list[str] = field(default_factory=list)
    stroke_px: float = 0.0
    black_ratio: float = 0.0
    regions: int = 0


def load_image(data: bytes | Image.Image) -> Image.Image:
    """Open bytes or an image as RGB, applying EXIF rotation and flattening alpha on white."""
    img = Image.open(BytesIO(data)) if isinstance(data, bytes) else data
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return img.convert("RGB")


def _resize_long_side(gray: np.ndarray, size: int) -> np.ndarray:
    h, w = gray.shape
    scale = size / max(h, w)
    if abs(scale - 1) < 0.01:
        return gray
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=interpolation)


def _remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    """Drop 8-connected components of ``mask`` smaller than ``min_area`` pixels."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return keep[labels]


def _stroke_width(ink: np.ndarray) -> float:
    """Average line width: for a line of width w and length L, area = wL and edge = 2L."""
    area = int(ink.sum())
    if not area:
        return 0.0
    eroded = cv2.erode(ink.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    edge = int((ink & ~eroded).sum())
    return 2 * area / max(edge, 1)


def _disk(diameter: int) -> np.ndarray:
    diameter = max(3, diameter | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (diameter, diameter))


def _hollow_fills(ink: np.ndarray, stroke: int) -> tuple[np.ndarray, float]:
    """Replace big solid black areas by their outline, ``stroke`` pixels thick."""
    fills = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, _disk(FILL_DIAMETER * stroke)).astype(bool)
    fills = _remove_small(fills, int(fills.size * FILL_MIN_AREA))
    if not fills.any():
        return ink, 0.0
    interior = cv2.erode(fills.astype(np.uint8), _disk(2 * stroke + 1)).astype(bool)
    return ink & ~interior, float(fills.mean())


def _count_regions(ink: np.ndarray, min_area: int) -> int:
    n, _, stats, _ = cv2.connectedComponentsWithStats((~ink).astype(np.uint8), connectivity=4)
    return int((stats[1:, cv2.CC_STAT_AREA] >= min_area).sum())


def _crop_to_paper(rgb: np.ndarray) -> tuple[np.ndarray, bool]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    paper = (hsv[:, :, 2] > 190) & (hsv[:, :, 1] < 40)
    h, w = paper.shape
    b = max(4, round(min(h, w) * PAPER_BORDER))
    border = np.concatenate([paper[:b].ravel(), paper[-b:].ravel(), paper[:, :b].ravel(), paper[:, -b:].ravel()])
    if border.mean() >= PAPER_MIN_WHITE:
        return rgb, False
    closed = cv2.morphologyEx(paper.astype(np.uint8), cv2.MORPH_CLOSE, _disk(round(min(h, w) * 0.03)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=4)
    if n < 2:
        return rgb, False
    x, y, bw, bh = stats[1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])), :4]
    if bw * bh < 0.3 * h * w:
        return rgb, False
    inset = round(min(bw, bh) * 0.015)
    return rgb[y + inset : y + bh - inset, x + inset : x + bw - inset], True


def _remove_frames(ink: np.ndarray) -> np.ndarray:
    h, w = ink.shape
    b = round(min(h, w) * FRAME_RING)
    ring = np.ones_like(ink)
    ring[b:-b, b:-b] = False
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    in_ring = np.bincount(labels[ring & ink], minlength=n)
    long = (stats[:, cv2.CC_STAT_WIDTH] >= w * FRAME_MIN_SPAN) | (stats[:, cv2.CC_STAT_HEIGHT] >= h * FRAME_MIN_SPAN)
    frame = long & (in_ring == stats[:, cv2.CC_STAT_AREA])
    frame[0] = False
    return ink & ~frame[labels]


def _thicken(ink: np.ndarray, target: int, min_area: int) -> tuple[np.ndarray, float]:
    stroke = _stroke_width(ink)
    regions = _count_regions(ink, min_area)
    while 0 < stroke < target:
        grown = cv2.dilate(ink.astype(np.uint8), _disk(3)).astype(bool)
        lost = regions - _count_regions(grown, min_area)
        if grown.mean() > THICKEN_MAX_BLACK or lost > max(THICKEN_MAX_LOST, regions * THICKEN_LOST_SHARE):
            break
        ink, stroke = grown, _stroke_width(grown)
    return ink, stroke


def _flat_dark_share(gray: np.ndarray, colored: np.ndarray) -> float:
    """Share of smooth dark-gray area: shading that thresholding would turn into black."""
    values = gray.astype(np.float32)
    mean = cv2.blur(values, (15, 15))
    std = np.sqrt(np.maximum(cv2.blur(values * values, (15, 15)) - mean * mean, 0))
    flat = cv2.medianBlur(gray, 7)
    return float(((flat > NEAR_BLACK) & (flat < MAX_THRESHOLD) & (std < 12) & ~colored).mean())


def clean(data: bytes | Image.Image, age_group: str) -> CleanResult:
    """Turn any image into a 1-bit coloring page and report quality warnings."""
    rgb, mockup = _crop_to_paper(np.array(load_image(data)))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    saturation = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 1]

    colored = (saturation > COLOR_SATURATION) & (gray > NEAR_BLACK)
    color = float(colored.mean())
    shading = _flat_dark_share(gray, colored)

    gray = _resize_long_side(gray, WORK_SIZE)
    colored = _resize_long_side(colored.astype(np.uint8) * 255, WORK_SIZE) > 127
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (gray < min(otsu, MAX_THRESHOLD)) & ~colored

    h, w = ink.shape
    speck = max(12, int(h * w * 2e-5))
    ink = _remove_small(ink, speck)
    # Tiny white holes inside lines become ink; they are too small to color anyway.
    ink |= ~ink & ~_remove_small(~ink, speck // 2)

    ink = _remove_frames(ink)

    target = MIN_STROKE_PX.get(age_group, MIN_STROKE_PX["6-8"])
    ink, filled = _hollow_fills(ink, target)

    ink, stroke = _thicken(ink, target, int(ink.size * THICKEN_REGION_AREA.get(age_group, 0.001)))

    ys, xs = np.nonzero(ink)
    if len(xs):
        top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        ink = ink[top:bottom, left:right]
    pad = round(max(ink.shape) * MARGIN_RATIO)
    ink = np.pad(ink, pad, constant_values=False)

    black_ratio = float(ink.mean())
    regions = _count_regions(ink, int(ink.size * 5e-4))
    flags = {
        "was_mockup": mockup,
        "had_color": color > COLOR_RATIO,
        "had_shading": shading > SHADING_RATIO,
        "filled_areas": filled > FILLED_RATIO,
        "too_dark": black_ratio > TOO_DARK_RATIO,
        "too_few_regions": regions < MIN_REGIONS,
    }
    warnings = [key for key in WARNINGS if flags[key]]

    image = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)
    return CleanResult(image, warnings, round(stroke, 1), round(black_ratio, 3), regions)


# Draft engine: the photo is flattened into a few color areas (mean shift + k-means)
# and the borders between areas become the lines, so every area is closed and can be
# colored. Fewer colors and smoother borders for younger kids and for cartoon style.
DRAFT_SIZE = 700
_DRAFT_COLORS = {"3-5": 6, "6-8": 10, "9+": 14}
_DRAFT_SMOOTH = {"3-5": 11, "6-8": 9, "9+": 7}


def draft(photo: bytes | Image.Image, style: str, age_group: str) -> Image.Image:
    """Offline line drawing of the photo (grayscale; pass it through ``clean``)."""
    rgb = np.array(load_image(photo))
    h, w = rgb.shape[:2]
    scale = DRAFT_SIZE / max(h, w)
    small = cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    small = cv2.pyrMeanShiftFiltering(small, 15, 35)
    colors = _DRAFT_COLORS.get(age_group, 10) - (2 if style == "cartoon" else 0)
    pixels = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    cv2.setRNGSeed(0)  # same photo, same draft
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, _ = cv2.kmeans(pixels, colors, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    areas = labels.reshape(small.shape[:2]).astype(np.uint8)
    for _ in range(2):
        areas = cv2.medianBlur(areas, _DRAFT_SMOOTH.get(age_group, 9))
    edges = np.zeros(areas.shape, bool)
    edges[:, 1:] |= areas[:, 1:] != areas[:, :-1]
    edges[1:, :] |= areas[1:, :] != areas[:-1, :]
    return Image.fromarray(np.where(edges, 0, 255).astype(np.uint8))


def to_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
