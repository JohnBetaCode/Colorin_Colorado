from io import BytesIO

from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.core import books, export, extras, lineart, pages
from app.core.schema import Page, Version

TITLES = ["Tucán pico iris", "Palomas en la plaza", "Una sonrisa enorme", "Ñandú"]


def _book(photo, line_art, titles=TITLES, **book_fields):
    book = books.create_book("Aves del jardín", **book_fields)
    clean = lineart.clean(line_art, book.age_group).image
    for title in titles:
        page = pages.add_photo(book.slug, "foto.png", photo)
        version = Version(n=0, engine="draft", style="realistic", age_group=book.age_group, background="remove", created_at="now")
        pages.add_version(book.slug, page.id, version, line_art, clean)
        pages.update_page(book.slug, page.id, title=title, background="remove")
    return books.load_book(book.slug)


def _pages(titles):
    return [Page(id=str(i), original="x.jpg", original_name="x.jpg", title=title) for i, title in enumerate(titles)]


def test_word_list_takes_the_longest_word_of_each_title():
    assert extras.word_list(_pages(TITLES + ["Tucán", "Hipopotamomonstruoso"]), "6-8") == ["TUCAN", "PALOMAS", "SONRISA", "ÑANDU"]


def test_word_search_hides_every_word_where_it_says():
    words = ["TUCAN", "PALOMAS", "SONRISA", "ÑANDU"]
    for age in ("3-5", "6-8", "9+"):
        puzzle = extras.word_search([w for w in words if len(w) <= extras.GRID_SIZE[age]], age, "es", "seed")
        size = extras.GRID_SIZE[age]
        assert len(puzzle.grid) == size and all(len(row) == size for row in puzzle.grid)
        for word, r, c, dr, dc in puzzle.placed:
            assert "".join(puzzle.grid[r + dr * i][c + dc * i] for i in range(len(word))) == word
            assert (dr, dc) in extras.DIRECTIONS[age]
    assert extras.word_search(words, "6-8", "es", "a").grid == extras.word_search(words, "6-8", "es", "a").grid


def test_maze_has_one_path_from_entrance_to_exit():
    puzzle = extras.maze("6-8", "seed")
    assert len(puzzle.passages) == puzzle.cols * puzzle.rows - 1  # a tree: every cell reachable, no loops
    assert puzzle.solution[0] == (0, 0) and puzzle.solution[-1] == (puzzle.rows - 1, puzzle.cols - 1)
    for a, b in zip(puzzle.solution, puzzle.solution[1:]):
        assert frozenset({a, b}) in puzzle.passages


def test_dots_trace_a_silhouette_but_not_a_framed_scene(tmp_path, line_art):
    subject = tmp_path / "subject.png"
    lineart.clean(line_art, "6-8").image.save(subject)
    found = extras._dots(str(subject), 0, 24)
    assert found is not None and 6 <= len(found.points) <= 24

    scene = Image.new("L", (900, 1200), 255)
    ImageDraw.Draw(scene).rectangle((5, 5, 894, 1194), outline=0, width=12)
    framed = tmp_path / "scene.png"
    scene.save(framed)
    assert extras._dots(str(framed), 0, 24) is None


def test_extras_go_in_order_and_are_drawn(photo, line_art):
    book = _book(photo, line_art, blank_backs=True, extras=["closing", "maze", "word_search", "dots", "solutions", "diploma", "color_test"])
    included = export.preflight(book).included
    order = [s for s in export.sheets(book, included) if isinstance(s, str) and s not in ("blank", "legal")]
    assert order == ["title", "owner", "color_test", "word_search", "maze", "dots", "solutions", "diploma", "closing"]
    reader = PdfReader(export.export_book_pdf(book))
    assert len(reader.pages) == len(export.sheets(book, included))
    text = " ".join(page.extract_text() for page in reader.pages)
    for label in ("Prueba tus colores", "Sopa de letras", "Laberinto", "Une los puntos", "Soluciones", "¡Felicitaciones!", "Colorín colorado"):
        assert label in text


def test_extras_the_pages_cannot_make_are_reported(photo, line_art):
    book = _book(photo, line_art, titles=["Ave", "Ave"], extras=["word_search", "solutions"])
    report = export.preflight(book)
    assert report.extras_missing == ["word_search", "solutions"]
    assert not any(s in ("word_search", "solutions") for s in export.sheets(book, report.included))


def test_dots_use_scenes_only_when_chosen(photo, line_art):
    book = _book(photo, line_art)
    page_list = pages.load_pages(book.slug)
    for page in page_list:
        pages.update_page(book.slug, page.id, background="keep")
    page_list = pages.load_pages(book.slug)
    assert extras.dots_page(book, page_list) is None
    book.dots_page_id = page_list[1].id
    assert extras.dots_page(book, page_list).id == page_list[1].id
