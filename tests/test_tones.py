import numpy as np
from PIL import Image

from app.core import books, imaging, pages, tones

from .conftest import png_bytes


def test_identity_leaves_every_tone_alone():
    assert (tones.lut(None) == np.arange(256)).all()
    assert (tones.lut([(0, 0), (255, 255)]) == np.arange(256)).all()


def test_curve_passes_through_its_points_and_never_goes_backwards():
    points = [(0, 0), (64, 20), (128, 200), (192, 210), (255, 255)]
    table = tones.lut(points)
    for x, y in points:
        assert abs(int(table[x]) - y) <= 1
    assert (np.diff(table.astype(int)) >= 0).all()  # monotone: no overshoot between points


def test_end_points_are_the_black_and_white_points():
    table = tones.lut([(40, 0), (200, 255)])
    assert table[:41].max() == 0 and table[200:].min() == 255
    assert 0 < table[120] < 255


def test_points_are_cleaned_up():
    assert tones.normalized([(300, -5), (10, 10), (10, 30)]) == [(10, 30), (255, 0)]
    assert tones.normalized([(5, 5)]) == tones.IDENTITY
    assert tones.is_identity(None) and not tones.is_identity(tones.PRESETS["contrast"])


def test_histogram_is_scaled_to_the_tallest_bin():
    image = Image.new("L", (10, 10), 0)
    image.paste(255, (0, 0, 10, 5))
    heights = tones.histogram(image)
    assert len(heights) == tones.HISTOGRAM_BINS and heights[0] == heights[-1] == 1.0
    assert sum(heights[1:-1]) == 0


def test_the_curve_reaches_every_engine_but_not_the_original(photo):
    book = books.create_book("Curvas")
    page = pages.add_photo(book.slug, "foto.png", photo)
    before = np.asarray(pages.cropped_photo(book.slug, page)).copy()
    page = pages.update_page(book.slug, page.id, curve=tones.PRESETS["darken"])
    after = np.asarray(pages.cropped_photo(book.slug, page))
    assert after.mean() < before.mean()
    assert (np.asarray(pages.cropped_photo(book.slug, page, curve=False)) == before).all()
    page = imaging.convert_page(books.load_book(book.slug), page, "mosaic")
    assert page.selected_version.curve == tones.PRESETS["darken"]
