"""Shared fixtures: an isolated books/ folder and synthetic images.

Run inside the container: ``docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider tests``
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.core import books


@pytest.fixture(autouse=True)
def books_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "BOOKS_DIR", tmp_path / "books")
    return tmp_path / "books"


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def photo() -> bytes:
    """A colorful 'photo': gradient sky, green hill, red sun."""
    w, h = 800, 600
    gradient = np.linspace(120, 230, h, dtype=np.uint8)[:, None].repeat(w, axis=1)
    image = Image.fromarray(np.dstack([gradient // 2, gradient // 2 + 40, gradient]).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    draw.ellipse((-100, 350, 900, 900), fill=(20, 90, 30))
    draw.ellipse((560, 80, 700, 220), fill=(220, 40, 30))
    return png_bytes(image)


@pytest.fixture
def line_art() -> bytes:
    """What a well-behaved model returns: thick black outlines on white, with gray AA edges."""
    image = Image.new("L", (900, 1200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 200, 750, 800), outline=0, width=12)
    draw.ellipse((330, 380, 420, 470), outline=0, width=10)
    draw.ellipse((480, 380, 570, 470), outline=0, width=10)
    draw.arc((300, 450, 600, 700), 20, 160, fill=0, width=12)
    draw.rectangle((100, 900, 800, 1100), outline=0, width=12)
    return png_bytes(image.resize((900, 1200), Image.Resampling.BICUBIC))
