import pytest
from PIL import Image

from app.core import books, imaging, lineart, pages
from app.core.schema import Crop, Version


def _version() -> Version:
    return Version(n=0, engine="draft", style="cartoon", age_group="6-8", background="simplify", created_at="now")


def test_create_book_and_add_photos(photo):
    book = books.create_book("Aves del jardín", style="cartoon")
    assert book.slug == "aves-del-jardin"
    assert books.load_book(book.slug).style == "cartoon"
    first = pages.add_photo(book.slug, "tucan.png", photo)
    pages.add_photo(book.slug, "colibri.png", photo)
    assert [p.original_name for p in pages.load_pages(book.slug)] == ["tucan.png", "colibri.png"]
    assert pages.original_path(book.slug, first).exists()
    assert books.create_book("Aves del jardín").slug != book.slug


def test_unreadable_upload_is_rejected():
    book = books.create_book("Test")
    with pytest.raises(ValueError):
        pages.add_photo(book.slug, "notes.txt", b"not an image")
    assert pages.load_pages(book.slug) == []


def test_versions_are_numbered_selected_and_never_overwritten(photo, line_art):
    book = books.create_book("Test")
    page = pages.add_photo(book.slug, "a.png", photo)
    clean = lineart.clean(line_art, "6-8").image
    pages.add_version(book.slug, page.id, _version(), line_art, clean)
    page = pages.add_version(book.slug, page.id, _version(), line_art, clean)
    assert [v.n for v in page.versions] == [1, 2]
    assert page.selected == 2 and page.status == "converted"
    assert pages.version_path(book.slug, page.id, 1).exists()
    page = pages.select_version(book.slug, page.id, 1)
    assert pages.selected_path(book.slug, page) == pages.version_path(book.slug, page.id, 1)
    assert pages.approve(book.slug, page.id).status == "approved"


def test_approve_requires_a_coloring_page(photo):
    book = books.create_book("Test")
    page = pages.add_photo(book.slug, "a.png", photo)
    with pytest.raises(ValueError):
        pages.approve(book.slug, page.id)


def test_move_and_delete(photo):
    book = books.create_book("Test")
    a, b, c = (pages.add_photo(book.slug, f"{n}.png", photo) for n in "abc")
    pages.move_page(book.slug, c.id, -2)
    assert [p.id for p in pages.load_pages(book.slug)] == [c.id, a.id, b.id]
    pages.move_page(book.slug, c.id, -1)  # already first: stays
    pages.delete_page(book.slug, a.id)
    assert [p.id for p in pages.load_pages(book.slug)] == [c.id, b.id]
    assert not pages.original_path(book.slug, a).exists()


def test_crop_applies_to_the_photo_and_its_size(photo):
    book = books.create_book("Test")
    page = pages.add_photo(book.slug, "a.png", photo)
    page = pages.set_crop(book.slug, page.id, Crop(left=0.5, top=0.0, right=1.0, bottom=0.5))
    assert pages.cropped_photo(book.slug, page).size == (400, 300)
    assert pages.photo_size(book.slug, page) == (400, 300)


def test_draft_conversion_end_to_end(photo):
    book = books.create_book("Test", age_group="3-5")
    page = pages.add_photo(book.slug, "a.png", photo)
    page = imaging.convert_page(book, page, "draft")
    assert page.selected == 1 and page.versions[0].engine == "draft"
    assert Image.open(pages.selected_path(book.slug, page)).mode == "1"


def test_prompt_carries_style_age_background_title_and_instructions():
    prompt = imaging.build_prompt("cartoon", "3-5", "remove", "Tucán", "solo el ave")
    assert "children's cartoon" in prompt and "ages 3 to 5" in prompt and "no background" in prompt
    assert "The subject is: Tucán." in prompt and "solo el ave" in prompt
    assert "AUTHOR'S INSTRUCTIONS" not in imaging.build_prompt("realistic", "9+", "keep")


def test_aspect_follows_the_photo():
    assert imaging.aspect_for(4000, 3000) == "4:3"
    assert imaging.aspect_for(3000, 4000) == "3:4"
    assert imaging.aspect_for(1000, 1050) == "1:1"
