"""Book storage.

Each book lives in its own folder under ``books/`` (git-ignored):

    books/<slug>/
        book.json                       Book
        pages.json                      list[Page], in book order
        originals/<page-id>.jpg         uploaded photo (rotated, downscaled)
        lineart/<page-id>/v<n>-raw.png  model output, untouched
        lineart/<page-id>/v<n>.png      1-bit cleaned coloring page
        cover_art/v<n>.jpg              front cover image for the KDP cover
        exports/<slug>-<timestamp>.pdf  one file per build
        exports/covers/<slug>-cover-<pages>p-<timestamp>.pdf
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from pydantic import ValidationError

from app.core.config import ROOT_DIR
from app.core.schema import Book, Page

BOOKS_DIR = ROOT_DIR / "books"
SUBFOLDERS = ("originals", "lineart", "exports")
# What a book archive carries: everything but its exports, which can be rebuilt.
ARCHIVE_ENTRIES = re.compile(r"^(book\.json|pages\.json|originals/[^/]+|lineart/[^/]+/[^/]+|cover_art/[^/]+)$")
MAX_ARCHIVE_BYTES = 2_000_000_000  # uncompressed, against zip bombs


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name.strip().lower()).strip("-")
    return slug or "book"


def inside(root: Path, path: Path) -> Path:
    """``path``, if it stays inside ``root``; raises ``ValueError`` otherwise."""
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{path} is outside {root}.")
    return path


def book_path(slug: str) -> Path:
    path = BOOKS_DIR / slug
    if not slug or path.resolve().parent != BOOKS_DIR.resolve():
        raise ValueError(f"Not a book folder name: {slug!r}.")
    return path


def list_books() -> list[Book]:
    """Every book on disk, newest first."""
    books = []
    for meta in BOOKS_DIR.glob("*/book.json") if BOOKS_DIR.exists() else []:
        try:
            books.append(Book.model_validate_json(meta.read_text(encoding="utf-8")))
        except (OSError, ValidationError):
            continue
    return sorted(books, key=lambda b: b.created_at, reverse=True)


def load_book(slug: str) -> Book | None:
    meta = book_path(slug) / "book.json"
    if not meta.exists():
        return None
    return Book.model_validate_json(meta.read_text(encoding="utf-8"))


def save_book(book: Book) -> None:
    book.updated_at = now()
    (book_path(book.slug) / "book.json").write_text(book.model_dump_json(indent=2), encoding="utf-8")


def _free_slug(title: str) -> str:
    slug = slugify(title)
    return f"{slug}-{uuid.uuid4().hex[:6]}" if book_path(slug).exists() else slug


def create_book(title: str, **fields) -> Book:
    slug = _free_slug(title)
    root = book_path(slug)
    for sub in SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "pages.json").write_text("[]")
    book = Book(id=uuid.uuid4().hex, slug=slug, title=title.strip(), created_at=now(), updated_at=now(), **fields)
    save_book(book)
    return book


def delete_book(slug: str) -> None:
    root = book_path(slug)
    if root.exists():
        shutil.rmtree(root)


def _as_new_book(book: Book, slug: str, title: str | None = None) -> Book:
    """``book`` under a new id and slug: a copy never shares usage or files with its source."""
    root = book_path(slug)
    for sub in SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    copy = book.model_copy(
        update={"id": uuid.uuid4().hex, "slug": slug, "title": (title or book.title).strip(), "created_at": now()}
    )
    save_book(copy)
    return copy


def duplicate_book(slug: str, title: str) -> Book:
    """Copy a book with its photos, coloring-page versions and cover images; exports stay behind."""
    source = load_book(slug)
    if source is None:
        raise ValueError(f"No book {slug!r}.")
    new_slug = _free_slug(title)
    shutil.copytree(book_path(slug), book_path(new_slug), ignore=shutil.ignore_patterns("exports"))
    return _as_new_book(source, new_slug, title)


def export_zip(slug: str) -> bytes:
    """The book as a ZIP archive (without its exports), to back it up or move it."""
    root = book_path(slug)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            name = path.relative_to(root).as_posix()
            if path.is_file() and ARCHIVE_ENTRIES.match(name):
                archive.write(path, name)
    return buffer.getvalue()


def import_zip(data: bytes) -> Book:
    """Add the book in a ZIP made by ``export_zip`` as a new book; it never replaces one.

    Raises ``ValueError`` when the file is not such an archive.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Not a ZIP file.") from exc
    with archive:
        entries = [info for info in archive.infolist() if ARCHIVE_ENTRIES.match(info.filename)]
        names = {info.filename for info in entries}
        if not {"book.json", "pages.json"} <= names:
            raise ValueError("Not a Colorín Colorado book: book.json or pages.json is missing.")
        if sum(info.file_size for info in entries) > MAX_ARCHIVE_BYTES:
            raise ValueError("The archive is too big.")
        try:
            book = Book.model_validate_json(archive.read("book.json"))
            [Page.model_validate(item) for item in json.loads(archive.read("pages.json"))]
        except (ValidationError, ValueError) as exc:
            raise ValueError(f"The book in the archive is damaged: {exc}") from exc
        slug = _free_slug(book.title)
        root = book_path(slug)
        try:
            for info in entries:
                if ".." in Path(info.filename).parts:
                    continue
                target = root / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
    return _as_new_book(book, slug)
