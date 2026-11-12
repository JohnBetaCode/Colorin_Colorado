"""Local GPU engine client: an open-weights model on this machine's NVIDIA GPU.

The ``local-image`` Compose service (``local_image/server.py``, profile ``gpu``) runs
Qwen-Image-2.1 by default; ``./launch.sh`` starts it when the GPU can run it. Like Stable
Diffusion it only draws coloring pages, from the uploaded photo as the reference image; texts,
translations and covers stay on Gemini. There is no cost per image.

A page takes 30-60 s on an RTX 5090 at 1K (the default; the first pages after the model loads
are the slow ones) and about 105 s at the native 2K.
After 20 idle minutes the server unloads the model to free RAM and the next page reloads it. Settings: ``config/.env``
(``LOCAL_IMAGE_URL`` and ``LOCAL_IMAGE_PAGE_SIZE`` here, ``LOCAL_IMAGE_*`` for the server).
"""

from __future__ import annotations

import base64
import threading
import time
from io import BytesIO

import requests
from PIL import Image

from app.core import usage
from app.core.config import get_settings

TIMEOUT = 900  # seconds: a 2K page plus a model reload after an idle unload
HEALTH_TIMEOUT = 3
# Models whose license does not allow selling what they draw without a separate agreement:
# Qwen-Image-2.1 is under the Qwen Research License (research and evaluation only).
NON_COMMERCIAL_MODELS = frozenset({"Qwen/Qwen-Image-2.1", "Qwen/Qwen-Image-2.1-Turbo"})
# Server states in which a page can be requested (an idle server reloads the model first).
USABLE = ("ready", "idle", "loading")

_lock = threading.Lock()  # the server draws one image at a time


class LocalImageError(RuntimeError):
    """Raised when the local GPU server is unreachable, not ready, or fails."""


# (url, timestamp, payload or error) of the last /health call
_health_cache: tuple[str, float, dict | LocalImageError] | None = None


def model_label(model_id: str) -> str:
    """Usage-log model name for a Hugging Face model id: 'Qwen/Qwen-Image-2.1' -> 'qwen-image-2.1-local'."""
    return model_id.rsplit("/", 1)[-1].lower() + "-local"


def health(max_age: float = 0) -> dict:
    """The server's /health payload; raises ``LocalImageError`` when it cannot be reached.

    ``max_age`` reuses the last answer, reachable or not, for that many seconds: Streamlit
    reruns ask on every click, and resolving a Compose service that is not running can take a
    moment.
    """
    global _health_cache
    url = f"{get_settings().local_url}/health"
    now = time.time()
    if max_age and _health_cache and _health_cache[0] == url and now - _health_cache[1] < max_age:
        result = _health_cache[2]
        if isinstance(result, LocalImageError):
            raise result
        return result
    try:
        response = requests.get(url, timeout=HEALTH_TIMEOUT)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        result = LocalImageError(f"The local GPU server is not reachable at {get_settings().local_url}: {exc}")
    _health_cache = (url, now, result)
    if isinstance(result, LocalImageError):
        raise result
    return result


def available(max_age: float = 15) -> bool:
    """Whether a page can be requested now (the engine's buttons are enabled)."""
    try:
        return health(max_age).get("status") in USABLE
    except LocalImageError:
        return False


def is_non_commercial(model_id: str | None) -> bool:
    return model_id in NON_COMMERCIAL_MODELS


def edit_image(photo: Image.Image, prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
    """Redraw ``photo`` as ``prompt`` asks; returns (PNG bytes, the model id that drew it)."""
    settings = get_settings()
    buffer = BytesIO()
    photo.convert("RGB").save(buffer, format="JPEG", quality=92)
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "reference_images": [base64.b64encode(buffer.getvalue()).decode()],
        "size": settings.local_size,
    }
    with _lock:
        try:
            response = requests.post(f"{settings.local_url}/generate", json=payload, timeout=TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise LocalImageError(f"The local GPU server is not reachable at {settings.local_url}: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise LocalImageError(f"Local GPU server ({response.status_code}): {str(detail)[:300]}")
    png = response.content
    try:
        Image.open(BytesIO(png)).verify()
    except Exception as exc:
        raise LocalImageError(f"The local GPU server returned no usable image: {exc}") from exc
    model_id = response.headers.get("X-Model", "local-model")
    usage.record("image_generation", model_label(model_id), images=1)
    return png, model_id
