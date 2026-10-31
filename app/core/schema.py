"""Book and page models, persisted as JSON under ``books/<slug>/``.

Everything here is written by the app or typed by the user; nothing comes from the
LLM, so empty strings are fine (unlike Once Upon a Time's ``"undefined"`` rule).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Style = Literal["realistic", "cartoon", "kawaii", "mandala"]
AgeGroup = Literal["3-5", "6-8", "9+", "adult"]
Background = Literal["keep", "simplify", "remove"]
Language = Literal["es", "en"]
PageSize = Literal["letter", "a4", "8x10", "square"]  # square: 8.5 × 8.5 in
Marketplace = Literal["us", "uk", "es"]
Template = Literal["free", "nature", "landmarks", "family"]  # see templates.py  # the Amazon store KDP costs and royalties are estimated for
Engine = Literal["gemini", "draft", "mosaic"]
# Mystery mosaics (mosaic.py): how each number is filled in (pencil tones or a palette of pen
# patterns), and whether cells are whole squares or split along a diagonal into two triangles.
MosaicFill = Literal["tones", "classic", "lines", "stipple", "geometric"]
MosaicCells = Literal["square", "diagonal"]
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

STYLES: tuple[Style, ...] = ("realistic", "cartoon", "kawaii", "mandala")
AGE_GROUPS: tuple[AgeGroup, ...] = ("3-5", "6-8", "9+", "adult")
BACKGROUNDS: tuple[Background, ...] = ("keep", "simplify", "remove")
PAGE_SIZES: tuple[PageSize, ...] = ("letter", "a4", "8x10", "square")
MARKETPLACES: tuple[Marketplace, ...] = ("us", "uk", "es")
TEMPLATES: tuple[Template, ...] = ("free", "nature", "landmarks", "family")
ENGINES: tuple[Engine, ...] = ("gemini", "draft", "mosaic")
MOSAIC_FILLS: tuple[MosaicFill, ...] = ("tones", "classic", "lines", "stipple", "geometric")
MOSAIC_CELLS: tuple[MosaicCells, ...] = ("square", "diagonal")
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


class MosaicSettings(BaseModel):
    """How a photo becomes a mystery mosaic. ``mosaic.default_settings`` gives the age group's."""

    fill: MosaicFill = "tones"
    cells: MosaicCells = "square"
    tones: int = 4  # 2 to 5, from black to white
    columns: int = 30
    contrast: int = 0  # percent, -50 to 50
    brightness: int = 0  # percent, -50 to 50
    # White cells carry a number too: the picture stays hidden until colored, but the finished
    # page shows those digits.
    number_white: bool = False

    @field_validator("fill", mode="before")
    @classmethod
    def _one_palette_before(cls, value):
        # The first version had a single pattern set, saved as "patterns" (and a "symbols"
        # choice, now always numbers, which is simply ignored).
        return "classic" if value == "patterns" else value


class CoverArt(BaseModel):
    """One color front-cover image, uploaded or drawn by the AI: ``cover_art/v<n>.jpg``."""

    n: int
    source: ArtSource
    prompt: str = ""  # what the author typed: the description, or extra instructions
    page_ids: list[str] = Field(default_factory=list)  # pages a collage was drawn from
    created_at: str


class Caption(BaseModel):
    """A page's text in one language."""

    title: str = ""
    subtitle: str = ""
    info: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.title.strip() or self.subtitle.strip() or self.info.strip())


class Listing(BaseModel):
    """The book's Amazon product page details, as entered on KDP."""

    description: str = ""  # KDP accepts simple HTML: <p>, <br>, <b>, <i>, <ul>, <li>
    keywords: list[str] = Field(default_factory=list)  # up to 7, 50 characters each
    categories: list[str] = Field(default_factory=list)  # up to 3, as KDP's category paths
    reading_age: str = ""  # e.g. "6-8"


class Book(BaseModel):
    id: str
    slug: str
    title: str
    subtitle: str = ""
    dedication: str = ""
    template: Template = "free"
    style: Style = "realistic"
    age_group: AgeGroup = "6-8"
    background: Background = "simplify"
    language: Language = "es"
    second_language: Language | None = None  # captions and fixed labels printed in both languages
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
    marketplace: Marketplace = "us"
    list_price: float = 9.99  # in the marketplace's currency, before VAT
    cover_color: CoverColor = "blue"
    back_text: str = ""
    listing: Listing = Field(default_factory=Listing)
    cover_art: list[CoverArt] = Field(default_factory=list)  # never overwritten, like page versions
    cover_art_selected: int | None = None  # None: the cover page's line art on the front
    mosaic: MosaicSettings | None = None  # None: the age group's defaults
    created_at: str
    updated_at: str

    @property
    def languages(self) -> list[str]:
        """The languages the PDF is printed in: the book's, then the second one, if any."""
        second = self.second_language
        return [self.language, second] if second and second != self.language else [self.language]


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
    curve: list[tuple[int, int]] | None = None  # the photo's tone curve when it was converted
    group: int | None = None  # and its color grouping bandwidth
    warnings: list[str] = Field(default_factory=list)
    mosaic: MosaicSettings | None = None  # what a mosaic version was made with
    created_at: str


class Page(BaseModel):
    id: str
    original: str  # file name under originals/
    original_name: str  # name of the uploaded file
    title: str = ""
    subtitle: str = ""
    info: str = ""
    translation: Caption = Field(default_factory=Caption)  # the caption in the book's second language
    credit: str = ""  # who took the photo and its license, printed on the copyright page
    license: License = "unknown"
    source_url: str = ""  # where the photo comes from, e.g. its Wikimedia Commons page
    style: Style | None = None  # None: the book's style
    background: Background | None = None  # None: the book's background
    instructions: str = ""
    crop: Crop = Field(default_factory=Crop)
    curve: list[tuple[int, int]] | None = None  # tone curve on the photo (tones.py); None: as shot
    group: int | None = None  # color grouping bandwidth after the curve (grouping.py); None: off
    mosaic: MosaicSettings | None = None  # None: the book's
    versions: list[Version] = Field(default_factory=list)
    last_version: int = 0  # highest Version.n ever given: a deleted version's number is never reused
    selected: int | None = None  # Version.n shown and exported
    status: Status = "pending"
    in_book: bool = True

    @property
    def has_caption(self) -> bool:
        return bool(self.title.strip() or self.subtitle.strip() or self.info.strip())

    @property
    def selected_version(self) -> Version | None:
        return next((v for v in self.versions if v.n == self.selected), None)

    @property
    def is_mosaic(self) -> bool:
        """Whether the selected version is a mystery mosaic (printed as a puzzle, not line art)."""
        version = self.selected_version
        return version is not None and version.engine == "mosaic"
