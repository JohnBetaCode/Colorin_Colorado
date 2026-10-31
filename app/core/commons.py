"""Photos and their credits from Wikimedia Commons.

``lookup`` reads a file page's author and license through the Commons API, so a page's
credit and license can be filled from its link; ``download`` fetches the photo itself,
2048 px wide at most. The license is mapped to the app's ``License`` so the KDP review
can tell whether the photo may be used in a book for sale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import unquote, urlparse

import httpx

from app.core import pages
from app.core.schema import License, Page

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia asks every client to identify itself.
HEADERS = {"User-Agent": "ColorinColorado/1.0 (coloring-book app; https://github.com/JohnBetaCode/Colorin_Colorado)"}
TIMEOUT = 20
DOWNLOAD_WIDTH = 2048  # pages.ORIGINAL_MAX_PX


class CommonsError(RuntimeError):
    """Raised when a link is not a Commons file or the lookup fails."""


@dataclass
class CommonsPhoto:
    title: str  # "File:Keel-billed toucan.jpg"
    author: str
    license_name: str  # as Commons writes it: "CC BY-SA 4.0", "CC0", "Public domain"
    license: License
    page_url: str
    image_url: str  # a JPEG/PNG at most DOWNLOAD_WIDTH wide

    @property
    def credit(self) -> str:
        return ", ".join(part for part in (self.author, self.license_name) if part)


def file_title(url: str) -> str:
    """``File:<name>`` from a Commons or Wikipedia file page, or an upload.wikimedia.org link."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = unquote(parsed.path)
    if host == "upload.wikimedia.org":
        parts = [p for p in path.split("/") if p]
        if "thumb" in parts:  # .../thumb/a/ab/Name.jpg/800px-Name.jpg
            return f"File:{parts[parts.index('thumb') + 3]}"
        return f"File:{parts[-1]}" if parts else ""
    if host.endswith("wikimedia.org") or host.endswith("wikipedia.org"):
        match = re.search(r"/wiki/((?:File|Archivo|Fichier|Datei|Image):.+)$", path)
        if match:
            return "File:" + match.group(1).split(":", 1)[1].replace("_", " ")
    return ""


def license_of(code: str, name: str) -> License:
    """The app's license for Commons' machine code (``cc-by-sa-4.0``) and short name."""
    text = f"{code} {name}".lower().replace("_", "-").replace(" ", "-")
    if "-nc" in text:
        return "non_commercial"
    if "-nd" in text:
        return "no_derivatives"
    if "cc0" in text or text.startswith("pd") or "public-domain" in text or "-pd-" in f"-{text}-":
        return "public_domain"
    if "by-sa" in text:
        return "cc_by_sa"
    if "cc-by" in text:
        return "cc_by"
    return "unknown"  # GFDL and others need checking by hand


def _plain(html: str) -> str:
    """Commons metadata is HTML; keep the text."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html or ""))).strip()


def _get_json(params: dict) -> dict:
    try:
        response = httpx.get(API, params=params, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CommonsError(f"Wikimedia Commons did not answer: {exc}") from exc


def lookup(url: str) -> CommonsPhoto:
    title = file_title(url)
    if not title:
        raise CommonsError("Not a Wikimedia Commons file link.")
    data = _get_json(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
            "iiurlwidth": DOWNLOAD_WIDTH,
            "format": "json",
            "formatversion": 2,
        }
    )
    found = (data.get("query") or {}).get("pages") or []
    if not found or found[0].get("missing") or not found[0].get("imageinfo"):
        raise CommonsError(f"{title} is not on Wikimedia Commons.")
    info = found[0]["imageinfo"][0]
    meta = {key: value.get("value", "") for key, value in (info.get("extmetadata") or {}).items()}
    name = _plain(meta.get("LicenseShortName", ""))
    return CommonsPhoto(
        title=found[0].get("title", title),
        author=_plain(meta.get("Artist", "")),
        license_name=name,
        license=license_of(meta.get("License", ""), name),
        page_url=info.get("descriptionurl", url),
        image_url=info.get("thumburl") or info.get("url", ""),
    )


def download(photo: CommonsPhoto) -> bytes:
    try:
        response = httpx.get(photo.image_url, headers=HEADERS, timeout=60, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        raise CommonsError(f"Could not download the photo: {exc}") from exc


def add_page(slug: str, url: str) -> Page:
    """Add a Commons photo as a new page of the book, with its credit, license and link."""
    photo = lookup(url)
    page = pages.add_photo(slug, photo.title.removeprefix("File:"), download(photo))
    return pages.update_page(slug, page.id, credit=photo.credit, license=photo.license, source_url=photo.page_url)
