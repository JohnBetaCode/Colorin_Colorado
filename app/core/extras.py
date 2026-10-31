"""Extra pages of a book: a color test, activities with the book's subjects, solutions,
a diploma and a closing page.

Activities are generated, never drawn by the AI: a word search with one word from each
page title, a maze, and a connect-the-dots made from a coloring page's silhouette (its
outline turns into numbered dots, the details inside stay). Sizes follow the age group,
and every random choice is seeded with the book's id, so a book always exports the same
puzzles. ``export`` decides where each page goes; this module generates and draws them.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from app.core import i18n, pages
from app.core.schema import EXTRAS, Book, Page

if TYPE_CHECKING:
    from app.core.export import Fonts

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5b6470")
ACTIVITIES = ("word_search", "maze", "dots")

Box = tuple[float, float, float, float]

# --- Word search ------------------------------------------------------------------

GRID_SIZE = {"3-5": 8, "6-8": 11, "9+": 14}
DIRECTIONS = {
    "3-5": [(0, 1), (1, 0)],
    "6-8": [(0, 1), (1, 0), (1, 1)],
    "9+": [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (-1, -1), (1, -1)],
}
MIN_WORDS = 3
MAX_WORDS = 12
ALPHABET = {"es": "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ", "en": "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


@dataclass
class WordSearch:
    grid: list[list[str]]
    placed: list[tuple[str, int, int, int, int]]  # word, row, col, d_row, d_col


def _plain_letters(word: str) -> str:
    """Uppercase without accents, keeping Ñ."""
    word = word.upper().replace("Ñ", "\0")
    word = "".join(ch for ch in unicodedata.normalize("NFD", word) if not unicodedata.combining(ch))
    return word.replace("\0", "Ñ")


def word_list(page_list: list[Page], age_group: str) -> list[str]:
    """One word per page: the longest word of its title, if it fits the grid."""
    size = GRID_SIZE[age_group]
    words: list[str] = []
    for page in page_list:
        candidates = re.findall(r"[^\W\d_]+", page.title)
        if not candidates:
            continue
        word = _plain_letters(max(candidates, key=len))
        if 3 <= len(word) <= size and word not in words:
            words.append(word)
    return words[:MAX_WORDS]


def word_search(words: list[str], age_group: str, language: str, seed: str) -> WordSearch:
    size = GRID_SIZE[age_group]
    rng = random.Random(f"{seed}-words")
    grid = [["" for _ in range(size)] for _ in range(size)]
    placed = []
    for word in sorted(words, key=len, reverse=True):
        for _ in range(400):
            dr, dc = rng.choice(DIRECTIONS[age_group])
            row, col = rng.randrange(size), rng.randrange(size)
            cells = [(row + dr * i, col + dc * i) for i in range(len(word))]
            if all(0 <= r < size and 0 <= c < size and grid[r][c] in ("", word[i]) for i, (r, c) in enumerate(cells)):
                for i, (r, c) in enumerate(cells):
                    grid[r][c] = word[i]
                placed.append((word, row, col, dr, dc))
                break
    alphabet = ALPHABET.get(language, ALPHABET["en"])
    for row in grid:
        for c, letter in enumerate(row):
            row[c] = letter or rng.choice(alphabet)
    return WordSearch(grid, sorted(placed, key=lambda item: words.index(item[0])))


# --- Maze ------------------------------------------------------------------------

MAZE_SIZE = {"3-5": (6, 8), "6-8": (10, 13), "9+": (16, 21)}  # columns, rows


@dataclass
class Maze:
    cols: int
    rows: int
    passages: set[frozenset[tuple[int, int]]]
    solution: list[tuple[int, int]]  # cells (row, col) from the entrance to the exit


def maze(age_group: str, seed: str) -> Maze:
    """A perfect maze (one path between any two cells) by depth-first carving."""
    cols, rows = MAZE_SIZE[age_group]
    rng = random.Random(f"{seed}-maze")
    passages: set[frozenset[tuple[int, int]]] = set()
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        r, c = stack[-1]
        options = [
            (r + dr, c + dc)
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0))
            if 0 <= r + dr < rows and 0 <= c + dc < cols and (r + dr, c + dc) not in visited
        ]
        if not options:
            stack.pop()
            continue
        nxt = rng.choice(options)
        passages.add(frozenset({(r, c), nxt}))
        visited.add(nxt)
        stack.append(nxt)
    # The path from the entrance (top left) to the exit (bottom right).
    goal = (rows - 1, cols - 1)
    came_from = {(0, 0): None}
    queue = deque([(0, 0)])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            break
        r, c = cell
        for nxt in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nxt not in came_from and frozenset({cell, nxt}) in passages:
                came_from[nxt] = cell
                queue.append(nxt)
    path, cell = [], goal
    while cell is not None:
        path.append(cell)
        cell = came_from[cell]
    return Maze(cols, rows, passages, path[::-1])


# --- Connect the dots ---------------------------------------------------------------

DOT_COUNT = {"3-5": 12, "6-8": 24, "9+": 40}


@dataclass
class Dots:
    image: Image.Image  # the drawing with its outline erased ("L", 0/255)
    points: list[tuple[float, float]]  # in image pixels, in drawing order


@lru_cache(maxsize=8)
def _dots(path: str, mtime: float, count: int) -> Dots | None:
    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    h, w = gray.shape
    lines = (gray < 128).astype(np.uint8) * 255
    closed = cv2.dilate(lines, np.ones((5, 5), np.uint8))
    # Everything the white background cannot reach from the border is the subject.
    padded = cv2.copyMakeBorder(255 - closed, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(padded, mask, (0, 0), 0)
    shape = (padded[1:-1, 1:-1] > 0).astype(np.uint8) * 255 | closed
    # Smooth the silhouette: thin spikes (grass, texture strokes) and narrow notches would
    # send the dots back and forth.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(15, w // 35),) * 2)
    shape = cv2.morphologyEx(cv2.morphologyEx(shape, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(shape, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    outline = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(outline)
    # A scene drawn to the edges has no silhouette; a speck is not a subject.
    if not 0.05 * w * h < area < 0.8 * w * h:
        return None
    # Dots evenly spaced along the outline, clockwise from the topmost point.
    ring = outline[:, 0, :].astype(float)
    steps = np.hypot(*np.diff(np.vstack([ring, ring[:1]]), axis=0).T)
    position = np.concatenate([[0], np.cumsum(steps)])
    targets = np.linspace(0, position[-1], count, endpoint=False)
    indices = np.searchsorted(position, targets).clip(0, len(ring) - 1)
    points = [tuple(ring[i]) for i in indices]
    start = min(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    points = points[start:] + points[:start]
    erased = gray.copy()
    cv2.drawContours(erased, [outline], -1, 255, thickness=max(11, w // 50))
    image = Image.fromarray(np.where(erased < 128, 0, 255).astype(np.uint8))
    return Dots(image, points)


def dots_for(book: Book, page: Page) -> Dots | None:
    path = pages.selected_path(book.slug, page)
    if path is None:
        return None
    return _dots(str(path), path.stat().st_mtime, DOT_COUNT[book.age_group])


def dots_page(book: Book, page_list: list[Page]) -> Page | None:
    """The page the connect-the-dots is made from: the chosen one, else the first drawing
    with no background that works.

    Only a subject alone has a clean silhouette: in a scene the outline runs through the
    background and the dots make no sense, so scenes are used only when chosen.
    """
    chosen = [p for p in page_list if p.id == book.dots_page_id]
    alone = [p for p in page_list if p.id != book.dots_page_id and (p.background or book.background) == "remove"]
    return next((p for p in chosen + alone if dots_for(book, p) is not None), None)


# --- Which extras can be drawn ------------------------------------------------------


def available(book: Book, page_list: list[Page]) -> list[str]:
    """The book's extras that can be drawn with its pages, in book order."""
    activities = {
        "word_search": len(word_list(page_list, book.age_group)) >= MIN_WORDS,
        "maze": True,
        "dots": dots_page(book, page_list) is not None,
    }
    result = []
    for extra in (e for e in EXTRAS if e in book.extras):
        if extra in activities and not activities[extra]:
            continue
        if extra == "solutions" and not any(a in book.extras and activities[a] for a in ACTIVITIES):
            continue
        result.append(extra)
    return result


