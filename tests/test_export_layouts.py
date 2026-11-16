"""Facing-pages layout and the print-shop PDF (bleed and crop marks)."""

import numpy as np
import pytest
from pypdf import PdfReader

from app.core import books, export, imaging, kdp, lineart, pages
from app.core.schema import Page, Version
from tests.test_export import _images


def _book(photo, line_art, count=3, **book_fields):
    book = books.create_book("Animales del jardín", **book_fields)
    clean = lineart.clean(line_art, "6-8").image
    version = Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now")
    for i in range(count):
        page = pages.add_photo(book.slug, f"foto-{i}.png", photo)
        pages.add_version(book.slug, page.id, version.model_copy(), line_art, clean)
        pages.update_page(book.slug, page.id, title=f"Animal {i + 1}", info="Dónde vive: en el jardín", status="approved")
    return books.load_book(book.slug)


def _order(book: books.Book) -> list[export.Sheet]:
    return export.sheets(book, export.preflight(book).included)


def _assert_spreads(order: list[export.Sheet]) -> None:
    """Every drawing is a right-hand page (even index: page 1 is the title, on the right)
    and, unless it is a mosaic, the photo page of the same page faces it."""
    for i, sheet in enumerate(order):
        if isinstance(sheet, Page):
            assert i % 2 == 0, (i, order)
            if not sheet.is_mosaic:
                facing = order[i - 1]
                assert isinstance(facing, export.PhotoSheet) and facing.page.id == sheet.id


@pytest.mark.parametrize("owner, backs, legal", [(True, True, ""), (True, False, ""), (False, False, "© 2026"), (False, True, "© 2026")])
def test_facing_pages_put_every_drawing_on_the_right(photo, line_art, owner, backs, legal):
    book = _book(photo, line_art, layout="facing", include_owner_page=owner, blank_backs=backs, legal=legal)
    order = _order(book)
    _assert_spreads(order)
    assert sum(isinstance(s, export.PhotoSheet) for s in order) == 3
    assert len(PdfReader(export.export_book_pdf(book)).pages) == len(order)


def test_facing_pages_with_mosaics_keep_the_parity(photo, line_art):
    book = _book(photo, line_art, count=2, layout="facing", include_owner_page=False)
    mystery = pages.add_photo(book.slug, "misterio.png", photo)
    imaging.convert_pages(book, [mystery], "mosaic")
    last = pages.add_photo(book.slug, "ultima.png", photo)
    clean = lineart.clean(line_art, "6-8").image
    pages.add_version(book.slug, last.id, Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now"), line_art, clean)
    book = books.load_book(book.slug)
    order = _order(book)
    _assert_spreads(order)
    assert any(isinstance(s, Page) and s.is_mosaic for s in order)
    assert len(PdfReader(export.export_book_pdf(book)).pages) == len(order)


def test_facing_pages_split_the_photo_from_the_drawing(photo, line_art):
    book = _book(photo, line_art, count=1, layout="facing", include_owner_page=False)
    order = _order(book)
    reader = PdfReader(export.export_book_pdf(book))
    left = next(i for i, s in enumerate(order) if isinstance(s, export.PhotoSheet))
    left_images, right_images = _images(reader, left), _images(reader, left + 1)
    assert [image.mode for image in left_images] == ["RGB"]  # the photo, alone
    assert "Animal 1" in reader.pages[left].extract_text()
    assert [image.mode for image in right_images] == ["L"]  # the drawing, alone, still pure black and white
    assert set(np.unique(np.array(right_images[0]))) <= {0, 255}
    assert "Animal 1" not in reader.pages[left + 1].extract_text()


def test_facing_pages_check_captions_against_their_own_box(photo, line_art):
    book = _book(photo, line_art, count=1, layout="facing")
    page = pages.load_pages(book.slug)[0]
    assert export.caption_fits(book, page)
    # Longer than the bottom box holds, short enough for a third of the left-hand page.
    medium = pages.update_page(book.slug, page.id, info="Un dato sobre el animal y su casa. " * 35)
    assert export.caption_fits(book, medium)
    assert not export.caption_fits(book.model_copy(update={"layout": "bottom_box"}), medium)
    long_page = pages.update_page(book.slug, page.id, info="Un dato sobre el animal y su casa. " * 150)
    assert not export.caption_fits(book, long_page)
    export.export_book_pdf(book)  # still builds; the text is clipped


def test_facing_pages_need_no_blank_backs_for_kdp(photo, line_art):
    book = _book(photo, line_art, layout="facing")
    issues = {issue.key for issue in kdp.review(book).issues}
    assert "no_blank_backs" not in issues
    assert "too_few_pages" in issues  # each drawing adds two pages, like with blank backs


def test_print_shop_pdf_adds_bleed_and_crop_marks(photo, line_art):
    book = _book(photo, line_art, count=2)
    plain = PdfReader(export.export_book_pdf(book))
    path = export.export_book_pdf(book, print_shop=True)
    assert export.is_print_shop(path) and path.name.endswith("-print-shop.pdf")
    marked = PdfReader(path)
    assert len(marked.pages) == len(plain.pages)

    border = export.PRINT_BLEED + export.PRINT_SLUG
    trim_w, trim_h = export.PAGE_SIZES[book.page_size]
    for page in marked.pages:
        assert float(page.mediabox.width) == pytest.approx(trim_w + 2 * border)
        assert float(page.mediabox.height) == pytest.approx(trim_h + 2 * border)
        trim = [float(v) for v in page.trimbox]
        assert trim == pytest.approx([border, border, border + trim_w, border + trim_h])
        bleed = [float(v) for v in page.bleedbox]
        assert bleed == pytest.approx([export.PRINT_SLUG, export.PRINT_SLUG, border + trim_w + export.PRINT_BLEED, border + trim_h + export.PRINT_BLEED])
    # Same content, unscaled: the line art keeps its pixels and stays pure black and white.
    for index in (2, 3):
        art = [image for image in _images(marked, index) if image.mode == "L"]
        assert art and set(np.unique(np.array(art[0]))) <= {0, 255}
        assert art[0].size == next(image for image in _images(plain, index) if image.mode == "L").size


def test_print_shop_pdf_crop_marks_stay_outside_the_bleed(photo, line_art):
    import pypdfium2 as pdfium

    book = _book(photo, line_art, count=1, include_owner_page=False)
    path = export.export_book_pdf(book, print_shop=True)
    pdf = pdfium.PdfDocument(path.read_bytes())
    try:
        image = np.array(pdf[0].render(scale=2).to_pil().convert("L"))
    finally:
        pdf.close()
    scale = 2
    slug = round(export.PRINT_SLUG * scale)
    border = round((export.PRINT_BLEED + export.PRINT_SLUG) * scale)
    corner = image[: border + 2, : border + 2]
    assert (corner[: slug - 2] < 128).any()  # a mark in the slug, above the page's corner
    bleed_strip = image[slug + 2 : border - 2, : border - 2]
    assert (bleed_strip > 250).all()  # the bleed is white: nothing printed, no mark
