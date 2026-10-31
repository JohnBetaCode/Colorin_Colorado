"""Color front-cover images for the KDP cover: uploaded, or drawn by the AI.

Unlike coloring pages, cover art is in full color and is not cleaned by
``lineart.clean``, and the AI may draw it from text alone: from a collage of the
book's pages (their line art and photos are the references), from a description the
author types, or from the book's theme (title, subtitle and page titles). Every image
is stored as ``books/<slug>/cover_art/v<n>.jpg`` and never overwritten; the book
records which one the cover uses.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

from app.core import books, gemini, lineart, pages, usage
from app.core.books import book_path, now
from app.core.schema import ArtMode, ArtSource, Book, CoverArt, Page

MAX_PX = 6000  # uploads are downscaled to this on the long side
JPEG_QUALITY = 95
ASPECT_RATIO = "3:4"  # closest to a portrait front cover
IMAGE_SIZE = "4K"  # 3584 × 4800 at 3:4: over 400 ppi on an 11 in cover
MAX_COLLAGE_PAGES = 6
# Ghostscript's default CMYK profile (coated paper, SWOP-like), from libgs-common in the image.
CMYK_PROFILE = Path("/usr/share/color/icc/ghostscript/default_cmyk.icc")  # each sends two references (line art and photo); the model takes 14

COVER_RULES = """Rules:
- Full color, bright and cheerful, clean shapes, made to look good in print.
- Fill the whole image edge to edge: no border, no frame, no mockup of a book, no photo of a printed cover.
- No text, letters, numbers, logos, signatures or watermarks anywhere: the title is added later.
- Keep the top quarter calm and simple (sky or a plain background): the title goes over it.
- Portrait composition with the main subjects in the middle and lower part."""

STYLE_HINTS = {
    "realistic": "a detailed, natural-looking children's book illustration",
    "cartoon": "a friendly children's cartoon with rounded shapes and expressive faces",
}


def art_path(book: Book, n: int) -> Path:
    return book_path(book.slug) / "cover_art" / f"v{n}.jpg"


def selected(book: Book) -> CoverArt | None:
    return next((art for art in book.cover_art if art.n == book.cover_art_selected), None)


def selected_path(book: Book) -> Path | None:
    """The cover image the front uses, or None for the cover page's line art."""
    art = selected(book)
    if art is None:
        return None
    path = art_path(book, art.n)
    return path if path.exists() else None


def print_ppi(size: tuple[int, int], box: tuple[float, float]) -> float:
    """Resolution of an image of ``size`` px scaled to fill a ``box`` in inches (overflow is cropped)."""
    return min(size[0] / box[0], size[1] / box[1])


@lru_cache(maxsize=1)
def _press_transform() -> ImageCms.ImageCmsTransform | None:
    if not CMYK_PROFILE.exists():
        return None
    return ImageCms.buildTransform(
        ImageCms.createProfile("sRGB"),
        ImageCms.getOpenProfile(str(CMYK_PROFILE)),
        "RGB",
        "CMYK",
        renderingIntent=ImageCms.Intent.PERCEPTUAL,
    )


def to_cmyk(image: Image.Image) -> Image.Image:
    """RGB to CMYK for print: through the press profile when installed, else ``plain_cmyk``.

    The profile keeps colors closer to the screen and limits the total ink; KDP strips
    embedded profiles and prints with its own, so none is embedded.
    """
    transform = _press_transform()
    if transform is None:
        return plain_cmyk(image)
    return ImageCms.applyTransform(image.convert("RGB"), transform)


