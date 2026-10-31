import pytest
from pypdf import PdfReader

from app.core import books, cover, export, kdp, lineart, pages
from app.core.schema import Version


def _book(photo, line_art, n_pages, credit="", license="unknown", **book_fields):
    book = books.create_book("Aves del jardín", subtitle="Para colorear", **book_fields)
    clean = lineart.clean(line_art, "6-8").image
    for i in range(n_pages):
        page = pages.add_photo(book.slug, f"ave-{i}.png", photo)
        version = Version(n=0, engine="draft", style="realistic", age_group="6-8", background="simplify", created_at="now")
        pages.add_version(book.slug, page.id, version, line_art, clean)
        pages.update_page(book.slug, page.id, title=f"Ave {i + 1}", credit=credit, license=license, status="approved")
    return books.load_book(book.slug)


def _issues(review: kdp.Review) -> dict[str, str]:
    return {issue.key: issue.level for issue in review.issues}


def test_spine_and_cover_size():
    assert kdp.spine_width(104, "black") == pytest.approx(0.234208)
    assert kdp.spine_width(103, "black") == kdp.spine_width(104, "black")  # printed with a blank last page
    width, height = kdp.cover_size(104, "premium_color", "letter")
    assert width == pytest.approx(0.125 + 8.5 + 104 * 0.002347 + 8.5 + 0.125)
    assert height == pytest.approx(11.25)


def test_printing_cost_by_ink_and_page_count():
    assert kdp.printing_cost(104, "black") == 2.84  # flat below 110 pages
    assert kdp.printing_cost(200, "black") == 4.40
    assert kdp.printing_cost(40, "premium_color") == 4.20
    assert kdp.printing_cost(104, "premium_color") == 9.32
    assert kdp.printing_cost(104, "standard_color") == 5.18
    assert kdp.printing_cost(70, "standard_color") is None  # standard color starts at 72 pages
    assert kdp.printing_cost(22, "black") is None


def test_royalty_and_minimum_price():
    assert kdp.royalty_rate(9.98) == 0.50 and kdp.royalty_rate(9.99) == 0.60
    assert kdp.royalty(9.99, 2.84) == 3.15
    assert kdp.royalty(8.99, 2.84) == 1.66
    assert kdp.min_price(2.84) == 5.68  # cost / 50%
    assert kdp.min_price(9.32) == 15.54  # cost / 60%, since cost / 50% would be above the threshold


def test_review_of_a_small_unfinished_book(photo, line_art):
    review = kdp.review(_book(photo, line_art, 3))
    assert review.pages == 5  # title, owner page, three coloring pages
    issues = _issues(review)
    assert issues["too_few_pages_no_backs"] == "error"
    assert issues["no_blank_backs"] == issues["no_legal"] == issues["license_unknown"] == "warning"
    assert "ai_disclosure" not in issues  # draft pages only
    assert not review.ready


def test_review_of_a_book_ready_for_kdp(photo, line_art):
    book = _book(photo, line_art, 10, credit="Foto propia", license="own", blank_backs=True, legal="© 2026 Ana. Todos los derechos reservados.")
    review = kdp.review(book)
    assert review.pages == 24  # title, copyright page, owner page + blank, 10 sheets + blank backs
    assert review.cost == 2.84 and review.royalty == 3.15
    assert review.ready
    assert set(_issues(review)) == {"photos_gray"}


def test_review_flags_inks_kdp_does_not_offer(photo, line_art):
    book = _book(photo, line_art, 10, blank_backs=True, kdp_ink="standard_color")
    assert _issues(kdp.review(book))["too_few_pages"] == "error"  # 72 pages minimum
    book.page_size = "a4"
    assert _issues(kdp.review(book))["ink_not_offered"] == "error"


def test_cover_pdf_matches_the_interior(photo, line_art):
    book = _book(photo, line_art, 5, blank_backs=True, back_text="Cinco aves para colorear.", kdp_ink="premium_color")
    pages_in_interior = len(PdfReader(export.export_book_pdf(book)).pages)
    path = cover.export_cover_pdf(book)
    assert cover.cover_pages(path) == pages_in_interior

    page = PdfReader(path).pages[0]
    width, height = kdp.cover_size(pages_in_interior, "premium_color", "letter")
    assert float(page.mediabox.width) == pytest.approx(width * 72, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(height * 72, abs=0.01)
    text = page.extract_text()
    assert "Aves del jardín" in text and "Cinco aves para colorear." in text

    assert page.get_contents().get_data().count(b" Do") == 1 + 4  # front cover art and four pages on the back
    images = [x.get_object() for x in page["/Resources"]["/XObject"].values()]
    assert {image["/ColorSpace"] for image in images} == {"/DeviceCMYK"}


def test_spine_title_only_on_thick_books(photo, line_art):
    thin = _book(photo, line_art, 2)
    assert PdfReader(cover.export_cover_pdf(thin)).pages[0].extract_text().count("Aves del jardín") == 1
    thick = _book(photo, line_art, 50, blank_backs=True)
    text = PdfReader(cover.export_cover_pdf(thick)).pages[0].extract_text()
    assert text.count("Aves del jardín") == 2  # front cover and spine


def test_review_blocks_photos_that_cannot_be_sold(photo, line_art):
    book = _book(photo, line_art, 2, license="cc_by")
    page_list = pages.load_pages(book.slug)
    pages.update_page(book.slug, page_list[1].id, license="non_commercial")
    issues = {i.key: i for i in kdp.review(book).issues}
    assert issues["license_not_for_sale"].level == "error" and issues["license_not_for_sale"].params["names"] == "Ave 2"
    assert issues["missing_credits"].params["names"] == "Ave 1"  # CC BY needs its credit
    pages.update_page(book.slug, page_list[1].id, license="cc_by_sa", credit="Ana, CC BY-SA 4.0")
    issues = {i.key: i for i in kdp.review(book).issues}
    assert "license_not_for_sale" not in issues and issues["share_alike"].params["names"] == "Ave 2"
