import re
import string
from pathlib import Path

from app.core import kdp, lineart
from app.core.config import AUTH_METHODS
from app.core.i18n import LANGUAGE_NAMES, STRINGS, t
from app.core.schema import (
    AGE_GROUPS,
    ART_MODES,
    ART_SOURCES,
    BACKGROUNDS,
    COVER_COLORS,
    ENGINES,
    INKS,
    PAGE_SIZES,
    STATUSES,
    STYLES,
)

APP = Path(__file__).resolve().parents[1] / "app"


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_key_has_every_language_with_the_same_placeholders():
    for key, texts in STRINGS.items():
        assert set(texts) == set(LANGUAGE_NAMES), key
        assert _fields(texts["es"]) == _fields(texts["en"]), key


def test_every_literal_key_used_in_the_code_exists():
    used = set()
    for path in APP.rglob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*["']([a-z_0-9.+-]+)["']""", path.read_text()))
    assert used, "no t() calls found"
    assert sorted(used - set(STRINGS)) == []


def test_every_option_and_warning_has_a_label():
    prefixes = {
        "style": STYLES,
        "age": AGE_GROUPS,
        "background": BACKGROUNDS,
        "status": STATUSES,
        "engine": ENGINES,
        "page_size": PAGE_SIZES,
        "warning": lineart.WARNINGS,
        "ink": INKS,
        "cover_color": COVER_COLORS,
        "kdp.trim": PAGE_SIZES,
        "auth": AUTH_METHODS,
        "art_mode": ART_MODES,
        "art_mode_help": ART_MODES,
        "art_source": ART_SOURCES,
    }
    missing = [f"{p}.{v}" for p, values in prefixes.items() for v in values if f"{p}.{v}" not in STRINGS]
    assert missing == []


def test_every_kdp_issue_has_a_label():
    keys = re.findall(r'\badd\(\s*"\w+",\s*"(\w+)"', Path(kdp.__file__).read_text())
    assert keys, "no issues found in kdp.review"
    assert sorted(f"kdp.issue.{k}" for k in keys if f"kdp.issue.{k}" not in STRINGS) == []


def test_t_formats_and_switches_language():
    assert t("pages.added", lang="es", n=3) == "Se agregaron 3 fotos."
    assert t("pages.added", lang="en", n=3) == "Added 3 photos."
    assert t("pdf.owner", lang="en") == "This book belongs to:"
