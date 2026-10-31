"""Background removal. SAM2 itself is replaced by a fake: the suite never downloads the model.

To check the real model on a photo, set ``COLORIN_SAM_TEST=1`` (downloads ~320 MB once).
"""

import os

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.core import background, books, imaging, mosaic, pages
from app.core.schema import MosaicSettings

from .conftest import png_bytes


def _bird_on_grass() -> Image.Image:
    """A dark 'bird' (ellipse) in the middle of a mid-gray striped 'grass'."""
    image = Image.new("RGB", (400, 300), (110, 140, 100))
    draw = ImageDraw.Draw(image)
    for x in range(0, 400, 12):
        draw.line((x, 300, x + 30, 0), fill=(70, 100, 60), width=4)
    draw.ellipse((140, 100, 260, 200), fill=(30, 30, 30))
    return image


def _ellipse_mask(size=(400, 300)) -> np.ndarray:
    y, x = np.indices(size[::-1])
    return ((x - 200) / 60) ** 2 + ((y - 150) / 50) ** 2 <= 1


@pytest.fixture
def fake_sam(monkeypatch):
    calls = []

    def predict(image, point):
        calls.append(point)
        mask = _ellipse_mask(image.size)
        mask[5:9, 5:9] = True  # a speck, to be cleaned away
        mask[148:152, 198:202] = False  # a hole, to be filled
        return mask

    monkeypatch.setattr(background, "_predict", predict)
    monkeypatch.setattr(background, "available", lambda: True)
    return calls


def _page(photo_bytes):
    book = books.create_book("Aves sin fondo")
    page = pages.add_photo(book.slug, "ave.png", photo_bytes)
    settings = MosaicSettings(columns=20, tones=3, remove_background=True)
    return books.load_book(book.slug), pages.update_page(book.slug, page.id, mosaic=settings)


def test_mask_is_cleaned_cached_and_keyed_by_the_point(fake_sam):
    book, page = _page(png_bytes(_bird_on_grass()))
    settings = page.mosaic
    mask = background.subject_mask(book.slug, page, settings)
    assert (mask == _ellipse_mask()).all()  # no speck, no hole
    assert fake_sam == [(200.0, 150.0)]  # the middle of the photo, in pixels
    background.subject_mask(book.slug, page, settings)
    assert len(fake_sam) == 1  # from the cache
    background.subject_mask(book.slug, page, settings.model_copy(update={"subject_x": 30}))
    assert len(fake_sam) == 2
    pages.delete_page(book.slug, page.id)
    assert not list((books.book_path(book.slug) / "masks").glob("*.png"))


def test_mosaic_without_background_is_white_and_unnumbered_outside_the_subject(fake_sam):
    book, page = _page(png_bytes(_bird_on_grass()))
    grid, settings = imaging.mosaic_draft(book, page)
    white = settings.tones - 1
    assert (grid[0, :, 0] == white).all() and (grid[:, 0, 0] == white).all()  # the grass is gone
    assert grid[grid.shape[0] // 2, grid.shape[1] // 2, 0] == 0  # the bird is black
    numbered = mosaic.numbered(grid, settings)
    assert 0 < len(numbered) < grid.shape[0] * grid.shape[1] // 3


def test_missing_sam_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(background, "available", lambda: False)
    book, page = _page(png_bytes(_bird_on_grass()))
    with pytest.raises(background.BackgroundError):
        imaging.convert_page(book, page, "mosaic")
    assert pages.load_pages(book.slug)[0].versions == []


@pytest.mark.skipif(not os.environ.get("COLORIN_SAM_TEST"), reason="downloads the SAM2 model; set COLORIN_SAM_TEST=1")
def test_real_sam2_finds_the_bird():
    book, page = _page(png_bytes(_bird_on_grass()))
    mask = background.subject_mask(book.slug, page, page.mosaic)
    overlap = (mask & _ellipse_mask()).sum() / (mask | _ellipse_mask()).sum()
    assert overlap > 0.8
