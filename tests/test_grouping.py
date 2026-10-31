import numpy as np
from PIL import Image

from app.core import books, grouping, imaging, pages, tones

from .conftest import png_bytes


def _noisy_halves() -> Image.Image:
    """A dark and a light half, both with noise: texture a grouping should flatten."""
    rng = np.random.default_rng(0)
    base = np.zeros((200, 300, 3), np.float32)
    base[:, :150] = 60
    base[:, 150:] = 190
    noisy = np.clip(base + rng.normal(0, 8, base.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(noisy)


def test_grouping_flattens_texture_more_with_a_bigger_bandwidth():
    image = _noisy_halves()
    spread = lambda img: np.asarray(img, dtype=float)[:, 20:130].std()  # noqa: E731
    small, big = grouping.group(image, 10), grouping.group(image, 40)
    assert spread(big) < spread(small) < spread(image)
    left, right = np.asarray(big)[:, :140].mean(), np.asarray(big)[:, 160:].mean()
    assert left < 100 < right  # the two halves stay apart


def test_big_photos_are_grouped_at_the_working_size_and_cached():
    image = Image.new("RGB", (2400, 1600), (120, 130, 140))
    grouped = grouping.group(image, 20, key=("big", 1))
    assert max(grouped.size) == grouping.GROUP_SIZE and grouped.size[0] / grouped.size[1] == 1.5
    again = grouping.group(Image.new("RGB", (10, 10)), 20, key=("big", 1))  # same key: from the cache
    assert again.size == grouped.size


def test_grouping_comes_after_the_curve_and_stays_out_of_the_reference_photo(photo):
    book = books.create_book("Agrupar")
    page = pages.add_photo(book.slug, "foto.png", photo)
    page = pages.update_page(book.slug, page.id, curve=tones.PRESETS["darken"], group=30)
    curved = pages.cropped_photo(book.slug, page, group=False)
    grouped = pages.cropped_photo(book.slug, page)
    assert np.asarray(curved).mean() < np.asarray(pages.cropped_photo(book.slug, page, curve=False)).mean()
    assert len(np.unique(np.asarray(grouped).reshape(-1, 3), axis=0)) < len(
        np.unique(np.asarray(curved).reshape(-1, 3), axis=0)
    )
    page = imaging.convert_page(books.load_book(book.slug), page, "mosaic")
    assert page.selected_version.group == 30
