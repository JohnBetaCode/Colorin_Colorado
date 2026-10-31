"""Background removal for mystery mosaics, with SAM2 (Segment Anything 2), offline.

The author points at the subject (the middle of the cropped photo unless moved) and SAM2
returns its mask; everything else becomes white paper, so a mosaic is only the bird, not
the grass behind it. The model is SAM 2.1 base-plus, the middle size, through
``transformers``: its weights are public on Hugging Face and download by themselves the
first time (about 320 MB, under ``models/``, which Compose mounts). Masks are cached in
``books/<slug>/masks/``, keyed by the crop, the point and the model, because SAM2 takes a
few seconds on a CPU.

``torch`` and ``transformers`` are imported only when a mask is needed, so everything
else works without them; ``available`` says whether they are installed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.core import pages
from app.core.books import book_path
from app.core.schema import MosaicSettings, Page

MODEL_ID = "facebook/sam2.1-hiera-base-plus"
MODEL_MB = 320  # download size, shown before the first use
MIN_PART = 0.01  # pieces of the mask smaller than this share of it are dropped (specks)

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


def _predict(image: Image.Image, point: tuple[float, float]) -> np.ndarray:
    """SAM2's best mask (bool, image size) for the object under ``point`` (pixels)."""
    import torch

    with _lock:  # one model, shared by the app's threads
        processor, model = _model()
        inputs = processor(images=image, input_points=[[[list(point)]]], input_labels=[[[1]]], return_tensors="pt")
        with torch.inference_mode():
            output = model(**inputs, multimask_output=True)
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


def _cache_path(slug: str, page: Page, point: tuple[int, int]) -> Path:
    crop = page.crop
    key = f"{MODEL_ID}|{crop.left},{crop.top},{crop.right},{crop.bottom}|{point[0]},{point[1]}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    return book_path(slug) / "masks" / f"{page.id}-{digest}.png"


def subject_mask(slug: str, page: Page, settings: MosaicSettings) -> np.ndarray:
    """The subject of the page's cropped photo (bool, photo size), from the cache or SAM2.

    Raises ``BackgroundError`` when SAM2 is not installed or finds nothing at the point.
    """
    point = (settings.subject_x, settings.subject_y)
    path = _cache_path(slug, page, point)
    if path.exists():
        with Image.open(path) as cached:
            return np.asarray(cached.convert("L")) > 127
    if not available():
        raise BackgroundError("SAM2 is not installed: rebuild the Docker image.")
    photo = pages.cropped_photo(slug, page)
    w, h = photo.size
    mask = _clean(_predict(photo, (w * point[0] / 100, h * point[1] / 100)))
    if not mask.any():
        raise BackgroundError("SAM2 found no subject at that point.")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path)
    return mask


def outline(photo: Image.Image, mask: np.ndarray, point: tuple[int, int]) -> Image.Image:
    """The photo with the background faded and the subject point marked, to check the cut."""
    rgb = np.asarray(photo.convert("RGB")).copy()
    rgb[~mask] = (rgb[~mask] * 0.25 + 191).astype(np.uint8)
    h, w = mask.shape
    center = (round(w * point[0] / 100), round(h * point[1] / 100))
    radius = max(6, max(w, h) // 80)
    cv2.circle(rgb, center, radius + 3, (255, 255, 255), -1)
    cv2.circle(rgb, center, radius, (220, 30, 30), -1)
    return Image.fromarray(rgb)