def plain_cmyk(image: Image.Image) -> Image.Image:
    """RGB to CMYK by formula, with full black generation: grays and darks print with black only."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
    k = 1 - rgb.max(axis=2)
    room = np.where(k < 1, 1 - k, 1)[..., None]
    cmy = (1 - rgb - k[..., None]) / room
    cmyk = (np.dstack([cmy, k]) * 255).round().astype(np.uint8)
    return Image.frombytes("CMYK", image.size, cmyk.tobytes())


def _store(book: Book, image: Image.Image, source: ArtSource, prompt: str = "", page_ids: list[str] | None = None) -> Book:
    """Save the image as the next version, select it and save the book."""
    n = max((art.n for art in book.cover_art), default=0) + 1
    path = art_path(book, n)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="JPEG", quality=JPEG_QUALITY)
    book.cover_art.append(CoverArt(n=n, source=source, prompt=prompt, page_ids=page_ids or [], created_at=now()))
    book.cover_art_selected = n
    books.save_book(book)
    return book


def add_upload(book: Book, data: bytes) -> Book:
    """Store an uploaded image as the new cover art. Raises ``ValueError`` if unreadable."""
    try:
        image = lineart.load_image(data)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    image.thumbnail((MAX_PX, MAX_PX))
    return _store(book, image, "upload")


def select(book: Book, n: int | None) -> Book:
    book.cover_art_selected = n
    books.save_book(book)
    return book


def _title(page: Page) -> str:
    return page.title.strip() or "(untitled)"


def build_prompt(book: Book, mode: ArtMode, text: str, page_list: list[Page]) -> str:
    style = STYLE_HINTS[book.style]
    titles = ", ".join(_title(p) for p in page_list)
    if mode == "collage":
        task = (
            "Create the front cover illustration of a children's coloring book as a joyful collage of its "
            "pages. The reference images come in pairs, one pair per subject: the coloring page (black "
            "outlines) and the photo it was drawn from. Redraw every subject from its coloring page, together "
            "in one composition, and color it in with the real colors from its photo: keep the clean black "
            "outlines visible and fill the areas with bright, flat or softly shaded colors, so the cover shows "
            "what the pages look like once colored. Not a photograph and not a painting. Keep each subject "
            f"recognizable. Subjects: {titles}."
        )
    elif mode == "text":
        task = f"Create the front cover illustration of a children's coloring book, in the style of {style}: {text.strip()}"
    else:
        subtitle = f" ({book.subtitle.strip()})" if book.subtitle.strip() else ""
        task = (
            "Create the front cover illustration of a children's coloring book, in the style of "
            f"{style}, that captures what the book is about. The book is called \"{book.title}\"{subtitle} "
            f"and its pages show: {titles or 'various subjects'}. Pick a few of them for an inviting scene."
        )
    if mode != "text" and text.strip():
        task += f"\nExtra instructions from the author: {text.strip()}"
    return f"{task}\n\n{COVER_RULES}"


def _references(book: Book, page_list: list[Page]) -> list[bytes]:
    images = []
    for page in page_list:
        art = pages.selected_path(book.slug, page)
        if art:
            images.append(art.read_bytes())
        photo = pages.cropped_photo(book.slug, page, group=False)  # the real colors for a color cover
        photo.thumbnail((1024, 1024))
        images.append(pages.jpeg_bytes(photo))
    return images


def generate(book: Book, mode: ArtMode, text: str = "", page_ids: list[str] | None = None) -> Book:
    """Draw a new cover image with the AI and select it. Raises ``gemini.GeminiError``.

    ``page_ids`` are the collage's pages (at most ``MAX_COLLAGE_PAGES``); the theme uses
    the titles of every page in the book.
    """
    if mode == "text" and not text.strip():
        raise ValueError("Describe the cover to draw it from text.")
    in_book = [p for p in pages.load_pages(book.slug) if p.in_book]
    chosen = [p for p in in_book if p.id in (page_ids or [])][:MAX_COLLAGE_PAGES] if mode == "collage" else []
    if mode == "collage" and not chosen:
        raise ValueError("Pick at least one page for the collage.")
    prompt = build_prompt(book, mode, text, chosen if mode == "collage" else in_book)
    with usage.book_context(book.id):
        raw = gemini.generate_image(prompt, _references(book, chosen), aspect_ratio=ASPECT_RATIO, image_size=IMAGE_SIZE)
    return _store(book, lineart.load_image(raw), mode, text.strip(), [p.id for p in chosen])
