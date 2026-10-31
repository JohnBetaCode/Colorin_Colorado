"""Text written with the AI: captions in the book's second language, and the Amazon listing.

Every call goes through ``gemini.extract_structured`` and is attributed to the book. The
model only works from what the book contains: it translates what the author typed, and
describes the pages that are there. The author edits everything before using it.
"""

from __future__ import annotations

from app.core import gemini, pages, usage
from app.core.i18n import LANGUAGE_NAMES
from app.core.schema import Book, Caption, Listing, Page

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


MAX_KEYWORDS = 7
MAX_KEYWORD_CHARS = 50
MAX_CATEGORIES = 3

LISTING_PROMPT = """\
Write the Amazon product page details of a children's coloring book that will be published
with Kindle Direct Publishing. Write in {language}, the language of the book.

The book:
- Title: {title}
- Subtitle: {subtitle}
- For ages {age}, {style} drawings, {count} coloring pages, each with the real photo it was
  drawn from and a short caption{bilingual}.
- Extra pages: {extras}
- The pages:
{pages}

Return:
- description: 120 to 250 words for parents and grandparents. What is inside, why it is
  different (every drawing comes with its real photo and facts), the age, and that each drawing
  is printed on its own sheet. Simple HTML only: <p>, <b>, <i>, <br>, <ul>, <li>.
- keywords: exactly 7 search phrases buyers would type, at most 50 characters each, spelled
  normally (with accents). Do not repeat words of the title, no brand or author names, no
  "free", "best seller", "new" or other claims.
- categories: 3 Amazon book categories as paths, e.g. "Children's Books > Activities, Crafts &
  Games > Coloring". Use the English names KDP shows.
- reading_age: the age range, like "6-8".
Only describe what is in the book. Do not invent pages, features or facts.
"""


def suggest_listing(book: Book, page_list: list[Page]) -> Listing:
    """A listing drafted from the book's pages. Raises ``gemini.GeminiError``."""
    included = [p for p in page_list if p.in_book]
    lines = [
        f"  - {p.title.strip() or p.original_name}" + (f": {p.info.strip().splitlines()[0]}" if p.info.strip() else "")
        for p in included
    ]
    second = book.languages[1:] if len(book.languages) > 1 else []
    prompt = LISTING_PROMPT.format(
        language=LANGUAGE_NAMES[book.language],
        title=book.title,
        subtitle=book.subtitle or "(none)",
        age=book.age_group,
        style=book.style,
        count=len(included),
        bilingual=f", in {LANGUAGE_NAMES[book.language]} and {LANGUAGE_NAMES[second[0]]}" if second else "",
        extras=", ".join(book.extras) or "none",
        pages="\n".join(lines) or "  (none yet)",
    )
    with usage.book_context(book.id):
        listing = gemini.extract_structured(prompt, Listing)
    return Listing(
        description=listing.description.strip(),
        keywords=[k.strip()[:MAX_KEYWORD_CHARS] for k in listing.keywords if k.strip()][:MAX_KEYWORDS],
        categories=[c.strip() for c in listing.categories if c.strip()][:MAX_CATEGORIES],
        reading_age=listing.reading_age.strip(),
    )
