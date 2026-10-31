"""Book and page models, persisted as JSON under ``books/<slug>/``.

Everything here is written by the app or typed by the user; nothing comes from the
LLM, so empty strings are fine (unlike Once Upon a Time's ``"undefined"`` rule).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Style = Literal["realistic", "cartoon"]
AgeGroup = Literal["3-5", "6-8", "9+"]
Background = Literal["keep", "simplify", "remove"]
Language = Literal["es", "en"]
PageSize = Literal["letter", "a4"]
Engine = Literal["gemini", "draft"]
Status = Literal["pending", "converted", "approved"]
Ink = Literal["black", "standard_color", "premium_color"]  # Amazon KDP interior ink, white paper
CoverColor = Literal["blue", "green", "orange", "purple", "pink", "teal"]
ArtMode = Literal["collage", "text", "theme"]  # what an AI cover image is drawn from
ArtSource = Literal["upload", "collage", "text", "theme"]
# Extra pages, in the order they are printed: the color test after the owner page, the
# activities and their solutions after the coloring pages, then the diploma and the closing page.
Extra = Literal["color_test", "word_search", "maze", "dots", "solutions", "diploma", "closing"]
# Photo licenses, by what they allow in a book for sale (see docs/amazon-kdp.md).
License = Literal[
    "unknown", "own", "public_domain", "cc_by", "cc_by_sa", "free_license", "non_commercial", "no_derivatives"
]

STYLES: tuple[Style, ...] = ("realistic", "cartoon")
AGE_GROUPS: tuple[AgeGroup, ...] = ("3-5", "6-8", "9+")
BACKGROUNDS: tuple[Background, ...] = ("keep", "simplify", "remove")
PAGE_SIZES: tuple[PageSize, ...] = ("letter", "a4")
ENGINES: tuple[Engine, ...] = ("gemini", "draft")
STATUSES: tuple[Status, ...] = ("pending", "converted", "approved")
INKS: tuple[Ink, ...] = ("black", "standard_color", "premium_color")
COVER_COLORS: tuple[CoverColor, ...] = ("blue", "green", "orange", "purple", "pink", "teal")
ART_MODES: tuple[ArtMode, ...] = ("collage", "text", "theme")
ART_SOURCES: tuple[ArtSource, ...] = ("upload", "collage", "text", "theme")
EXTRAS: tuple[Extra, ...] = ("color_test", "word_search", "maze", "dots", "solutions", "diploma", "closing")
LICENSES: tuple[License, ...] = (
    "unknown", "own", "public_domain", "cc_by", "cc_by_sa", "free_license", "non_commercial", "no_derivatives"
)
LICENSES_NOT_FOR_SALE: tuple[License, ...] = ("non_commercial", "no_derivatives")
LICENSES_WITH_CREDIT: tuple[License, ...] = ("cc_by", "cc_by_sa")  # the credit must be printed


class CoverArt(BaseModel):
    """One color front-cover image, uploaded or drawn by the AI: ``cover_art/v<n>.jpg``."""

    n: int
    source: ArtSource
    prompt: str = ""  # what the author typed: the description, or extra instructions
    page_ids: list[str] = Field(default_factory=list)  # pages a collage was drawn from
    created_at: str


class Book(BaseModel):
    id: str
    slug: str
    title: str
    subtitle: str = ""
    dedication: str = ""
    style: Style = "realistic"
    age_group: AgeGroup = "6-8"
    background: Background = "simplify"
    language: Language = "es"
    page_size: PageSize = "letter"
    include_reference_photo: bool = True
    include_owner_page: bool = True
    blank_backs: bool = False
    cover_page_id: str | None = None
    extras: list[Extra] = Field(default_factory=list)
    dots_page_id: str | None = None  # the page the connect-the-dots is traced from; None: the first that works
    legal: str = ""  # copyright page text: rights, edition, ISBN
    # Amazon KDP: interior ink and list price (cost and royalty estimates), and the wraparound cover.
    kdp_ink: Ink = "black"
    list_price: float = 9.99
    cover_color: CoverColor = "blue"
    back_text: str = ""
    cover_art: list[CoverArt] = Field(default_factory=list)  # never overwritten, like page versions
    cover_art_selected: int | None = None  # None: the cover page's line art on the front
    created_at: str
    updated_at: str


class Crop(BaseModel):
    """Part of the photo to convert, as fractions of its width and height."""

    left: float = 0.0
    top: float = 0.0
    right: float = 1.0
    bottom: float = 1.0

    @property
    def is_full(self) -> bool:
        return (self.left, self.top, self.right, self.bottom) == (0.0, 0.0, 1.0, 1.0)


class Version(BaseModel):
    """One conversion attempt. Its files are ``lineart/<page-id>/v<n>-raw.png`` and ``v<n>.png``."""

    n: int
    engine: Engine
    style: Style
    age_group: AgeGroup
    background: Background
    instructions: str = ""
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class Page(BaseModel):
    id: str
    original: str  # file name under originals/
    original_name: str  # name of the uploaded file
    title: str = ""
    subtitle: str = ""
    info: str = ""
    credit: str = ""  # who took the photo and its license, printed on the copyright page
    license: License = "unknown"
    source_url: str = ""  # where the photo comes from, e.g. its Wikimedia Commons page
    style: Style | None = None  # None: the book's style
    background: Background | None = None  # None: the book's background
    instructions: str = ""
    crop: Crop = Field(default_factory=Crop)
    versions: list[Version] = Field(default_factory=list)
    selected: int | None = None  # Version.n shown and exported
    status: Status = "pending"
    in_book: bool = True

    @property
    def has_caption(self) -> bool:
        return bool(self.title.strip() or self.subtitle.strip() or self.info.strip())
