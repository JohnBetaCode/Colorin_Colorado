from io import BytesIO

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from app.core import books, export, lineart, pages
from app.core.schema import Version


def _book_with_pages(photo, line_art, **book_fields):
    book = books.create_book("Aves del jardín", subtitle="Para colorear", dedication="Para Sofía", **book_fields)
    clean = lineart.clean(line_art, "6-8").image
    version = Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now")
    toucan = pages.add_photo(book.slug, "tucan.png", photo)
    pages.add_version(book.slug, toucan.id, version.model_copy(), line_art, clean)
    pages.update_page(
        book.slug, toucan.id, title="Tucán pico iris", subtitle="Ramphastos sulfuratus",
        info="Dónde vive: bosques húmedos\nDato curioso: su pico es liviano y hueco", status="approved",
    )
    plain = pages.add_photo(book.slug, "sin-texto.png", photo)
    pages.add_version(book.slug, plain.id, version.model_copy(), line_art, clean)
    pages.add_photo(book.slug, "pendiente.png", photo)  # never converted: skipped
    return books.load_book(book.slug), clean.size


def _images(reader: PdfReader, page_index: int) -> list[Image.Image]:
    return [Image.open(BytesIO(img.data)) if not hasattr(img, "image") else img.image for img in reader.pages[page_index].images]


def test_preflight_lists_what_the_book_will_contain(photo, line_art):
    book, _ = _book_with_pages(photo, line_art)
    report = export.preflight(book)
    assert [p.original_name for p in report.included] == ["tucan.png", "sin-texto.png"]
    assert [p.original_name for p in report.not_approved] == ["sin-texto.png"]
    assert [p.original_name for p in report.without_version] == ["pendiente.png"]
    assert report.overflowing == []


def test_pdf_has_cover_owner_page_and_pure_black_and_white_line_art(photo, line_art):
    book, _ = _book_with_pages(photo, line_art)
    reader = PdfReader(export.export_book_pdf(book))
    assert len(reader.pages) == 4  # cover, owner page, two coloring pages
    assert "Aves del jardín" in reader.pages[0].extract_text()
    assert "Este libro pertenece a" in reader.pages[1].extract_text()
    assert "Tucán pico iris" in reader.pages[2].extract_text()

    line_arts = photos = 0
    for index in (2, 3):
        for image in _images(reader, index):
            if image.mode == "L":  # line art is grayscale (and upsampled when needed); photos are RGB
                line_arts += 1
                assert set(np.unique(np.array(image))) <= {0, 255}
            else:
                photos += 1
    assert line_arts == 2 and photos == 2


def test_options_change_the_page_count_and_labels(photo, line_art):
    book, _ = _book_with_pages(photo, line_art, language="en", include_owner_page=True, blank_backs=True, page_size="a4")
    reader = PdfReader(export.export_book_pdf(book))
    assert len(reader.pages) == 8  # every sheet followed by a blank back
    assert "This book belongs to" in reader.pages[2].extract_text()
    assert reader.pages[0].extract_text().strip() != "" and reader.pages[1].extract_text().strip() == ""
    width, height = float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)
    assert (round(width), round(height)) == (595, 842)


def test_long_captions_are_reported(photo, line_art):
    book, _ = _book_with_pages(photo, line_art)
    page = pages.load_pages(book.slug)[0]
    long_page = pages.update_page(book.slug, page.id, info="Un dato muy largo sobre el ave. " * 60)
    assert not export.caption_fits(book, long_page)
    assert [p.id for p in export.preflight(book).overflowing] == [page.id]
    export.export_book_pdf(book)  # still builds; the text is clipped to the box


def test_info_markup_bolds_labels_and_escapes():
    markup = export.info_markup("Hábitat: bosques <húmedos>\nsin etiqueta")
    assert markup == "<b>Hábitat:</b> bosques &lt;húmedos&gt;<br/>sin etiqueta"


def _embedded(reader: PdfReader) -> dict[str, bool]:
    fonts = {}
    for page in reader.pages:
        for font in page["/Resources"].get("/Font", {}).values():
            font = font.get_object()
            descriptor = font.get("/FontDescriptor")
            fonts[font["/BaseFont"]] = descriptor is not None and "/FontFile2" in descriptor.get_object()
    return fonts


def test_every_font_is_embedded(photo, line_art):
    book, _ = _book_with_pages(photo, line_art)
    fonts = _embedded(PdfReader(export.export_book_pdf(book)))
    assert fonts and all(fonts.values()), fonts


def test_copyright_page_backs_the_title_page_with_the_photo_credits(photo, line_art):
    book, _ = _book_with_pages(photo, line_art, blank_backs=True)
    book.legal = "© 2026 Ana Pérez.\nTodos los derechos reservados."
    books.save_book(book)
    toucan = pages.load_pages(book.slug)[0]
    pages.update_page(book.slug, toucan.id, credit="Bernard Gagnon, CC0")
    reader = PdfReader(export.export_book_pdf(book))
    included = export.preflight(book).included
    assert len(reader.pages) == len(export.sheets(book, included)) == 8  # the copyright page replaces a blank
    text = reader.pages[1].extract_text()
    assert "© 2026 Ana Pérez." in text and "Créditos de las fotografías" in text
    assert "Pág. 1 · Tucán pico iris: Bernard Gagnon, CC0" in text
    assert "Este libro pertenece a" in reader.pages[2].extract_text()


@pytest.mark.parametrize("owner, backs", [(True, True), (True, False), (False, True), (False, False)])
def test_sheets_match_the_built_pdf(photo, line_art, owner, backs):
    book, _ = _book_with_pages(photo, line_art, include_owner_page=owner, blank_backs=backs)
    built = len(PdfReader(export.export_book_pdf(book)).pages)
    assert built == len(export.sheets(book, export.preflight(book).included))


def test_line_art_is_upsampled_to_print_resolution(tmp_path, line_art):
    path = tmp_path / "art.png"
    lineart.clean(line_art, "6-8").image.save(path)
    box = (7.5 * 72, 9.7 * 72)  # a full Letter page inside the margins
    image = export.line_art_image(path, box)
    points_per_px = min(box[0] / image.width, box[1] / image.height)
    assert 72 / points_per_px >= export.PRINT_DPI
    assert set(np.unique(np.array(image))) <= {0, 255}
