"""Background removal for mystery mosaics, with SAM2 (Segment Anything 2), offline.

The author clicks points on the photo: on the subject (left click) or on the background
(right click); with none, the middle of the cropped photo is the subject. SAM2 returns the
subject's mask and everything else becomes white paper, so a mosaic is only the bird, not
the grass behind it. The model is SAM 2.1 base-plus, the middle size, through
``transformers``: its weights are public on Hugging Face and download by themselves the
first time (about 320 MB, under ``models/``, which Compose mounts). Masks are cached in
``books/<slug>/masks/``, keyed by the crop, the points and the model, because SAM2 takes a
few seconds on a CPU.

``torch`` and ``transformers`` are imported only when a mask is needed, so everything
else works without them; ``available`` says whether they are installed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.core import pages
from app.core.books import book_path
from app.core.schema import MosaicSettings, Page, SubjectPoint

MODEL_ID = "facebook/sam2.1-hiera-base-plus"
MODEL_MB = 320  # download size, shown before the first use
MIN_PART = 0.01  # pieces of the mask smaller than this share of it are dropped (specks)
POINT_REACH = 3.0  # percent of the photo: a click this close to a point removes it

_lock = threading.Lock()


class BackgroundError(Exception):
    pass


def available() -> bool:
    """Whether torch and transformers are installed (they are in the Docker image)."""
    return all(importlib.util.find_spec(name) for name in ("torch", "transformers"))


def model_downloaded() -> bool:
    """Whether the weights are already on disk, so the first use will not download them."""
    if not available():
        return False
    from huggingface_hub import try_to_load_from_cache

    return isinstance(try_to_load_from_cache(MODEL_ID, "config.json"), str)


@lru_cache(maxsize=1)
def _model():
    """The processor and model, loaded once per process (downloaded the first time)."""
    from transformers import Sam2Model, Sam2Processor
    from transformers.utils import logging

    logging.set_verbosity_error()  # the checkpoint is a video one; the image model loads its subset
    return Sam2Processor.from_pretrained(MODEL_ID), Sam2Model.from_pretrained(MODEL_ID).eval()


def _predict(image: Image.Image, points: list[tuple[float, float]], labels: list[int]) -> np.ndarray:
    """SAM2's best mask (bool, image size) for one object: ``points`` in pixels, labeled 1
    (part of it) or 0 (not part of it)."""
    import torch

    with _lock:  # one model, shared by the app's threads
        processor, model = _model()
        inputs = processor(
            images=image, input_points=[[[list(p) for p in points]]], input_labels=[[labels]], return_tensors="pt"
        )
        with torch.inference_mode():
            # One point is ambiguous (the bird, its head, the branch): take the best of three.
            output = model(**inputs, multimask_output=len(points) == 1)
        masks = processor.post_process_masks(output.pred_masks, inputs["original_sizes"])[0][0]
        best = int(output.iou_scores[0, 0].argmax())
    return masks[best].numpy().astype(bool)


def _clean(mask: np.ndarray) -> np.ndarray:
    """Drop specks and fill the holes inside the subject."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= MIN_PART * mask.sum()
    keep[0] = False
    solid = keep[labels].astype(np.uint8)
    # Holes: background the outside cannot reach.
    padded = cv2.copyMakeBorder(solid, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flood = padded.copy()
    cv2.floodFill(flood, np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8), (0, 0), 1)
    holes = flood[1:-1, 1:-1] == 0
    return solid.astype(bool) | holes


def hints(settings: MosaicSettings) -> list[SubjectPoint]:
    """The author's points, or the middle of the photo as the subject when there is none."""
    points = list(settings.points)
    if not any(p.subject for p in points):
        points.insert(0, SubjectPoint(x=50, y=50))
    return points


def clicked(settings: MosaicSettings, click: SubjectPoint) -> list[SubjectPoint]:
    """The points after a click on the photo: on a point, it goes; elsewhere, ``click`` is
    added. It starts from the points shown, so the middle of the photo (the subject while
    there is none) stays unless clicked away."""
    shown = hints(settings)
    near = next((p for p in shown if math.hypot(p.x - click.x, p.y - click.y) <= POINT_REACH), None)
    return [p for p in shown if p is not near] if near else [*shown, click]


def _cache_path(slug: str, page: Page, points: list[SubjectPoint]) -> Path:
    crop = page.crop
    hints_key = ";".join(f"{p.x:.1f},{p.y:.1f},{int(p.subject)}" for p in points)
    key = f"{MODEL_ID}|{crop.left},{crop.top},{crop.right},{crop.bottom}|{hints_key}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    return book_path(slug) / "masks" / f"{page.id}-{digest}.png"


def subject_mask(slug: str, page: Page, settings: MosaicSettings) -> np.ndarray:
    """The subject of the page's cropped photo (bool, photo size), from the cache or SAM2.

    Each subject point is cut out on its own, with every background point, and the cuts are
    joined: two birds apart stay two whole birds (as one object SAM2 mixes them up), and a
    second point on the same bird adds what the first one missed.

    Raises ``BackgroundError`` when SAM2 is not installed or finds nothing at the points.
    """
    points = hints(settings)
    path = _cache_path(slug, page, points)
    if path.exists():
        with Image.open(path) as cached:
            return np.asarray(cached.convert("L")) > 127
    if not available():
        raise BackgroundError("SAM2 is not installed: rebuild the Docker image.")
    photo = pages.cropped_photo(slug, page)
    w, h = photo.size

    def pixels(p: SubjectPoint) -> tuple[float, float]:
        return w * p.x / 100, h * p.y / 100

    away = [pixels(p) for p in points if not p.subject]
    mask = np.zeros((h, w), bool)
    for point in (p for p in points if p.subject):
        mask |= _predict(photo, [pixels(point), *away], [1] + [0] * len(away))
    mask = _clean(mask)
    if not mask.any():
        raise BackgroundError("SAM2 found no subject at those points.")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path)
    return mask


def outline(photo: Image.Image, mask: np.ndarray) -> Image.Image:
    """The photo with the background faded, to check the cut."""
    rgb = np.asarray(photo.convert("RGB")).copy()
    rgb[~mask] = (rgb[~mask] * 0.25 + 191).astype(np.uint8)
    return Image.fromarray(rgb)
