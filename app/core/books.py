"""Book storage.

Each book lives in its own folder under ``books/`` (git-ignored):

    books/<slug>/
        book.json                       Book
        pages.json                      list[Page], in book order
        originals/<page-id>.jpg         uploaded photo (rotated, downscaled)
        lineart/<page-id>/v<n>-raw.png  model output, untouched
        lineart/<page-id>/v<n>.png      1-bit cleaned coloring page
        exports/<slug>-<timestamp>.pdf  one file per build
"""

from __future__ import annotations

import re
import shutil
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.core.config import ROOT_DIR
from app.core.schema import Book

BOOKS_DIR = ROOT_DIR / "books"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name.strip().lower()).strip("-")
    return slug or "book"


def book_path(slug: str) -> Path:
    return BOOKS_DIR / slug


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


def create_book(title: str, **fields) -> Book:
    slug = slugify(title)
    if book_path(slug).exists():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"
    root = book_path(slug)
    for sub in ("originals", "lineart", "exports"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "pages.json").write_text("[]")
    book = Book(id=uuid.uuid4().hex, slug=slug, title=title.strip(), created_at=now(), updated_at=now(), **fields)
    save_book(book)
    return book


def delete_book(slug: str) -> None:
    root = book_path(slug)
    if root.exists():
        shutil.rmtree(root)