# --- Drawing ----------------------------------------------------------------------


def _label(key: str, book: Book, **params) -> str:
    """The label in the book's languages: one line each, joined with " / "."""
    return " / ".join(i18n.t_all(key, book.languages, **params))


def _heading(c: Canvas, book: Book, fonts: Fonts, box: Box, title_key: str, hint_key: str | None = None, **params) -> float:
    """Title and instructions at the top of ``box`` (second language below, muted); returns the y below them."""
    x, y, w, h = box
    title, *other_titles = i18n.t_all(title_key, book.languages)
    hints = i18n.t_all(hint_key, book.languages, **params) if hint_key else []
    styles = [ParagraphStyle("extra_title", fontName=fonts.bold, fontSize=28, leading=34, alignment=TA_CENTER, textColor=INK)]
    styles += [ParagraphStyle("extra_title2", fontName=fonts.bold, fontSize=18, leading=22, alignment=TA_CENTER, textColor=MUTED)] * len(other_titles)
    styles += [ParagraphStyle("extra_hint", fontName=fonts.italic, fontSize=14, leading=18, alignment=TA_CENTER, textColor=MUTED)] * len(hints)
    top = y + h
    for text, style in zip([title, *other_titles, *hints], styles):
        paragraph = Paragraph(escape(text), style)
        _, ph = paragraph.wrap(w, h)
        top -= ph + (0 if top == y + h else 4)
        paragraph.drawOn(c, x, top)
    return top - 0.3 * inch


