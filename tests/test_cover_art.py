from io import BytesIO

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

from app.core import books, cover, cover_art, gemini, kdp, lineart, pages
from app.core.schema import Version


def _jpeg(size, color=(30, 140, 220)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _book(photo, line_art, n_pages=3):
    book = books.create_book("Aves del jardín", subtitle="Para colorear", dedication="Para Sofía")
    clean = lineart.clean(line_art, "6-8").image
    for i in range(n_pages):
        page = pages.add_photo(book.slug, f"ave-{i}.png", photo)
        version = Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now")
        pages.add_version(book.slug, page.id, version, line_art, clean)
        pages.update_page(book.slug, page.id, title=f"Ave {i + 1}")
    return books.load_book(book.slug)


def test_plain_cmyk_prints_grays_with_black_only():
    image = Image.fromarray(np.array([[[0, 0, 0], [128, 128, 128], [255, 0, 0], [255, 255, 255]]], dtype=np.uint8))
    cmyk = np.array(cover_art.plain_cmyk(image))[0]
    assert cmyk[0].tolist() == [0, 0, 0, 255]
    assert cmyk[1].tolist() == [0, 0, 0, 127]
    assert cmyk[2].tolist() == [0, 255, 255, 0]
    assert cmyk[3].tolist() == [0, 0, 0, 0]


def test_to_cmyk_uses_the_press_profile():
    assert cover_art.CMYK_PROFILE.exists(), "libgs-common is installed in the Docker image"
    image = Image.fromarray(np.array([[[255, 255, 255], [220, 30, 30], [0, 0, 0]]], dtype=np.uint8))
    white, red, black = (np.array(cover_art.to_cmyk(image))[0].astype(int)).tolist()
    assert sum(white) < 10  # paper stays paper
    assert red[1] > 180 and red[2] > 150 and red[0] < 60  # magenta and yellow, little cyan
    assert black[3] > 200 and sum(black) <= 0.82 * 1020  # rich black within a total ink limit


def test_uploads_are_versions_and_the_front_can_go_back_to_line_art(photo, line_art):
    book = _book(photo, line_art)
    book = cover_art.add_upload(book, _jpeg((300, 400)))
    book = cover_art.add_upload(books.load_book(book.slug), _jpeg((600, 800)))
    assert [(a.n, a.source) for a in book.cover_art] == [(1, "upload"), (2, "upload")]
    assert book.cover_art_selected == 2 and cover_art.selected_path(book).name == "v2.jpg"
    assert cover_art.art_path(book, 1).exists()
    book = cover_art.select(book, None)
    assert cover_art.selected_path(books.load_book(book.slug)) is None
    with pytest.raises(ValueError):
        cover_art.add_upload(book, b"not an image")


def test_prompts_name_the_subjects_and_keep_text_off_the_art(photo, line_art):
    book = _book(photo, line_art)
    page_list = pages.load_pages(book.slug)
    collage = cover_art.build_prompt(book, "collage", "", page_list[:2])
    assert "Ave 1, Ave 2" in collage and "Ave 3" not in collage and "No text" in collage
    text = cover_art.build_prompt(book, "text", "un zorro leyendo", [])
    assert "un zorro leyendo" in text and "Extra instructions" not in text
    theme = cover_art.build_prompt(book, "theme", "de noche", page_list)
    assert '"Aves del jardín" (Para colorear)' in theme and "Extra instructions from the author: de noche" in theme


def test_generate_sends_line_art_and_photos_of_the_collage(photo, line_art, monkeypatch):
    book = _book(photo, line_art)
    calls = {}

    def fake_generate_image(prompt, reference_images=None, aspect_ratio=None, image_size=None):
        calls.update(prompt=prompt, references=reference_images, aspect_ratio=aspect_ratio, image_size=image_size)
        return _jpeg((768, 1024), (240, 120, 30))

    monkeypatch.setattr(gemini, "generate_image", fake_generate_image)
    chosen = [p.id for p in pages.load_pages(book.slug)[:2]]
    book = cover_art.generate(book, "collage", "con sol", chosen)
    assert len(calls["references"]) == 4  # line art + photo per page
    assert (calls["aspect_ratio"], calls["image_size"]) == ("3:4", "4K")
    art = book.cover_art[-1]
    assert (art.source, art.prompt, art.page_ids) == ("collage", "con sol", chosen)

    book = cover_art.generate(book, "text", "un zorro leyendo")
    assert calls["references"] == [] and book.cover_art_selected == 2
    with pytest.raises(ValueError):
        cover_art.generate(book, "text", "  ")
    with pytest.raises(ValueError):
        cover_art.generate(book, "collage", "", [])


def test_cover_pdf_puts_the_image_on_the_front(photo, line_art):
    book = cover_art.add_upload(_book(photo, line_art), _jpeg((2700, 3500)))
    page = PdfReader(cover.export_cover_pdf(book)).pages[0]
    text = page.extract_text()
    assert "Aves del jardín" in text and "Para Sofía" in text
    images = [x.get_object() for x in page["/Resources"]["/XObject"].values()]
    photos = [i for i in images if i["/Filter"] == "/DCTDecode" or "/DCTDecode" in i["/Filter"]]
    assert len(photos) == 1 and photos[0]["/ColorSpace"] == "/DeviceCMYK"
    assert {i["/ColorSpace"] for i in images} == {"/DeviceCMYK"}


def test_review_flags_small_or_ai_cover_images(photo, line_art, monkeypatch):
    book = cover_art.add_upload(_book(photo, line_art), _jpeg((600, 800)))
    issues = {i.key: i for i in kdp.review(book).issues}
    assert issues["cover_art_low_res"].params["ppi"] < kdp.MIN_PPI
    assert "ai_disclosure" not in issues  # draft pages and an uploaded image

    monkeypatch.setattr(gemini, "generate_image", lambda *args, **kwargs: _jpeg((3072, 4096)))
    book = cover_art.generate(book, "theme")
    issues = {i.key for i in kdp.review(book).issues}
    assert "ai_disclosure" in issues and "cover_art_low_res" not in issues


def test_listing_images_are_made_from_the_books_pdfs(photo, line_art):
    import zipfile

    from app.core import export, marketing

    book = _book(photo, line_art, n_pages=4)
    path = marketing.export_listing_images(book, export.preflight(book).included)
    with zipfile.ZipFile(path) as archive:
        sizes = {name: Image.open(BytesIO(archive.read(name))).size for name in archive.namelist()}
    assert sizes["mockup.jpg"] == (2000, 2000) and sizes["inside.jpg"] == (2400, 1600)
    assert sizes["front.jpg"][1] == marketing.FRONT_HEIGHT
    assert not list(export.exports_dir(book).glob("*.pdf"))  # the PDFs were temporary
