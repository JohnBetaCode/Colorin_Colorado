"""Tone curves for a page's photo, like GIMP's Curves tool, applied before any conversion.

A curve is a few control points (input, output), 0 to 255, joined by a monotone cubic
(Fritsch–Carlson), which bends smoothly through the points without overshooting them, so
lighter input never comes out darker. The end points are the black and white points: moving
the first one right turns more shadows black. The same curve applies to red, green and blue.

The curve is stored on the page (``Page.curve``), never baked into the photo: the original
stays, and resetting the curve brings it back.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

Point = tuple[int, int]

IDENTITY: list[Point] = [(0, 0), (255, 255)]
# Quick starting points for the editor.
PRESETS: dict[str, list[Point]] = {
    "contrast": [(0, 0), (64, 40), (192, 215), (255, 255)],
    "lighten": [(0, 0), (110, 150), (255, 255)],
    "darken": [(0, 0), (150, 110), (255, 255)],
}
HISTOGRAM_BINS = 64


def normalized(points: list[Point] | None) -> list[Point]:
    """Points clamped to 0–255, sorted by input, one per input, at least the two ends."""
    if not points:
        return list(IDENTITY)
    by_x: dict[int, int] = {}
    for x, y in points:
        by_x[max(0, min(255, round(x)))] = max(0, min(255, round(y)))
    result = sorted(by_x.items())
    return result if len(result) >= 2 else list(IDENTITY)


def is_identity(points: list[Point] | None) -> bool:
    return normalized(points) == IDENTITY


def lut(points: list[Point] | None) -> np.ndarray:
    """The curve as a 256-entry lookup table (uint8).

    Flat before the first point and after the last, like GIMP: inputs below the black point
    are black (or whatever the first point outputs).
    """
    pts = np.array(normalized(points), dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    if len(x) == 2:
        values = np.interp(np.arange(256), x, y)
        return np.clip(np.round(values), 0, 255).astype(np.uint8)
    # Fritsch–Carlson tangents: zero at a peak or valley between neighbors, so no overshoot.
    h = np.diff(x)
    delta = np.diff(y) / h
    slopes = np.zeros_like(x)
    slopes[0], slopes[-1] = delta[0], delta[-1]
    for i in range(1, len(x) - 1):
        if delta[i - 1] * delta[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            slopes[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    inputs = np.arange(256, dtype=float)
    values = np.interp(inputs, x, y)  # outside the points: flat
    for i in range(len(x) - 1):
        inside = (inputs >= x[i]) & (inputs <= x[i + 1])
        t = (inputs[inside] - x[i]) / h[i]
        t2, t3 = t * t, t * t * t
        values[inside] = (
            (2 * t3 - 3 * t2 + 1) * y[i]
            + (t3 - 2 * t2 + t) * h[i] * slopes[i]
            + (-2 * t3 + 3 * t2) * y[i + 1]
            + (t3 - t2) * h[i] * slopes[i + 1]
        )
    return np.clip(np.round(values), 0, 255).astype(np.uint8)


def apply(image: Image.Image, points: list[Point] | None) -> Image.Image:
    """``image`` (RGB) through the curve; unchanged when the curve is the identity."""
    if is_identity(points):
        return image
    table = lut(points).tolist()
    return image.convert("RGB").point(table * 3)


def histogram(image: Image.Image) -> list[float]:
    """The brightness histogram in ``HISTOGRAM_BINS`` bins, scaled so the tallest is 1.

    Square-rooted, so a few dominant tones (a white sky) do not flatten the rest.
    """
    gray = np.asarray(image.convert("L")).ravel().astype(np.int32)
    counts = np.bincount(gray * HISTOGRAM_BINS // 256, minlength=HISTOGRAM_BINS)
    heights = np.sqrt(counts.astype(float))
    return (heights / max(heights.max(), 1.0)).round(3).tolist()
