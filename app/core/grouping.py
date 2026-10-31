"""Color grouping for a page's photo: mean shift merges neighboring pixels of similar color into
flat areas, so the engines after it (the mosaic, the free draft, the AI) see shapes rather than
texture. It runs after the tone curve, and only when the author turns it on.

The one setting is the bandwidth: the color radius of the mean shift (OpenCV's
``pyrMeanShiftFiltering``), in RGB levels. A bigger bandwidth merges more different colors. The
spatial radius is fixed. Mean shift takes seconds on a big photo, so it works at
``GROUP_SIZE`` pixels on the long side and the results are cached by what they were made from.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np
from PIL import Image

MIN_BANDWIDTH, MAX_BANDWIDTH = 5, 60
DEFAULT_BANDWIDTH = 25
GROUP_SIZE = 1200  # long side the grouped photo is worked and returned at
SPATIAL_RADIUS = 12  # pixels at GROUP_SIZE
CACHE_SIZE = 16

_cache: dict[tuple, Image.Image] = {}
_lock = threading.Lock()


def group(image: Image.Image, bandwidth: int, key: tuple | None = None) -> Image.Image:
    """``image`` with similar colors grouped into flat areas, at most ``GROUP_SIZE`` on the long
    side. With ``key`` (whatever ``image`` was made from), the result is cached under it."""
    bandwidth = max(MIN_BANDWIDTH, min(MAX_BANDWIDTH, int(bandwidth)))
    full_key = None if key is None else (*key, bandwidth)
    with _lock:
        if full_key in _cache:
            return _cache[full_key].copy()
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    scale = GROUP_SIZE / max(h, w)
    if scale < 1:
        rgb = cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    grouped = Image.fromarray(cv2.pyrMeanShiftFiltering(np.ascontiguousarray(rgb), SPATIAL_RADIUS, bandwidth, maxLevel=1))
    if full_key is not None:
        with _lock:
            if len(_cache) >= CACHE_SIZE:
                _cache.pop(next(iter(_cache)))  # the oldest
            _cache[full_key] = grouped
        return grouped.copy()
    return grouped
