"""Amazon KDP paperback numbers and a review of a book against them.

Page limits, spine and cover size, printing cost and royalty, from the KDP help pages
as checked on 2026-10-31, for white paper, in Amazon.com (USD), Amazon.co.uk (GBP) and
Amazon.es (EUR; the other EU stores share its costs). ``docs/amazon-kdp.md``
has the sources and everything else KDP asks for. KDP changes these numbers from time
to time: update this module and that document together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image

from app.core import cover_art, export
from app.core.schema import LICENSES_NOT_FOR_SALE, LICENSES_WITH_CREDIT, Book, Ink, Marketplace, Page, PageSize

TRIM: dict[PageSize, tuple[float, float]] = {  # inches; all of them are "large" trims for printing cost
    "letter": (8.5, 11.0),
    "a4": (8.27, 11.69),
    "8x10": (8.0, 10.0),
    "square": (8.5, 8.5),
}
BLEED = 0.125  # inches added to the top, bottom and outside edges of the cover
# Interior page range per trim and ink, white paper. Standard color is not offered in A4.
PAGE_RANGE: dict[tuple[PageSize, Ink], tuple[int, int] | None] = {
    ("letter", "black"): (24, 590),
    ("letter", "standard_color"): (72, 600),
    ("letter", "premium_color"): (24, 590),
    ("a4", "black"): (24, 780),
    ("a4", "standard_color"): None,
    ("a4", "premium_color"): (24, 590),
    ("8x10", "black"): (24, 828),
    ("8x10", "standard_color"): (72, 600),
    ("8x10", "premium_color"): (24, 828),
    ("square", "black"): (24, 590),
    ("square", "standard_color"): (72, 600),
    ("square", "premium_color"): (24, 590),
}
MAX_PAGES = 300  # export.MARGIN (0.5") is KDP's minimum inside margin up to 300 pages
SPINE_PER_PAGE: dict[Ink, float] = {"black": 0.002252, "standard_color": 0.002252, "premium_color": 0.002347}
SPINE_TEXT_MIN_PAGES = 79
SPINE_TEXT_CLEARANCE = 0.0625  # inches between spine text and each spine edge
BARCODE = (2.0, 1.2)  # inches: the white box KDP prints in the lower right of the back cover
BARCODE_INSET = 0.25  # inches from the spine and the bottom trim
ROYALTY_HIGH, ROYALTY_LOW = 0.60, 0.50
# List prices below these earn ROYALTY_LOW (since 2025-06-10). List prices are before VAT:
# Amazon adds the local VAT on top in the UK and EU stores.
ROYALTY_THRESHOLD: dict[Marketplace, float] = {"us": 9.99, "uk": 7.99, "es": 9.99}
CURRENCY: dict[Marketplace, str] = {"us": "$", "uk": "£", "es": "€"}
# Large-trim printing cost: (flat cost below the per-page range, fixed cost, cost per page).
PRINTING: dict[Marketplace, dict[Ink, tuple[float, float, float]]] = {
    "us": {"black": (2.84, 1.00, 0.017), "premium_color": (4.20, 1.00, 0.08), "standard_color": (0.0, 1.00, 0.0402)},
    "uk": {"black": (2.15, 0.85, 0.012), "premium_color": (3.24, 0.85, 0.0598), "standard_color": (0.0, 0.85, 0.027)},
    "es": {"black": (2.48, 0.75, 0.016), "premium_color": (3.61, 0.75, 0.0715), "standard_color": (0.0, 0.75, 0.035)},
}
FLAT_UP_TO: dict[Ink, int] = {"black": 108, "premium_color": 40, "standard_color": 0}  # pages at the flat cost
MIN_PRINT_PAGES: dict[Ink, int] = {"black": 24, "premium_color": 24, "standard_color": 72}
MAX_PRICE = 250.0
MIN_PPI = 300

Level = Literal["error", "warning", "info"]


def printed_pages(pages: int) -> int:
    """Pages as printed: every sheet has two sides, so an odd count gets a blank last page."""
    return pages + pages % 2


def spine_width(pages: int, ink: Ink) -> float:
    """Spine width in inches."""
    return printed_pages(pages) * SPINE_PER_PAGE[ink]


def cover_size(pages: int, ink: Ink, page_size: PageSize) -> tuple[float, float]:
    """Width and height in inches of the wraparound cover: back, spine and front, with bleed."""
    width, height = TRIM[page_size]
    return 2 * BLEED + 2 * width + spine_width(pages, ink), 2 * BLEED + height


def front_art_size(page_size: PageSize) -> tuple[float, float]:
    """Inches a front cover image fills: the front plus its bleed on the three outer edges."""
    width, height = TRIM[page_size]
    return width + BLEED, height + 2 * BLEED


def printing_cost(pages: int, ink: Ink, marketplace: Marketplace = "us") -> float | None:
    """Printing cost of one copy in the marketplace's currency (every trim here is large).

    None below the ink's minimum page count, where KDP does not print the book.
    """
    n = printed_pages(pages)
    if n < MIN_PRINT_PAGES[ink]:
        return None
    flat, fixed, per_page = PRINTING[marketplace][ink]
    return round(flat if n <= FLAT_UP_TO[ink] else fixed + per_page * n, 2)


def royalty_rate(price: float, marketplace: Marketplace = "us") -> float:
    return ROYALTY_HIGH if price >= ROYALTY_THRESHOLD[marketplace] else ROYALTY_LOW


def royalty(price: float, cost: float, marketplace: Marketplace = "us") -> float:
    """What KDP pays per copy sold on Amazon: rate × list price − printing cost."""
    return round(royalty_rate(price, marketplace) * price - cost, 2)


def min_price(cost: float, marketplace: Marketplace = "us") -> float:
    """Lowest list price KDP accepts: the royalty at that price must cover the printing cost."""
    threshold = ROYALTY_THRESHOLD[marketplace]
    low = math.ceil(cost / ROYALTY_LOW * 100) / 100
    if low < threshold:
        return low
    return max(threshold, math.ceil(cost / ROYALTY_HIGH * 100) / 100)


# --- Review -----------------------------------------------------------------------


@dataclass
class Issue:
    level: Level
    key: str  # i18n key under "kdp.issue."
    params: dict = field(default_factory=dict)


@dataclass
class Review:
    """A book measured against KDP: the interior it would upload and what to fix first."""

    pages: int
    spine: float
    cost: float | None
    min_price: float | None
    royalty: float | None
    issues: list[Issue]

    @property
    def ready(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)


def _names(page_list: list[Page]) -> str:
    return ", ".join(p.title.strip() or p.original_name for p in page_list)


def _uses_ai(page: Page) -> bool:
    return any(v.n == page.selected and v.engine == "gemini" for v in page.versions)


def review(book: Book) -> Review:
    report = export.preflight(book)
    pages = len(export.sheets(book, report.included))
    market = book.marketplace
    symbol = CURRENCY[market]
    cost = printing_cost(pages, book.kdp_ink, market)
    lowest = min_price(cost, market) if cost is not None else None
    issues: list[Issue] = []

    def add(level: Level, key: str, **params) -> None:
        issues.append(Issue(level, key, params))

    if not report.included:
        add("error", "no_pages")
    page_range = PAGE_RANGE[(book.page_size, book.kdp_ink)]
    if page_range is None:
        add("error", "ink_not_offered")
    elif pages < page_range[0]:
        add("error", "too_few_pages" if book.blank_backs else "too_few_pages_no_backs", pages=pages, min=page_range[0])
    if pages > MAX_PAGES:
        add("error", "too_many_pages", pages=pages, max=MAX_PAGES)
    not_for_sale = [p for p in report.included if p.license in LICENSES_NOT_FOR_SALE]
    if not_for_sale:
        add("error", "license_not_for_sale", names=_names(not_for_sale))
    if not export.fonts_embedded():
        add("error", "fonts")
    if lowest is not None and book.list_price < lowest:
        add("error", "price_too_low", price=lowest, symbol=symbol)
    if not book.blank_backs:
        add("warning", "no_blank_backs")
    if report.not_approved:
        add("warning", "not_approved", names=_names(report.not_approved))
    if report.overflowing:
        add("warning", "overflowing", names=_names(report.overflowing))
    if not book.legal.strip():
        add("warning", "no_legal")
    unknown = [p for p in report.included if p.license == "unknown"]
    if unknown:
        add("warning", "license_unknown", names=_names(unknown))
    without_credit = [p for p in report.included if p.license in LICENSES_WITH_CREDIT and not p.credit.strip()]
    if without_credit:
        add("warning", "missing_credits", names=_names(without_credit))
    share_alike = [p for p in report.included if p.license == "cc_by_sa"]
    if share_alike:
        add("info", "share_alike", names=_names(share_alike))
    if cost is not None and book.list_price < ROYALTY_THRESHOLD[market]:
        add("info", "low_royalty", threshold=ROYALTY_THRESHOLD[market], symbol=symbol)
    art = cover_art.selected(book)
    art_path = cover_art.selected_path(book)
    if art_path:
        with Image.open(art_path) as image:
            ppi = cover_art.print_ppi(image.size, front_art_size(book.page_size))
        if ppi < MIN_PPI:
            add("warning", "cover_art_low_res", ppi=round(ppi), min=MIN_PPI)
    if book.kdp_ink == "black" and book.include_reference_photo:
        add("info", "photos_gray")
    if any(_uses_ai(p) for p in report.included) or (art_path and art.source != "upload"):
        add("info", "ai_disclosure")

    return Review(
        pages=pages,
        spine=spine_width(pages, book.kdp_ink),
        cost=cost,
        min_price=lowest,
        royalty=royalty(book.list_price, cost, market) if cost is not None else None,
        issues=issues,
    )
