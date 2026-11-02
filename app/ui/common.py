"""Pieces shared by the home page and the book workspace."""

from __future__ import annotations

import re

import streamlit as st

from app.core import i18n
from app.core.config import LANGUAGES, save_settings
from app.core.i18n import LANGUAGE_NAMES


_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def plain(text: str) -> str:
    """Escape Markdown in text someone typed or imported, so it shows as typed.

    Titles go into ``st.markdown``, captions and messages; unescaped, a title like
    ``![](https://…)`` would load an image from anywhere.
    """
    return _MARKDOWN.sub(r"\\\1", text)


def _save_language() -> None:
    language = st.session_state.ui_language
    save_settings({"UI_LANGUAGE": language})
    i18n.set_language(language)


def language_switch() -> None:
    """Sidebar selector for the UI language, persisted to config/.env."""
    st.session_state.setdefault("ui_language", i18n.language())
    st.sidebar.selectbox(
        "🌐 Idioma · Language",
        LANGUAGES,
        format_func=LANGUAGE_NAMES.get,
        key="ui_language",
        on_change=_save_language,
    )


def seed(key: str, value) -> None:
    """Give a keyed widget its starting value through session state.

    Never pass ``value=``/``index=`` to a widget whose starting value comes from saved
    data: Streamlit hashes those arguments into the widget's identity, so once an
    ``on_change`` saves the new value the widget is re-created and the next click on
    the page is lost. Seed the key instead and call the widget without them.
    """
    if key not in st.session_state:
        st.session_state[key] = value


def flash(kind: str, message: str) -> None:
    """Queue a message (``success``, ``error``...) for the next run."""
    st.session_state.flash = (kind, message)


def show_flash() -> None:
    message = st.session_state.pop("flash", None)
    if message:
        kind, text = message
        getattr(st, kind)(text)
