from io import BytesIO

import pytest
from PIL import Image

from app.core import books, commons, pages

TOUCAN = {
    "query": {
        "pages": [
            {
                "title": "File:Keel-billed Toucan.jpg",
                "imageinfo": [
                    {
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Keel-billed_Toucan.jpg",
                        "thumburl": "https://upload.wikimedia.org/thumb/toucan-2048.jpg",
                        "url": "https://upload.wikimedia.org/toucan.jpg",
                        "extmetadata": {
                            "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:BG">Bernard&nbsp;Gagnon</a>'},
                            "LicenseShortName": {"value": "CC BY-SA 3.0"},
                            "License": {"value": "cc-by-sa-3.0"},
                        },
                    }
                ],
            }
        ]
    }
}


@pytest.mark.parametrize(
    "url, title",
    [
        ("https://commons.wikimedia.org/wiki/File:Keel-billed_Toucan.jpg", "File:Keel-billed Toucan.jpg"),
        ("https://es.wikipedia.org/wiki/Archivo:Tuc%C3%A1n.jpg", "File:Tucán.jpg"),
        ("https://upload.wikimedia.org/wikipedia/commons/a/ab/Toucan.jpg", "File:Toucan.jpg"),
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Toucan.jpg/800px-Toucan.jpg", "File:Toucan.jpg"),
        ("https://example.com/toucan.jpg", ""),
    ],
)
def test_file_title_from_links(url, title):
    assert commons.file_title(url) == title


@pytest.mark.parametrize(
    "code, name, expected",
    [
        ("cc0", "CC0", "public_domain"),
        ("pd", "Public domain", "public_domain"),
        ("cc-by-2.0", "CC BY 2.0", "cc_by"),
        ("cc-by-sa-4.0", "CC BY-SA 4.0", "cc_by_sa"),
        ("cc-by-nc-sa-2.0", "CC BY-NC-SA 2.0", "non_commercial"),
        ("cc-by-nd-4.0", "CC BY-ND 4.0", "no_derivatives"),
        ("gfdl", "GFDL", "unknown"),
    ],
)
def test_license_mapping(code, name, expected):
    assert commons.license_of(code, name) == expected


def test_add_page_from_commons(monkeypatch, photo):
    monkeypatch.setattr(commons, "_get_json", lambda params: TOUCAN)
    monkeypatch.setattr(commons, "download", lambda found: photo)
    book = books.create_book("Aves del jardín")
    page = commons.add_page(book.slug, "https://commons.wikimedia.org/wiki/File:Keel-billed_Toucan.jpg")
    assert page.original_name == "Keel-billed Toucan.jpg"
    assert (page.credit, page.license) == ("Bernard Gagnon, CC BY-SA 3.0", "cc_by_sa")
    assert page.source_url.endswith("File:Keel-billed_Toucan.jpg")
    assert pages.original_path(book.slug, page).exists()


def test_lookup_rejects_other_links_and_missing_files(monkeypatch):
    with pytest.raises(commons.CommonsError):
        commons.lookup("https://example.com/toucan.jpg")
    monkeypatch.setattr(commons, "_get_json", lambda params: {"query": {"pages": [{"title": "File:X.jpg", "missing": True}]}})
    with pytest.raises(commons.CommonsError):
        commons.lookup("https://commons.wikimedia.org/wiki/File:X.jpg")
