"""Stable Diffusion client: a stable-diffusion.cpp server (``sd-server``) running FLUX.1 Kontext.

The second, optional image engine: it redraws the uploaded photo through the server's
OpenAI-style edit endpoint (``POST /v1/images/edits``, multipart in, base64 PNG out).
It only draws coloring pages; texts and covers stay on Gemini.

The server is slow (about 1-1.5 minutes per page at 768 px and 12 steps) and draws one image
at a time, so calls are serialized here and use a long timeout. After 10 idle minutes it
unloads the model and the next call takes 10-30 s more. ``GET /v1/models`` wakes it up, so the
connection test reads ``/sdcpp/v1/models/status`` instead. Settings: ``config/.env``.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from io import BytesIO

import requests
from PIL import Image

from app.core import usage
from app.core.config import get_settings

MODEL = "stable-diffusion"  # usage.py has no price for it: the author's own server costs nothing per image
TIMEOUT = 900  # seconds; a page can wait behind other users' images
RETRIES = 2
STATUS_TIMEOUT = 10

_lock = threading.Lock()  # the server draws one image at a time


class StableDiffusionError(RuntimeError):
    """Raised when the Stable Diffusion server fails or returns an unusable response."""


def _url() -> str:
    url = get_settings().sd_url
    if not url:
        raise StableDiffusionError(
            "Stable Diffusion is not configured. Set its server URL in config/.env (see the Settings panel)."
        )
    return url


def request_size(width: int, height: int, long_side: int) -> tuple[int, int]:
    """The photo's size with its long side at ``long_side``, both sides multiples of 8."""
    scale = long_side / max(width, height)
    return max(8, round(width * scale / 8) * 8), max(8, round(height * scale / 8) * 8)


def check_connection() -> str:
    """The server's model state (e.g. ``ready``), without waking the model; raises on failure."""
    try:
        response = requests.get(f"{_url()}/sdcpp/v1/models/status", timeout=STATUS_TIMEOUT)
        response.raise_for_status()
        return str(response.json().get("state") or "ok")
    except StableDiffusionError:
        raise
    except Exception as exc:
        raise StableDiffusionError(str(exc)) from exc


def edit_image(photo: Image.Image, prompt: str) -> bytes:
    """Redraw ``photo`` as ``prompt`` asks; returns PNG bytes at the request size.

    The photo is shrunk first: without a size the server works at the photo's own, and a
    2,000 px photo would take many minutes.
    """
    settings = get_settings()
    url = _url()
    size = request_size(*photo.size, settings.sd_size)
    buffer = BytesIO()
    photo.convert("RGB").resize(size, Image.LANCZOS).save(buffer, format="PNG")
    # Extra sampling parameters travel inside the prompt; the server strips the block.
    extra = json.dumps({"sample_params": {"sample_steps": settings.sd_steps}})
    data = {
        "prompt": f"{prompt} <sd_cpp_extra_args>{extra}</sd_cpp_extra_args>",
        "size": f"{size[0]}x{size[1]}",
        "output_format": "png",
        "n": "1",
    }
    files = [("image[]", ("photo.png", buffer.getvalue(), "image/png"))]
    with _lock:
        for attempt in range(RETRIES + 1):
            try:
                response = requests.post(f"{url}/v1/images/edits", files=files, data=data, timeout=TIMEOUT)
                if response.status_code < 500:
                    response.raise_for_status()
                    break
                error: Exception = StableDiffusionError(f"Server error {response.status_code}: {response.text[:200]}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                error = exc
            except requests.RequestException as exc:  # 4xx: retrying will not help
                raise StableDiffusionError(f"Image edit call failed: {exc}") from exc
            if attempt == RETRIES:
                raise StableDiffusionError(f"Image edit call failed: {error}") from error
            time.sleep(10 * (attempt + 1))  # restarting, busy, or loading the model
    try:
        png = base64.b64decode(response.json()["data"][0]["b64_json"])
        Image.open(BytesIO(png)).verify()
    except Exception as exc:
        raise StableDiffusionError(f"The server returned no usable image: {exc}") from exc
    usage.record("image_generation", MODEL, images=1)
    return png
