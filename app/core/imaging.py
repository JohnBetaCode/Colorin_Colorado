"""Coloring-page generation.

The uploaded photo is always the reference image: the model redraws that exact
subject as line art, it never invents one from text. Whatever comes back goes
through ``lineart.clean`` before anyone sees it. Mystery mosaics (``mosaic.py``) are
the exception: they are a grid of tones, not line art.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.core import gemini, lineart, mosaic, pages, usage
from app.core.books import now
from app.core.schema import Book, Engine, MosaicSettings, Page, Version

AI_PAGE_COST_USD = 0.14  # estimate shown before converting many pages at once
BATCH_WORKERS = 3  # AI conversions running at the same time in convert_pages

STYLE_PROMPTS = {
    "realistic": (
        "realistic field-guide line drawing traced from the photo: accurate anatomy or "
        "architecture and proportions, the characteristic markings and patterns drawn as "
        "outlined regions, clean confident contour lines"
    ),
    "cartoon": (
        "friendly children's cartoon: simplified rounded shapes, slightly bigger head and "
        "expressive eyes when the subject has a face, smooth even outlines, fewer and bigger "
        "areas to color; still unmistakably the same subject as the photo"
    ),
    "kawaii": (
        "kawaii: very cute, round and chubby shapes, a big head with large shiny eyes and a small "
        "smile when the subject has a face, soft rounded outlines, and a few tiny decorations "
        "around it (little stars, hearts or sparkles) drawn as closed outlines; still "
        "unmistakably the same subject as the photo"
    ),
    "mandala": (
        "pattern art: the subject's silhouette and main parts stay accurate to the photo, and "
        "every large area inside them is filled with decorative patterns (scales, petals, "
        "swirls, circles, small geometric shapes), each pattern piece a closed outlined area to "
        "color; the background, if any, is plain or a simple pattern"
    ),
}

AGE_PROMPTS = {
    "3-5": {
        "detail": (
            "VERY SIMPLE, for ages 3 to 5: only the main silhouette and a few big inner shapes "
            "(roughly 10 to 20 areas to color), no small details, no textures; any background is "
            "at most a few big simple shapes, even in a busy scene"
        ),
        "lines": "VERY THICK, like a marker: about 1/80 of the image width, the same everywhere",
    },
    "6-8": {
        "detail": (
            "SIMPLE, for ages 6 to 8: the main features and the few details that make the "
            "subject recognizable (roughly 25 to 60 areas to color), mostly large areas"
        ),
        "lines": "thick and even: about 1/130 of the image width",
    },
    "9+": {
        "detail": (
            "DETAILED, for ages 9 and up: full detail, textures such as feathers, fur, stones or "
            "leaves drawn as many small outlined areas"
        ),
        "lines": "medium: about 1/200 of the image width, slightly finer for inner details",
    },
    "adult": {
        "detail": (
            "INTRICATE, for teens and adults who color with fine pens: very detailed, hundreds of "
            "small areas, every texture (feathers, fur, stones, leaves, fabric) drawn as many small "
            "outlined areas"
        ),
        "lines": "fine: about 1/300 of the image width, even finer for small inner details",
    },
}

BACKGROUND_PROMPTS = {
    "keep": (
        "keep the setting and the framing of the photo, redrawn as outlined shapes to color at "
        "the detail level above"
    ),
    "simplify": (
        "replace the background with a few simple outlined elements that suggest the setting "
        "(for example a branch, the ground, a horizon line, a couple of clouds); zoom in on the "
        "main subject so it fills most of the page"
    ),
    "remove": (
        "no background at all: the subject alone on plain white, zoomed in so it fills most of "
        "the page"
    ),
}

COLORING_PAGE_PROMPT = """\
Turn the attached photo into a coloring-book page for children: a BLACK-AND-WHITE LINE
DRAWING, black outlines on a pure white background, with NO COLOR AT ALL.

Do NOT copy the colors or the dark areas of the photo. Every area is left WHITE inside its
outline so a child can color it in, including the parts that are black or dark in the photo:
a black bird's body is an outline with white inside, never a black shape.

SUBJECT: the attached photo IS the subject. Keep what makes it recognizable: the same
species, building, object or person, the same pose and viewpoint, the same proportions,
and its distinctive shapes and markings, drawn as outlined areas to color. Draw exactly the
animals, people and objects that are in the photo: never add new ones, never duplicate one.
{title_line}
STYLE: {style}.
DETAIL: {detail}.
BACKGROUND: {background}.
{instructions_block}
STRICT COLORING-PAGE RULES:
- Pure black outlines on a pure white background. Nothing else: no color anywhere.
- No shading, no gray, no gradients, no hatching, no stippling, no texture strokes.
- No solid black fills, except tiny details such as the pupils of the eyes. Dark fur,
  feathers, hair, windows or shadows are outlines with white inside.
- Every line belongs to a closed shape, so each area can be colored in. No loose strokes:
  grass, leaves, fur, hair and feathers are a few outlined clumps or locks, never many
  separate little lines.
- Line weight: {lines}.
- No text, letters, numbers, signatures, watermarks, borders or frames.
- Flat digital artwork filling the whole image. Not a photo or mockup of a printed page:
  no paper edges, no book, no table, no shadows.
