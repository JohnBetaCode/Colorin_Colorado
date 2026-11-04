import io
import zipfile

import numpy as np
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.core import books, export, lineart, page_templates, pages
from app.core.schema import Version

SIZES = {"letter": (540.0, 698.4), "square": (540.0, 518.4)}  # content boxes, in points


def _book_with_page(photo, line_art, **fields):
    book = books.create_book("Aves del jardín", **fields)
    page = pages.add_photo(book.slug, "tucan.png", photo)
    version = Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now")
    pages.add_version(book.slug, page.id, version, line_art, lineart.clean(line_art, "6-8").image)
    pages.update_page(book.slug, page.id, title="Tucán pico iris", info="Dónde vive: bosques")
    return books.load_book(book.slug), pages.load_pages(book.slug)[0]


@pytest.mark.parametrize("design", list(page_templates.PREDEFINED))
@pytest.mark.parametrize("size", list(SIZES))
def test_predefined_designs_fit_any_page_and_leave_their_area_empty(design, size):
    w, h = SIZES[size]
    px = (round(w / 72 * page_templates.DPI), round(h / 72 * page_templates.DPI))
    art = np.asarray(page_templates._predefined(design, *px).convert("L")) < 128
    assert art.shape == (px[1], px[0]) and art.any()
    book = books.create_book("Plantillas")
    left, top, right, bottom = page_templates.area_fractions(book, design, px)
    inside = art[round(top * px[1]) : round(bottom * px[1]), round(left * px[0]) : round(right * px[0])]
    assert inside.mean() < 0.002, (design, size, inside.mean())  # the drawing's place is blank


def test_uploaded_templates_become_one_bit_and_find_their_empty_area(tmp_path):
    book = books.create_book("Aves del jardín")
    picture = Image.new("RGB", (800, 1000), (250, 240, 230))
    draw = ImageDraw.Draw(picture)
    draw.rectangle((0, 0, 799, 999), outline=(30, 60, 20), width=90)  # a thick colored frame
    data = io.BytesIO()
    picture.save(data, format="PNG")
    book = page_templates.add_upload(book, data.getvalue(), "Mi marco")
    template = book.page_templates[0]
    assert template.name == "Mi marco" and template.id.startswith("u")
    stored = Image.open(page_templates.uploaded_path(book, template.id))
    assert set(np.unique(np.asarray(stored.convert("L")))) <= {0, 255}
    left, top, right, bottom = template.area
    assert 0.1 < left < 0.16 and 0.08 < top < 0.13 and 0.84 < right < 0.9 and 0.87 < bottom < 0.92
    with pytest.raises(ValueError):
        page_templates.add_upload(book, b"not an image", "x")


def test_pages_use_the_books_template_unless_they_choose(photo, line_art):
    book, page = _book_with_page(photo, line_art, page_template="stars")
    assert page_templates.for_page(book, page) == "stars"
    assert page_templates.for_page(book, page.model_copy(update={"page_template": "clouds"})) == "clouds"
    assert page_templates.for_page(book, page.model_copy(update={"page_template": page_templates.NO_TEMPLATE})) is None
    assert page_templates.for_page(book, page.model_copy(update={"page_template": "gone"})) is None


def test_template_pages_print_the_frame_and_keep_the_drawing_inside(photo, line_art):
    book, page = _book_with_page(photo, line_art, page_template="flowers")
    layout = export._layout(book)
    area = export.sheet_area(book, page, layout)
    x, y, w, h = layout.content
    assert x < area[0] and y < area[1] and area[2] < w and area[3] < h  # smaller than the page
    narrower = export.sheet_area(book, page.model_copy(update={"template_inset": 10}), layout)
    assert narrower[2] < area[2] and narrower[3] < area[3]

    reader = PdfReader(export.export_book_pdf(book))
    sheet = export.sheets(book, export.preflight(book).included).index(page) if False else -1
    images = [Image.open(io.BytesIO(i.data)) if not hasattr(i, "image") else i.image for i in reader.pages[sheet].images]
    grays = [i for i in images if i.mode == "L"]
    assert len(grays) == 2  # the template and the drawing, both lossless
    for image in grays:
        assert set(np.unique(np.asarray(image))) <= {0, 255}
    assert export.page_preview(book, page).size[0] > 300


def test_uploaded_templates_travel_with_the_book(photo, line_art):
    book, _ = _book_with_page(photo, line_art)
    picture = Image.new("L", (300, 400), 255)
    ImageDraw.Draw(picture).rectangle((0, 0, 299, 399), outline=0, width=20)
    data = io.BytesIO()
    picture.save(data, format="PNG")
    book = page_templates.add_upload(book, data.getvalue(), "Marco")
    archive = books.export_zip(book.slug)
    assert f"page_templates/{book.page_templates[0].id}.png" in zipfile.ZipFile(io.BytesIO(archive)).namelist()
    copy = books.import_zip(archive)
    assert page_templates.uploaded_path(copy, copy.page_templates[0].id).exists()
    book = page_templates.delete_upload(book, book.page_templates[0].id)
    assert book.page_templates == []
