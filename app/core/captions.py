"""Page captions written with the AI: translation into the book's second language.

Every call goes through ``gemini.extract_structured`` and is attributed to the book.
Nothing is invented: the model only translates what the author typed.
"""

from __future__ import annotations

from app.core import gemini, pages, usage
from app.core.i18n import LANGUAGE_NAMES
from app.core.schema import Book, Caption, Page

TRANSLATE_PROMPT = """\
Translate the caption of a page of a children's coloring book from {source} to {target}.
Keep it as short, simple and friendly as the original, for children aged {age}. Keep
scientific names, people's names and place names as they are. The info text keeps its
lines: a line "Label: text" stays one line, with the label translated. Translate only what
is there: add nothing, and leave a field empty when it is empty.

Title: {title}
Subtitle: {subtitle}
Info:
{info}
"""


def translate(book: Book, page: Page) -> Caption:
    """The page's caption in the book's second language. Raises ``gemini.GeminiError``."""
    if not book.second_language or book.second_language == book.language:
        raise ValueError("The book has no second language.")
    prompt = TRANSLATE_PROMPT.format(
        source=LANGUAGE_NAMES[book.language],
        target=LANGUAGE_NAMES[book.second_language],
        age=book.age_group,
        title=page.title.strip(),
        subtitle=page.subtitle.strip(),
        info=page.info.strip(),
    )
    with usage.book_context(book.id):
        return gemini.extract_structured(prompt, Caption)


def translate_page(book: Book, page: Page) -> Page:
    """Translate one page and store the result."""
    return pages.update_page(book.slug, page.id, translation=translate(book, page))


def missing_translations(book: Book, page_list: list[Page]) -> list[Page]:
    """Pages with a caption and no translation yet."""
    return [p for p in page_list if p.has_caption and p.translation.is_empty]