def draw_color_test(c: Canvas, book: Book, fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    bottom = _heading(c, book, fonts, box, "pdf.color_test", "pdf.color_test_hint")
    cols, rows, gap = 4, 6, 0.22 * inch
    cell_w = (w - gap * (cols - 1)) / cols
    cell_h = (bottom - y - gap * (rows - 1)) / rows
    c.setStrokeColor(INK)
    for r in range(rows):
        for col in range(cols):
            cx, cy = x + col * (cell_w + gap), bottom - (r + 1) * cell_h - r * gap
            c.setLineWidth(1.5)
            c.roundRect(cx, cy + 0.28 * inch, cell_w, cell_h - 0.28 * inch, 8)
            c.setLineWidth(0.6)
            c.line(cx + 6, cy + 0.08 * inch, cx + cell_w - 6, cy + 0.08 * inch)


def _word_grid(c: Canvas, puzzle: WordSearch, fonts: Fonts, box: Box, solved: bool) -> None:
    """The letter grid centered in ``box``; with ``solved``, each word circled."""
    x, y, w, h = box
    size = len(puzzle.grid)
    cell = min(w, h) / size
    left, top = x + (w - cell * size) / 2, y + (h + cell * size) / 2
    c.setFillColor(INK)
    c.setFont(fonts.bold, cell * 0.55)
    for r, row in enumerate(puzzle.grid):
        for col, letter in enumerate(row):
            c.drawCentredString(left + (col + 0.5) * cell, top - (r + 0.5) * cell - cell * 0.2, letter)
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    c.roundRect(left - cell * 0.2, top - cell * (size + 0.2), cell * (size + 0.4), cell * (size + 0.4), 8)
    if solved:
        c.setLineWidth(max(0.8, cell * 0.06))
        for word, r, col, dr, dc in puzzle.placed:
            x0, y0 = left + (col + 0.5) * cell, top - (r + 0.5) * cell
            x1, y1 = left + (col + dc * (len(word) - 1) + 0.5) * cell, top - (r + dr * (len(word) - 1) + 0.5) * cell
            c.saveState()
            c.translate(x0, y0)
            angle = np.degrees(np.arctan2(y1 - y0, x1 - x0))
            length = float(np.hypot(x1 - x0, y1 - y0))
            c.rotate(angle)
            c.roundRect(-cell * 0.4, -cell * 0.4, length + cell * 0.8, cell * 0.8, cell * 0.4)
            c.restoreState()


def draw_word_search(c: Canvas, book: Book, page_list: list[Page], fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    words = word_list(page_list, book.age_group)
    puzzle = word_search(words, book.age_group, book.language, book.id)
    bottom = _heading(c, book, fonts, box, "pdf.word_search", "pdf.word_search_hint")
    list_h = 0.42 * inch * ((len(puzzle.placed) + 2) // 3)
    _word_grid(c, puzzle, fonts, (x, y + list_h + 0.2 * inch, w, bottom - y - list_h - 0.2 * inch), solved=False)
    c.setFillColor(INK)
    c.setFont(fonts.regular, 15)
    for i, (word, *_rest) in enumerate(puzzle.placed):
        col, row = i % 3, i // 3
        c.drawString(x + w * (0.08 + col * 0.33), y + list_h - (row + 1) * 0.42 * inch + 0.12 * inch, word)


def _maze_lines(c: Canvas, puzzle: Maze, box: Box, solved: bool, line_width: float) -> None:
    x, y, w, h = box
    cell = min(w / puzzle.cols, h / puzzle.rows)
    left, top = x + (w - cell * puzzle.cols) / 2, y + (h + cell * puzzle.rows) / 2
    c.setStrokeColor(INK)
    c.setLineWidth(line_width)
    c.setLineCap(1)
    path = c.beginPath()
    for r in range(puzzle.rows):
        for col in range(puzzle.cols):
            cx, cy = left + col * cell, top - r * cell
            if r == 0 and col != 0 or r > 0 and frozenset({(r, col), (r - 1, col)}) not in puzzle.passages:
                path.moveTo(cx, cy)
                path.lineTo(cx + cell, cy)
            if col == 0 or frozenset({(r, col), (r, col - 1)}) not in puzzle.passages:
                path.moveTo(cx, cy)
                path.lineTo(cx, cy - cell)
    bottom = top - puzzle.rows * cell
    path.moveTo(left, bottom)
    path.lineTo(left + (puzzle.cols - 1) * cell, bottom)  # the last cell's floor is the exit
    path.moveTo(left + puzzle.cols * cell, top)
    path.lineTo(left + puzzle.cols * cell, bottom)
    c.drawPath(path, stroke=1, fill=0)
    if solved:
        c.setDash(line_width * 2, line_width * 2)
        trail = c.beginPath()
        trail.moveTo(left + 0.5 * cell, top + 0.5 * cell)
        for r, col in puzzle.solution:
            trail.lineTo(left + (col + 0.5) * cell, top - (r + 0.5) * cell)
        trail.lineTo(left + (puzzle.cols - 0.5) * cell, bottom - 0.5 * cell)
        c.drawPath(trail, stroke=1, fill=0)
        c.setDash()


def draw_maze(c: Canvas, book: Book, fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    puzzle = maze(book.age_group, book.id)
    bottom = _heading(c, book, fonts, box, "pdf.maze", "pdf.maze_hint")
    label_h = 0.35 * inch
    area = (x, y + label_h, w, bottom - y - 2 * label_h)
    _maze_lines(c, puzzle, area, solved=False, line_width={"3-5": 4, "6-8": 3, "9+": 2}[book.age_group])
    cell = min(area[2] / puzzle.cols, area[3] / puzzle.rows)
    left = x + (w - cell * puzzle.cols) / 2
    c.setFillColor(INK)
    c.setFont(fonts.bold, 14)
    c.drawString(left, bottom - label_h + 0.08 * inch, _label("pdf.maze_start", book))
    c.drawRightString(left + cell * puzzle.cols, y + 0.05 * inch, _label("pdf.maze_end", book))


def _draw_gray(c: Canvas, image: Image.Image, box: Box) -> tuple[float, float, float]:
    """Draw a grayscale image fitted in ``box``; returns its left, bottom and scale."""
    x, y, w, h = box
    scale = min(w / image.width, h / image.height)
    left, bottom = x + (w - image.width * scale) / 2, y + (h - image.height * scale) / 2
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    c.drawImage(ImageReader(buffer), left, bottom, image.width * scale, image.height * scale)
    return left, bottom, scale


def draw_dots(c: Canvas, book: Book, page_list: list[Page], fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    page = dots_page(book, page_list)
    puzzle = dots_for(book, page)
    bottom = _heading(c, book, fonts, box, "pdf.dots", "pdf.dots_hint", count=len(puzzle.points))
    left, base, scale = _draw_gray(c, puzzle.image, (x, y, w, bottom - y))
    height = puzzle.image.height
    cx = sum(p[0] for p in puzzle.points) / len(puzzle.points)
    cy = sum(p[1] for p in puzzle.points) / len(puzzle.points)
    size = {"3-5": 14, "6-8": 11, "9+": 9}[book.age_group]
    c.setFillColor(INK)
    c.setFont(fonts.bold, size)
    for n, (px, py) in enumerate(puzzle.points, start=1):
        dx, dy = px - cx, py - cy
        norm = max(float(np.hypot(dx, dy)), 1.0)
        X, Y = left + px * scale, base + (height - py) * scale
        c.circle(X, Y, 2.4, stroke=0, fill=1)
        c.drawCentredString(X + dx / norm * size, Y - dy / norm * size - size * 0.35, str(n))


def draw_solutions(c: Canvas, book: Book, page_list: list[Page], fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    bottom = _heading(c, book, fonts, box, "pdf.solutions")
    shown = [a for a in available(book, page_list) if a in ACTIVITIES]
    gap = 0.3 * inch
    cell_h = (bottom - y - gap * (len(shown) - 1)) / max(len(shown), 1)
    for i, activity in enumerate(shown):
        top = bottom - i * (cell_h + gap)
        c.setFillColor(MUTED)
        c.setFont(fonts.bold, 13)
        c.drawString(x, top - 13, _label(f"pdf.{activity}", book))
        area = (x, top - cell_h, w, cell_h - 22)
        if activity == "word_search":
            words = word_list(page_list, book.age_group)
            _word_grid(c, word_search(words, book.age_group, book.language, book.id), fonts, area, solved=True)
        elif activity == "maze":
            _maze_lines(c, maze(book.age_group, book.id), area, solved=True, line_width=1.2)
        else:
            path = pages.selected_path(book.slug, dots_page(book, page_list))
            with Image.open(path) as image:
                _draw_gray(c, image.convert("L"), area)


def _frame(c: Canvas, box: Box) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(2)
    c.roundRect(*box, 18)


def _star(c: Canvas, cx: float, cy: float, r: float) -> None:
    path = c.beginPath()
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        angle = np.pi / 2 + i * np.pi / 5
        point = (cx + radius * np.cos(angle), cy + radius * np.sin(angle))
        if i == 0:
            path.moveTo(*point)
        else:
            path.lineTo(*point)
    path.close()
    c.drawPath(path, stroke=1, fill=0)


def draw_diploma(c: Canvas, book: Book, fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    _frame(c, box)
    c.setLineWidth(1)
    c.roundRect(x + 10, y + 10, w - 20, h - 20, 12)
    for i in range(5):
        _star(c, x + w * (0.3 + i * 0.1), y + h - 1.1 * inch, 13 if i == 2 else 9)
    style = lambda size, font=fonts.bold, color=INK: ParagraphStyle(  # noqa: E731
        f"diploma{size}", fontName=font, fontSize=size, leading=size * 1.25, alignment=TA_CENTER, textColor=color
    )
    inner = w - 1.2 * inch
    top = y + h - 1.7 * inch
    for text, paragraph_style, space in (
        (_label("pdf.diploma_title", book), style(38), 0),
        (_label("pdf.diploma_for", book), style(16, fonts.italic, MUTED), 0.5 * inch),
    ):
        paragraph = Paragraph(escape(text), paragraph_style)
        _, ph = paragraph.wrap(inner, h)
        top -= space + ph
        paragraph.drawOn(c, x + 0.6 * inch, top)
    top -= 0.9 * inch
    c.setLineWidth(1.5)
    c.line(x + w * 0.15, top, x + w * 0.85, top)
    paragraph = Paragraph(escape(_label("pdf.diploma_reason", book, title=book.title)), style(18, fonts.regular))
    _, ph = paragraph.wrap(inner, h)
    top -= 0.5 * inch + ph
    paragraph.drawOn(c, x + 0.6 * inch, top)
    c.setFont(fonts.regular, 12)
    c.setFillColor(MUTED)
    for i, key in enumerate(("pdf.diploma_date", "pdf.diploma_signature")):
        lx = x + w * (0.1 + i * 0.47)
        c.line(lx, y + 1.3 * inch, lx + w * 0.36, y + 1.3 * inch)
        c.drawCentredString(lx + w * 0.18, y + 1.05 * inch, _label(key, book))


def draw_closing(c: Canvas, book: Book, fonts: Fonts, box: Box) -> None:
    x, y, w, h = box
    style = ParagraphStyle("closing", fontName=fonts.bold, fontSize=30, leading=38, alignment=TA_CENTER, textColor=INK)
    paragraph = Paragraph("<br/><br/>".join(escape(t) for t in i18n.t_all("pdf.closing", book.languages)), style)
    _, ph = paragraph.wrap(w - inch, h)
    middle = y + h * 0.55
    paragraph.drawOn(c, x + 0.5 * inch, middle - ph / 2)
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    for i in range(3):
        _star(c, x + w * (0.4 + i * 0.1), middle - ph / 2 - 0.7 * inch, 11)


def draw(kind: str, c: Canvas, book: Book, page_list: list[Page], fonts: Fonts, box: Box) -> None:
    """Draw one extra page in the content ``box`` of the page (without ``showPage``)."""
    if kind == "color_test":
        draw_color_test(c, book, fonts, box)
    elif kind == "word_search":
        draw_word_search(c, book, page_list, fonts, box)
    elif kind == "maze":
        draw_maze(c, book, fonts, box)
    elif kind == "dots":
        draw_dots(c, book, page_list, fonts, box)
    elif kind == "solutions":
        draw_solutions(c, book, page_list, fonts, box)
    elif kind == "diploma":
        draw_diploma(c, book, fonts, box)
    elif kind == "closing":
        draw_closing(c, book, fonts, box)