- The whole subject is visible, with a white margin around the drawing.
"""

# Aspect ratios the image model accepts, as width / height.
_ASPECTS = {"3:4": 3 / 4, "1:1": 1.0, "4:3": 4 / 3}


def aspect_for(width: int, height: int) -> str:
    """Closest supported aspect ratio to the photo's, so the framing survives."""
    ratio = width / height
    return min(_ASPECTS, key=lambda key: abs(_ASPECTS[key] - ratio))


def build_prompt(style: str, age_group: str, background: str, title: str = "", instructions: str = "") -> str:
    age = AGE_PROMPTS[age_group]
    title_line = f"The subject is: {title.strip()}.\n" if title.strip() else ""
    instructions_block = (
        f"AUTHOR'S INSTRUCTIONS (highest priority, unless they break the coloring-page rules):\n"
        f"{instructions.strip()}\n"
        if instructions.strip()
        else ""
    )
    return COLORING_PAGE_PROMPT.format(
        title_line=title_line,
        style=STYLE_PROMPTS[style],
        detail=age["detail"],
        background=BACKGROUND_PROMPTS[background],
        instructions_block=instructions_block,
        lines=age["lines"],
    )


def render_coloring_page(photo: bytes, size: tuple[int, int], prompt: str) -> bytes:
    """Raw model output for one photo (PNG bytes, not yet cleaned)."""
    return gemini.generate_image(prompt, reference_images=[photo], aspect_ratio=aspect_for(*size), image_size="2K")


@dataclass
class Rendered:
    """A conversion that is ready to store: model output, cleaned page, and its version."""

    page: Page
    raw: bytes
    version: Version
    clean: Image.Image


def mosaic_draft(book: Book, page: Page) -> tuple[np.ndarray, MosaicSettings]:
    """The mystery mosaic the page's current settings make, without storing it (previews)."""
    settings = mosaic.settings_for(book, page)
    return mosaic.make_grid(pages.cropped_photo(book.slug, page), settings), settings


def render_page(book: Book, page: Page, engine: Engine) -> Rendered:
    """Convert a page's (cropped) photo without storing anything. Raises ``gemini.GeminiError``."""
    style = page.style or book.style
    background = page.background or book.background
    if engine == "mosaic":
        # Not line art: the grid is stored as data and the solution is already 1-bit.
        grid, settings = mosaic_draft(book, page)
        version = Version(
            n=0, engine=engine, style=style, age_group=book.age_group, background=background,
            mosaic=settings, curve=page.curve, created_at=now(),
        )
        return Rendered(page, mosaic.grid_png(grid), version, mosaic.render_solution(grid, settings))
    photo = pages.cropped_photo(book.slug, page)
    if engine == "gemini":
        prompt = build_prompt(style, book.age_group, background, page.title, page.instructions)
        with usage.book_context(book.id):
            raw = render_coloring_page(pages.jpeg_bytes(photo), photo.size, prompt)
    else:
        raw = lineart.to_png(lineart.draft(photo, style, book.age_group))
    cleaned = lineart.clean(raw, book.age_group)
    version = Version(
        n=0,
        engine=engine,
        style=style,
        age_group=book.age_group,
        background=background,
        instructions=page.instructions,
        curve=page.curve,
        warnings=cleaned.warnings,
        created_at=now(),
    )
    return Rendered(page, raw, version, cleaned.image)


def _store(book: Book, rendered: Rendered) -> Page:
    return pages.add_version(book.slug, rendered.page.id, rendered.version, rendered.raw, rendered.clean)


def convert_page(book: Book, page: Page, engine: Engine, replace: int | None = None) -> Page:
    """Convert a page's (cropped) photo and store the result as its new selected version.

    ``engine`` is ``"gemini"`` (AI, paid), ``"draft"`` (offline, free) or ``"mosaic"`` (a
    mystery mosaic, offline, free). With ``replace``, that version is deleted once the new
    one is stored: versions are never overwritten, so the replacement gets the next number.
    Raises ``gemini.GeminiError`` when the AI call fails; nothing is stored or deleted then.
    """
    stored = _store(book, render_page(book, page, engine))
    if replace is not None:
        stored = pages.delete_version(book.slug, page.id, replace)
    return stored


def convert_pages(
    book: Book, page_list: list[Page], engine: Engine, on_done: Callable[[int, Page, str | None], None] | None = None
) -> list[tuple[Page, str]]:
    """Convert several pages, ``BATCH_WORKERS`` AI calls at a time; returns the failures.

    Every result is stored from the calling thread as soon as it arrives, so ``pages.json``
    is never written by two threads. ``on_done(count, page, error)`` reports each page.
    """
    failures: list[tuple[Page, str]] = []
    workers = BATCH_WORKERS if engine == "gemini" else 1
    # usage.book_context is process-wide: set it once around the pool, not per thread.
    with usage.book_context(book.id), ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(render_page, book, page, engine): page for page in page_list}
        for count, future in enumerate(as_completed(futures), start=1):
            page = futures[future]
            try:
                _store(book, future.result())
                error = None
            except gemini.GeminiError as exc:
                error = str(exc)
                failures.append((page, error))
            if on_done:
                on_done(count, page, error)
    return failures
