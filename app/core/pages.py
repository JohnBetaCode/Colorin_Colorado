"""Pages of a book: uploaded photos, their coloring-page versions, order and status.

``pages.json`` is rewritten whole on every change; the app is single-user and the
file stays small. Versions are never overwritten: regenerating adds ``v<n+1>``. The
author may delete one; its number is not reused.
"""

from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from app.core import lineart, tones
from app.core.books import book_path
from app.core.schema import Crop, Page, Version

register_heif_opener()

ORIGINAL_MAX_PX = 2048
UPLOAD_TYPES = ("jpg", "jpeg", "png", "webp", "heic", "heif")


def _pages_file(slug: str) -> Path:
    return book_path(slug) / "pages.json"


def load_pages(slug: str) -> list[Page]:
    path = _pages_file(slug)
    if not path.exists():
        return []
    return [Page.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def save_pages(slug: str, pages: list[Page]) -> None:
    payload = "[\n" + ",\n".join(p.model_dump_json(indent=2) for p in pages) + "\n]"
    _pages_file(slug).write_text(payload, encoding="utf-8")


def get_page(slug: str, page_id: str) -> Page | None:
    return next((p for p in load_pages(slug) if p.id == page_id), None)


def update_page(slug: str, page_id: str, **fields) -> Page:
    """Set ``fields`` on one page and save. Returns the updated page."""
    pages = load_pages(slug)
    page = next(p for p in pages if p.id == page_id)
    for key, value in fields.items():
        setattr(page, key, value)
    save_pages(slug, pages)
    return page


# --- Files -----------------------------------------------------------------------


def original_path(slug: str, page: Page) -> Path:
    return book_path(slug) / "originals" / page.original


def version_path(slug: str, page_id: str, n: int, raw: bool = False) -> Path:
    return book_path(slug) / "lineart" / page_id / (f"v{n}-raw.png" if raw else f"v{n}.png")


def selected_path(slug: str, page: Page) -> Path | None:
    """The cleaned coloring page currently selected, if any."""
    if page.selected is None:
        return None
    path = version_path(slug, page.id, page.selected)
    return path if path.exists() else None


def cropped_photo(slug: str, page: Page, curve: bool = True) -> Image.Image:
    """The original photo with the page's crop applied and, unless ``curve`` is False, its
    tone curve: what every engine converts and the PDF shows as the reference photo."""
    image = Image.open(original_path(slug, page)).convert("RGB")
    crop = page.crop
    if not crop.is_full:
        w, h = image.size
        box = (round(crop.left * w), round(crop.top * h), round(crop.right * w), round(crop.bottom * h))
        image = image.crop(box)
    return tones.apply(image, page.curve) if curve else image


def photo_size(slug: str, page: Page) -> tuple[int, int]:
    """Size of the cropped photo, without decoding it."""
    with Image.open(original_path(slug, page)) as image:
        w, h = image.size
    crop = page.crop
    return max(1, round((crop.right - crop.left) * w)), max(1, round((crop.bottom - crop.top) * h))


def jpeg_bytes(image: Image.Image, quality: int = 92) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


# --- Changes -----------------------------------------------------------------------


def add_photo(slug: str, filename: str, data: bytes) -> Page:
    """Store an uploaded photo as a new page at the end of the book.

    Raises ``ValueError`` when the file is not a readable image.
    """
    try:
        image = lineart.load_image(data)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    image.thumbnail((ORIGINAL_MAX_PX, ORIGINAL_MAX_PX))
    page_id = uuid.uuid4().hex[:12]
    page = Page(id=page_id, original=f"{page_id}.jpg", original_name=filename)
    (book_path(slug) / "originals").mkdir(parents=True, exist_ok=True)
    original_path(slug, page).write_bytes(jpeg_bytes(image))
    pages = load_pages(slug)
    pages.append(page)
    save_pages(slug, pages)
    return page


def add_version(slug: str, page_id: str, version: Version, raw: bytes, clean: Image.Image) -> Page:
    """Store a new conversion, select it and mark the page as converted."""
    pages = load_pages(slug)
    page = next(p for p in pages if p.id == page_id)
    version.n = max([page.last_version, *(v.n for v in page.versions)]) + 1
    page.last_version = version.n
    folder = book_path(slug) / "lineart" / page_id
    folder.mkdir(parents=True, exist_ok=True)
    version_path(slug, page_id, version.n, raw=True).write_bytes(raw)
    clean.save(version_path(slug, page_id, version.n))
    page.versions.append(version)
    page.selected = version.n
    page.status = "converted"
    save_pages(slug, pages)
    return page


def delete_version(slug: str, page_id: str, n: int) -> Page:
    """Delete one version and its files, when the author asks.

    Its number is never given again. When it was the selected one, the newest remaining
    version is selected and the page needs approving again; with none left it is pending.
    """
    pages = load_pages(slug)
    page = next(p for p in pages if p.id == page_id)
    if not any(v.n == n for v in page.versions):
        raise ValueError(f"Page {page_id} has no version {n}.")
    page.last_version = max([page.last_version, *(v.n for v in page.versions)])
    page.versions = [v for v in page.versions if v.n != n]
    for raw in (False, True):
        version_path(slug, page_id, n, raw=raw).unlink(missing_ok=True)
    if page.selected == n:
        page.selected = max((v.n for v in page.versions), default=None)
        page.status = "converted" if page.versions else "pending"
    save_pages(slug, pages)
    return page


def select_version(slug: str, page_id: str, n: int) -> Page:
    return update_page(slug, page_id, selected=n, status="converted")


def approve(slug: str, page_id: str) -> Page:
    page = get_page(slug, page_id)
    if page is None or page.selected is None:
        raise ValueError("Convert the page before approving it.")
    return update_page(slug, page_id, status="approved")


def set_crop(slug: str, page_id: str, crop: Crop) -> Page:
    return update_page(slug, page_id, crop=crop)


def move_page(slug: str, page_id: str, delta: int) -> None:
    pages = load_pages(slug)
    index = next(i for i, p in enumerate(pages) if p.id == page_id)
    target = max(0, min(len(pages) - 1, index + delta))
    pages.insert(target, pages.pop(index))
    save_pages(slug, pages)


def delete_page(slug: str, page_id: str) -> None:
    pages = load_pages(slug)
    page = next(p for p in pages if p.id == page_id)
    original_path(slug, page).unlink(missing_ok=True)
    folder = book_path(slug) / "lineart" / page_id
    for file in folder.glob("*") if folder.exists() else []:
        file.unlink()
    if folder.exists():
        folder.rmdir()
    for mask in (book_path(slug) / "masks").glob(f"{page_id}-*.png"):  # background.py's cache
        mask.unlink()
    save_pages(slug, [p for p in pages if p.id != page_id])


def book_thumbnail(slug: str, cover_page_id: str | None) -> Path | None:
    """The cover's coloring page, else the first converted page, else the first photo."""
    pages = load_pages(slug)
    ordered = sorted(pages, key=lambda p: p.id != cover_page_id)
    for page in ordered:
        path = selected_path(slug, page)
        if path:
            return path
    return original_path(slug, pages[0]) if pages else None
