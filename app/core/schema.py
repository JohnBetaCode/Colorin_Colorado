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

STYLES: tuple[Style, ...] = ("realistic", "cartoon")
AGE_GROUPS: tuple[AgeGroup, ...] = ("3-5", "6-8", "9+")
BACKGROUNDS: tuple[Background, ...] = ("keep", "simplify", "remove")
PAGE_SIZES: tuple[PageSize, ...] = ("letter", "a4")
ENGINES: tuple[Engine, ...] = ("gemini", "draft")
STATUSES: tuple[Status, ...] = ("pending", "converted", "approved")


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
