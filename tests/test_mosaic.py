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
    for fill in mosaic.PALETTES:
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


# --- One pen ---------------------------------------------------------------------


def _gradient(size=(480, 240)) -> Image.Image:
    """Black on the left to white on the right."""
    w, h = size
    return Image.fromarray(np.tile(np.linspace(0, 255, w), (h, 1)).astype(np.uint8)).convert("RGB")


def test_pen_marks_get_darker_one_by_one():
    ink = mosaic.pen_ink()
    assert len(ink) == mosaic.PEN_TONES == 6 and ink[-1] == 0
    assert ink[0] > ink[1] > ink[2] > ink[3] > 0 and ink[3] == ink[4]  # "\" and "/" share their ink


def test_pen_settings_are_always_six_marks_on_squares():
    settings = mosaic.normalized(MosaicSettings(fill="pen", cells="diagonal", tones=3, columns=500))
    assert (settings.tones, settings.cells, settings.columns) == (6, "square", mosaic.PEN_MAX_COLUMNS)


def test_pen_grid_follows_the_tones_with_one_mark_per_cell():
    grid = mosaic.make_grid(_gradient(), MosaicSettings(fill="pen", columns=24, contrast=0))
    assert set(np.unique(grid[..., 0])) <= set(range(6)) and (grid[..., 2] == mosaic.WHOLE).all()
    ink = np.array(mosaic.pen_ink())[grid[..., 0]]
    thirds = [ink[:, i * 8 : (i + 1) * 8].mean() for i in range(3)]
    assert thirds[0] > thirds[1] > thirds[2]  # more ink where the photo is darker
    assert (grid[:, -2:, 0] == 5).all()  # white stays empty


def test_single_strokes_follow_the_edge_they_sit_on():
    k, size = mosaic.SAMPLES, 24
    y, x = np.indices((size * k, size * k))
    for rising, stroke, other in ((True, 4, 3), (False, 3, 4)):
        d = (x + y - size * k) if rising else (x - y)
        value = np.where(np.abs(d) < size * k * 0.12, 0.7, 1.0).astype(np.float32)  # a light band
        tones = mosaic._pen_grid(value, size, size, k)[..., 0]
        assert (tones == stroke).sum() > 3 * max((tones == other).sum(), 1), (rising, np.bincount(tones.ravel()))


def test_pen_keeps_white_paper_white():
    pixels = np.full((300, 400), 255, np.uint8)
    pixels[100:200, 150:250] = 40  # a dark object on white
    grid = mosaic.make_grid(Image.fromarray(pixels).convert("RGB"), MosaicSettings(fill="pen", columns=40))
    tones = grid[..., 0]
    assert (tones[:5] == 5).all() and (tones[:, :10] == 5).all()
    assert (tones[13:17, 17:23] <= 1).all()  # the object: heavy marks


def test_pen_mosaics_print_dots_numbers_and_their_marks(photo):
    book = books.create_book("Misterios del jardín")
    page = pages.add_photo(book.slug, "uno.png", photo)
    pages.update_page(book.slug, page.id, mosaic=MosaicSettings(fill="pen", columns=30))
    imaging.convert_pages(book, pages.load_pages(book.slug), "mosaic")
    stored = pages.load_pages(book.slug)[0]
    assert mosaic.render_solution(*export.mosaic_of(book, stored)).mode == "1"
    reader = PdfReader(export.export_book_pdf(book))
    text = " ".join(p.extract_text() for p in reader.pages)
    assert "Equis" in text and "Estrella" in text and "Cuadro relleno" in text
    rows, cols = mosaic.load_grid(pages.version_path(book.slug, stored.id, stored.selected, raw=True)).shape[:2]
    assert 3 < export.mosaic_cell_mm(book, rows, cols) < 8


# --- Background removal ---------------------------------------------------------------


def test_the_subject_mask_is_computed_once_and_cached(photo, monkeypatch):
    from app.core import background

    calls = []

    def fake_predict(image):
        calls.append(image.size)
        w, h = image.size
        out = np.zeros((h, w), np.float32)
        out[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4] = 1  # a subject in the middle
        return out

    monkeypatch.setattr(background, "available", lambda: True)
    monkeypatch.setattr(background, "_predict", fake_predict)
    book = books.create_book("Misterios del jardín")
    page = pages.add_photo(book.slug, "uno.png", photo)
    settings = MosaicSettings(fill="pen", remove_background=True, columns=20)
    first = background.subject_mask(book.slug, page, settings)
    second = background.subject_mask(book.slug, page, settings)
    assert len(calls) == 1 and (first == second).all() and first[first.shape[0] // 2, first.shape[1] // 2]
    assert (books.book_path(book.slug) / "masks").is_dir()

    photo_size = pages.cropped_photo(book.slug, page).size
    grid = mosaic.make_grid(pages.cropped_photo(book.slug, page), settings, first)
    rows, cols = grid.shape[:2]
    # The grid frames the subject: half the photo each way, plus a small margin.
    assert abs(rows / cols - photo_size[1] / photo_size[0]) < 0.15 and cols == 20


def test_background_errors_are_clear_when_the_model_is_missing(photo, monkeypatch):
    import pytest

    from app.core import background

    monkeypatch.setattr(background, "available", lambda: False)
    book = books.create_book("Misterios del jardín")
    page = pages.add_photo(book.slug, "uno.png", photo)
    with pytest.raises(background.BackgroundError):
        background.subject_mask(book.slug, page, MosaicSettings(remove_background=True))
