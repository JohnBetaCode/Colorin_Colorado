"""Create (once) the neutral demo book the screenshots are taken from. Never calls an AI.

Runs inside the app's image, through ``demo_book.sh``, which mounts this folder at /skill and
``spike/`` read-only. The book is found by its title: when it already exists nothing is changed
and its slug is printed, so the script is safe to run before every capture.

Pages (photo, caption) are listed in DEMO_PAGES. Captions are written here, never copied from
another book: the product is place-neutral, and the screenshots must not show a country or city.
Each photo is looked for in spike/photos/, then among the originals of the existing books (by
the name it was uploaded with). Each coloring page is, in order of preference:

  1. the selected version of a page of another book made from the same photo (an AI page that
     already went through lineart.clean, copied as is: no new AI call, no cost); or
  2. the free offline draft (imaging.convert_page with the "draft" engine, the "Borrador gratis"
     button's path).

The first page is approved, the others are left converted, so the workbench shows both states.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from PIL import Image  # noqa: E402

from app.core import books, imaging, pages  # noqa: E402
from app.core.books import now  # noqa: E402
from app.core.schema import Version  # noqa: E402

TITLE = "Mi mundo para colorear"
BOOK = {
    "subtitle": "Para colorear y aprender",
    "style": "realistic",
    "age_group": "6-8",
    "background": "simplify",
    "language": "es",
}
SPIKE_PHOTOS = Path("/workspace/spike/photos")

# Keep every text free of place names (no country, city, region or landmark).
DEMO_PAGES = [
    {
        "photo": "toucan.jpg",
        "title": "Tucán pico iris",
        "subtitle": "Ramphastos sulfuratus",
        "info": "Dónde vive: bosques tropicales húmedos\nDato curioso: su pico es enorme pero liviano, hueco por dentro",
    },
    {
        "photo": "pigeons.jpg",
        "title": "Palomas en la plaza",
        "subtitle": "",
        "info": "Una niña juega entre las palomas.",
    },
    {
        "photo": "boy.jpg",
        "title": "Una sonrisa enorme",
        "subtitle": "",
        "info": "",
    },
]


def find_demo() -> books.Book | None:
    return next((b for b in books.list_books() if b.title == TITLE), None)


def find_photo(name: str) -> tuple[bytes, tuple[str, pages.Page] | None] | None:
    """The photo's bytes, and a page of another book made from it (if any)."""
    source = None
    for book in books.list_books():
        if book.title == TITLE:
            continue
        for page in pages.load_pages(book.slug):
            if page.original_name == name and pages.selected_path(book.slug, page):
                source = (book.slug, page)
                break
        if source:
            break
    if (SPIKE_PHOTOS / name).exists():
        return (SPIKE_PHOTOS / name).read_bytes(), source
    if source:
        slug, page = source
        return pages.original_path(slug, page).read_bytes(), source
    return None


def copy_version(dest_slug: str, page_id: str, source: tuple[str, pages.Page]) -> Version:
    slug, page = source
    old = next(v for v in page.versions if v.n == page.selected)
    raw_path = pages.version_path(slug, page.id, old.n, raw=True)
    clean = Image.open(pages.version_path(slug, page.id, old.n))
    clean.load()
    raw = raw_path.read_bytes() if raw_path.exists() else pages.version_path(slug, page.id, old.n).read_bytes()
    version = old.model_copy(update={"n": 0, "created_at": now(), "instructions": ""})
    pages.add_version(dest_slug, page_id, version, raw, clean)
    return version


def main() -> None:
    existing = find_demo()
    if existing:
        print(existing.slug)
        return
    found = []
    for spec in DEMO_PAGES:
        hit = find_photo(spec["photo"])
        if hit is None:
            print(f"skipped {spec['photo']}: not in spike/photos/ nor in any book", file=sys.stderr)
        else:
            found.append((spec, *hit))
    if not found:
        sys.exit("no demo photos found: put " + ", ".join(p["photo"] for p in DEMO_PAGES) + " in spike/photos/")

    book = books.create_book(TITLE, **BOOK)
    page_ids = []
    for spec, photo, source in found:
        page = pages.add_photo(book.slug, spec["photo"], photo)
        fields = {k: spec[k] for k in ("title", "subtitle", "info")}
        if source:
            version = copy_version(book.slug, page.id, source)
            if version.style != book.style:
                fields["style"] = version.style  # so the workbench shows the style it was drawn in
            how = f"copied its {version.engine} page from books/{source[0]}"
        pages.update_page(book.slug, page.id, **fields)
        if not source:
            imaging.convert_page(book, pages.get_page(book.slug, page.id), "draft")
            how = "free draft"
        page_ids.append(page.id)
        print(f"{spec['photo']}: {how}", file=sys.stderr)
    pages.approve(book.slug, page_ids[0])
    print(book.slug)


if __name__ == "__main__":
    main()
