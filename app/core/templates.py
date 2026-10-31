"""Book templates: how a kind of book is usually drawn and what its pages usually say.

A template sets the book's default background when it is created, the hint under the
page title (``template_subtitle.<template>``) and the labels the workbench can insert into
a page's info text (``template_labels.<template>``, in the book's language). ``free`` has none.
"""

from __future__ import annotations

from app.core import i18n
from app.core.schema import Background, Book, Template

BACKGROUND: dict[Template, Background] = {"free": "simplify", "nature": "simplify", "landmarks": "keep", "family": "simplify"}


def labels(book: Book) -> str:
    """The info lines to fill in, like "Where it lives: ", one per line; empty for ``free``."""
    if book.template == "free":
        return ""
    return "\n".join(f"{label} " for label in i18n.t(f"template_labels.{book.template}", lang=book.language).splitlines())
