"""Background removal for mystery mosaics, offline, with a small local model (IS-Net).

The subject of the page's cropped photo is cut out and everything else becomes white paper,
so a mosaic is only the bird, not the grass behind it. The model is IS-Net
(``isnet-general-use``, from the DIS project, Apache-2.0), run on the CPU with ONNX Runtime
in under a second. It downloads by itself the first time into ``models/`` (about 180 MB;
Compose mounts the folder, so it survives rebuilds), and its SHA-256 is checked before it is
loaded, so a damaged or tampered file is never used. Masks are cached in
``books/<slug>/masks/``, keyed by the crop and the model.

``onnxruntime`` is imported only when a mask is needed, so everything else works without it;
``available`` says whether it is installed. The interface matches the ``SAM`` branch's
version of this module (SAM2 with points), so the two can live side by side.
"""

from __future__ import annotations

import hashlib
import importlib.util
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import httpx
import numpy as np
from PIL import Image

from app.core import pages
from app.core.books import book_path, inside
from app.core.config import ROOT_DIR
from app.core.schema import MosaicSettings, Page

MODEL_ID = "isnet-general-use"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODEL_SHA256 = "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a"
MODEL_MB = 180  # download size, shown before the first use
MODELS_DIR = ROOT_DIR / "models"
INPUT = 1024  # the model's input side, in pixels
MEAN = np.array((0.485, 0.456, 0.406), np.float32)
MIN_PART = 0.01  # pieces of the mask smaller than this share of it are dropped (specks)

_lock = threading.Lock()


class BackgroundError(Exception):
    pass


def available() -> bool:
    """Whether ONNX Runtime is installed (it is in the Docker image)."""
    return importlib.util.find_spec("onnxruntime") is not None


def model_path() -> Path:
    return MODELS_DIR / f"{MODEL_ID}.onnx"


def model_downloaded() -> bool:
    """Whether the model is already on disk, so the first use will not download it."""
    return model_path().exists()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download() -> Path:
    path = model_path()
    part = path.with_suffix(".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with part.open("wb") as file:
                for chunk in response.iter_bytes(1 << 20):
                    file.write(chunk)
    except httpx.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise BackgroundError(f"Could not download the background model: {exc}") from exc
    if _sha256(part) != MODEL_SHA256:
        part.unlink(missing_ok=True)
        raise BackgroundError("The downloaded background model is not the expected file.")
    part.replace(path)
    return path


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort

    with _lock:
        path = model_path() if model_path().exists() else _download()
        if _sha256(path) != MODEL_SHA256:
            raise BackgroundError(f"{path.name} is not the expected model; delete it to download it again.")
        return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _predict(image: Image.Image) -> np.ndarray:
    """How sure the model is that each pixel is subject, 0 to 1, at the photo's size."""
    session = _session()
    rgb = np.asarray(image.convert("RGB").resize((INPUT, INPUT), Image.Resampling.LANCZOS), np.float32)
    rgb /= max(float(rgb.max()), 1e-6)
    tensor = (rgb - MEAN).transpose(2, 0, 1)[None].astype(np.float32)
    out = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    out = (out - out.min()) / max(float(out.max() - out.min()), 1e-6)
    return cv2.resize(out, image.size, interpolation=cv2.INTER_LINEAR)


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


def _cache_path(slug: str, page: Page) -> Path:
    crop = page.crop
    key = f"{MODEL_ID}|{crop.left},{crop.top},{crop.right},{crop.bottom}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    folder = book_path(slug) / "masks"
    return inside(folder, folder / f"{page.id}-{digest}.png")


def subject_mask(slug: str, page: Page, settings: MosaicSettings) -> np.ndarray:
    """The subject of the page's cropped photo (bool, photo size), from the cache or the model.

    Raises ``BackgroundError`` when ONNX Runtime is not installed, the model cannot be
    downloaded, or no subject is found.
    """
    path = _cache_path(slug, page)
    if path.exists():
        with Image.open(path) as cached:
            return np.asarray(cached.convert("L")) > 127
    if not available():
        raise BackgroundError("ONNX Runtime is not installed: rebuild the Docker image.")
    # Without the tone curve: the subject is the same however the tones are set, so moving
    # the curve never runs the model again (and the cache key needs no curve).
    photo = pages.cropped_photo(slug, page, curve=False)
    mask = _clean(_predict(photo) > 0.5)
    if not mask.any():
        raise BackgroundError("No subject found in the photo.")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path)
    return mask


def outline(photo: Image.Image, mask: np.ndarray) -> Image.Image:
    """The photo with the background faded, to check the cut."""
    rgb = np.asarray(photo.convert("RGB")).copy()
    rgb[~mask] = (rgb[~mask] * 0.25 + 191).astype(np.uint8)
    return Image.fromarray(rgb)
