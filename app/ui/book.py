"""Book workspace: sidebar, and the workbench / pages / export / Amazon KDP views."""

from __future__ import annotations

import streamlit as st

from app.core import books, pages, usage
from app.core.config import LANGUAGES
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import AGE_GROUPS, BACKGROUNDS, STYLES, TEMPLATES, Book
from app.ui import export_panel, kdp_panel, pages_grid, workbench
from app.ui.common import flash, language_switch, plain, seed, show_flash

VIEWS = ("workbench", "pages", "export", "kdp")
NO_SECOND_LANGUAGE = "none"  # stored as None; not None itself, which a selectbox shows as empty


def _close_book() -> None:
    st.session_state.current_book = None
    for key in ("view", "last_view", "wb_page"):
        st.session_state.pop(key, None)


def _render_sidebar(book: Book) -> None:
    with st.sidebar:
        st.markdown(f"### {plain(book.title)}")
        st.caption(
            f"{t(f'style.{book.style}')} · {t(f'age.{book.age_group}')} · {LANGUAGE_NAMES[book.language]}"
        )
        spend = usage.summarize([e for e in usage.load_entries() if e.get("book") == book.id])
        if spend["calls"]:
            st.caption(t("book.spend", cost=spend["cost_usd"], images=spend["images"], tokens=spend["tokens"]))

        fields = ("title", "subtitle", "dedication", "template", "style", "age_group", "background", "language")
        for field in fields:
            seed(f"edit_{field}_{book.slug}", getattr(book, field))
        seed(f"edit_second_language_{book.slug}", book.second_language or NO_SECOND_LANGUAGE)
        key = lambda field: f"edit_{field}_{book.slug}"  # noqa: E731
        with st.expander(t("book.edit")):
            with st.form("edit_book"):
                title = st.text_input(t("book.title"), key=key("title"))
                subtitle = st.text_input(t("book.subtitle"), key=key("subtitle"))
                dedication = st.text_area(t("book.dedication"), height=80, key=key("dedication"))
                template = st.selectbox(
                    t("book.template"),
                    TEMPLATES,
                    format_func=lambda k: t(f"template.{k}"),
                    help=t("book.template_help"),
                    key=key("template"),
                )
                style = st.selectbox(t("book.style"), STYLES, format_func=lambda s: t(f"style.{s}"), key=key("style"))
                age_group = st.selectbox(
                    t("book.age_group"), AGE_GROUPS, format_func=lambda a: t(f"age.{a}"), key=key("age_group")
                )
                background = st.selectbox(
                    t("book.background"),
                    BACKGROUNDS,
                    format_func=lambda b: t(f"background.{b}"),
                    key=key("background"),
                )
                language = st.selectbox(
                    t("book.language"),
                    LANGUAGES,
                    format_func=LANGUAGE_NAMES.get,
                    help=t("book.language_help"),
                    key=key("language"),
                )
                second_language = st.selectbox(
                    t("book.second_language"),
                    [NO_SECOND_LANGUAGE, *LANGUAGES],
                    format_func=lambda lang: t("book.no_second_language") if lang == NO_SECOND_LANGUAGE else LANGUAGE_NAMES[lang],
                    help=t("book.second_language_help"),
                    key=key("second_language"),
                )
                if st.form_submit_button(t("book.save"), type="primary"):
                    book.title = title.strip() or book.title
                    book.subtitle = subtitle.strip()
                    book.dedication = dedication.strip()
                    book.template = template
                    book.style, book.age_group, book.background, book.language = style, age_group, background, language
                    book.second_language = None if second_language in (NO_SECOND_LANGUAGE, language) else second_language
                    books.save_book(book)
                    flash("success", t("book.saved"))
                    st.rerun()
            st.caption(t("book.edit_note"))

        st.divider()
        st.button(t("book.back"), width="stretch", on_click=_close_book)


def render_book(book: Book) -> None:
    language_switch()
    _render_sidebar(book)
    show_flash()

    st.title(f"🖍️ {plain(book.title)}")
    if book.subtitle:
        st.caption(plain(book.subtitle))

    page_list = pages.load_pages(book.slug)
    st.session_state.setdefault("view", "workbench" if page_list else "pages")
    st.segmented_control(
        "view", VIEWS, format_func=lambda v: t(f"view.{v}"), key="view", label_visibility="collapsed"
    )
    # Clicking the selected segment again deselects it; stay on the last view.
    view = st.session_state.view or st.session_state.get("last_view", "workbench")
    st.session_state.last_view = view

    if view == "pages":
        pages_grid.render(book, page_list)
    elif view == "export":
        export_panel.render(book)
    elif view == "kdp":
        kdp_panel.render(book)
    else:
        workbench.render(book, page_list)
