import numpy as np
from PIL import Image
from pypdf import PdfReader

from app.core import books, export, extras, imaging, mosaic, pages
from app.core.schema import MOSAIC_FILLS, MosaicSettings


def _half_black(size=(400, 300)) -> Image.Image:
    """Left half black, right half white."""
    w, h = size
    pixels = np.full((h, w), 255, np.uint8)
    pixels[:, : w // 2] = 0
    return Image.fromarray(pixels).convert("RGB")


def _upper_left_black(size=400) -> Image.Image:
    """Black above the "/" diagonal of a square, white below."""
    y, x = np.indices((size, size))
    return Image.fromarray(np.where(x + y < size, 0, 255).astype(np.uint8)).convert("RGB")


def test_grid_follows_the_photo_and_its_shape():
    grid = mosaic.make_grid(_half_black(), MosaicSettings(columns=20, tones=2))
    assert grid.shape == (15, 20, 3)  # rows from the 4:3 photo
    assert (grid[:, :10, 0] == 0).all() and (grid[:, 10:, 0] == 1).all()
    assert (grid[..., 2] == mosaic.WHOLE).all()


def test_diagonal_cells_split_along_edges_only():
    photo = _upper_left_black()
    grid = mosaic.make_grid(photo, MosaicSettings(columns=8, tones=2, cells="diagonal"))
    rows, cols = np.indices(grid.shape[:2])
    edge = rows + cols == 7
    assert (grid[edge, 2] == mosaic.SLASH).all()
    assert (grid[edge, 0] == 0).all() and (grid[edge, 1] == 1).all()  # dark upper-left triangle
    assert (grid[~edge, 2] == mosaic.WHOLE).all()
    square = mosaic.make_grid(photo, MosaicSettings(columns=8, tones=2, cells="square"))
    assert (square[..., 2] == mosaic.WHOLE).all()


def test_settings_are_kept_in_range():
    settings = mosaic.normalized(MosaicSettings(cells="diagonal", columns=99, tones=9, contrast=-80))
    assert (settings.columns, settings.tones, settings.contrast) == (mosaic.MAX_COLUMNS["diagonal"], 5, -50)


def test_grid_survives_the_png_round_trip(tmp_path):
    grid = mosaic.make_grid(_upper_left_black(), MosaicSettings(columns=12, tones=3, cells="diagonal"))
    path = tmp_path / "grid.png"
    path.write_bytes(mosaic.grid_png(grid))
    assert (mosaic.load_grid(path) == grid).all()


def test_solution_is_one_bit_for_every_fill():
    grid = mosaic.make_grid(_upper_left_black(), MosaicSettings(columns=10, tones=5, cells="diagonal"))
    for fill in MOSAIC_FILLS:
        assert mosaic.render_solution(grid, MosaicSettings(columns=10, tones=5, fill=fill)).mode == "1"


def test_every_palette_has_a_pattern_per_tone_ending_in_white():
    for fill in MOSAIC_FILLS[1:]:
        for tones in range(mosaic.MIN_TONES, mosaic.MAX_TONES + 1):
            chosen = mosaic.patterns(MosaicSettings(fill=fill, tones=tones))
            assert len(chosen) == tones and chosen[0] == "solid" and chosen[-1] == "empty"
            assert len(set(chosen)) == tones


def test_white_cells_have_no_number_unless_asked():
    grid = mosaic.make_grid(_half_black(), MosaicSettings(columns=20, tones=2))
    plain = mosaic.numbered(grid, MosaicSettings(tones=2))
    assert len(plain) == 15 * 10 and {number for number, _ in plain} == {"1"}  # only the black half
    assert len(mosaic.numbered(grid, MosaicSettings(tones=2, number_white=True))) == 15 * 20


def test_settings_saved_by_the_first_version_still_load():
    old = MosaicSettings.model_validate({"symbols": "shapes", "fill": "patterns", "tones": 4})
    assert old.fill == "classic" and not old.number_white


def _mosaic_book(photo):
    book = books.create_book("Misterios del jardín")
    first = pages.add_photo(book.slug, "uno.png", photo)
    pages.update_page(book.slug, first.id, title="Tucán pico iris")
    second = pages.add_photo(book.slug, "dos.png", photo)
    pages.update_page(book.slug, second.id, mosaic=MosaicSettings(cells="diagonal", fill="geometric"))
    book = books.load_book(book.slug)
    imaging.convert_pages(book, pages.load_pages(book.slug), "mosaic")
    return book


def test_mosaic_engine_stores_the_grid_and_a_one_bit_solution(photo):
    book = _mosaic_book(photo)
    first, second = pages.load_pages(book.slug)
    assert first.is_mosaic and first.status == "converted"
    assert first.selected_version.mosaic == mosaic.default_settings(book.age_group)
    assert second.selected_version.mosaic.cells == "diagonal"  # the page's own settings
    grid = mosaic.load_grid(pages.version_path(book.slug, first.id, first.selected, raw=True))
    assert grid.shape[1] == first.selected_version.mosaic.columns
    with Image.open(pages.selected_path(book.slug, first)) as solution:
        assert solution.mode == "1"


def test_preview_matches_what_saving_stores(photo):
    book = _mosaic_book(photo)
    page = pages.load_pages(book.slug)[1]
    draft, settings = imaging.mosaic_draft(book, page)
    stored, stored_settings = export.mosaic_of(book, page)
    assert (draft == stored).all() and settings == stored_settings
    assert export.mosaic_preview(book, page, draft, settings).mode == "RGB"


def test_replace_stores_the_new_options_under_the_next_number(photo):
    book = _mosaic_book(photo)
    page = pages.update_page(book.slug, pages.load_pages(book.slug)[0].id, mosaic=MosaicSettings(columns=12, tones=2))
    page = imaging.convert_page(book, page, "mosaic", replace=page.selected)
    assert [v.n for v in page.versions] == [2] and page.selected == 2
    assert page.selected_version.mosaic.columns == 12
    assert not pages.version_path(book.slug, page.id, 1).exists()


def test_pdf_hides_the_answer_and_adds_the_solutions(photo):
    book = _mosaic_book(photo)
    included = export.preflight(book).included
    order = export.sheets(book, included)
    assert order[-1] == "mosaic_solutions:0"
    reader = PdfReader(export.export_book_pdf(book))
    assert len(reader.pages) == len(order)
    puzzle = order.index(included[0])
    text = reader.pages[puzzle].extract_text()
    assert "Misterio 1" in text and "Tucán" not in text
    assert list(reader.pages[puzzle].images) == []  # vectors only: no photo, no picture of the answer
    solutions = reader.pages[-1].extract_text()
    assert "Soluciones de los misterios" in solutions and "Misterio 1 · Tucán pico iris" in solutions


def test_mosaics_stay_out_of_the_word_search(photo):
    book = _mosaic_book(photo)
    assert extras.word_list(pages.load_pages(book.slug), book.age_group) == []
    assert extras.mosaic_solution_sheets(pages.load_pages(book.slug)) == ["mosaic_solutions:0"]
