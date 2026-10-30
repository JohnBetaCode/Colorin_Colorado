"""Colorín Colorado — Streamlit entry point."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.core import books, i18n
from app.core.config import get_settings
from app.ui.book import render_book
from app.ui.home import render_home

st.set_page_config(page_title="Colorín Colorado", page_icon="🖍️", layout="wide")


def main() -> None:
    i18n.set_language(get_settings().ui_language)
    slug = st.session_state.get("current_book")
    if slug:
        book = books.load_book(slug)
        if book is None:
            st.session_state.current_book = None
            st.rerun()
        render_book(book)
    else:
        render_home()


main()
