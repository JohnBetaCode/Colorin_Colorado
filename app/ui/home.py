"""Home page: settings, usage, create a book or open an existing one."""

from __future__ import annotations

import streamlit as st

from app.core import books, gemini, i18n, pages, usage
from app.core.config import AUTH_METHODS, LANGUAGES, get_settings, save_settings
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import AGE_GROUPS, STYLES
from app.ui.common import language_switch, seed, show_flash


def _render_settings_panel() -> None:
    settings = get_settings()
    for field in ("auth", "api_key", "project", "text_location", "image_location", "text_model", "image_model"):
        seed(f"settings_{field}", getattr(settings, field))
    with st.expander(t("settings.title"), expanded=not settings.configured):
        st.caption(t("settings.help"))
        with st.form("settings_form"):
            col1, col2 = st.columns(2)
            auth = col1.selectbox(
                t("settings.auth"), AUTH_METHODS, format_func=lambda a: t(f"auth.{a}"), key="settings_auth"
            )
            api_key = col2.text_input(
                t("settings.api_key"), type="password", help=t("settings.api_key_help"), key="settings_api_key"
            )
            col1, col2, col3 = st.columns(3)
            project = col1.text_input(t("settings.project"), key="settings_project")
            text_location = col2.text_input(t("settings.text_location"), key="settings_text_location")
            image_location = col3.text_input(t("settings.image_location"), key="settings_image_location")
            col4, col5 = st.columns(2)
            text_model = col4.text_input(t("settings.text_model"), key="settings_text_model")
            image_model = col5.text_input(t("settings.image_model"), key="settings_image_model")
            save_col, test_col, _ = st.columns([1, 1, 3])
            saved = save_col.form_submit_button(t("settings.save"), type="primary")
            tested = test_col.form_submit_button(t("settings.save_test"))

        if saved or tested:
            save_settings(
                {
                    "GEMINI_AUTH": auth,
                    "GEMINI_API_KEY": api_key.strip(),
                    "GOOGLE_CLOUD_PROJECT": project.strip(),
                    "GOOGLE_CLOUD_LOCATION": text_location.strip(),
                    "GEMINI_IMAGE_LOCATION": image_location.strip(),
                    "GEMINI_TEXT_MODEL": text_model.strip(),
                    "GEMINI_IMAGE_MODEL": image_model.strip(),
                }
            )
            gemini.reset_clients()
            st.success(t("settings.saved"))
        if tested:
            with st.spinner(t("settings.testing")):
                try:
                    st.success(t("settings.ok", reply=gemini.check_connection()))
                except gemini.GeminiError as exc:
                    st.error(t("settings.failed", error=exc))


def _render_usage_panel() -> None:
    with st.expander(t("usage.title")):
        entries = usage.load_entries()
        if not entries:
            st.info(t("usage.empty"))
            return
        totals = usage.summarize(entries)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("usage.calls"), f"{totals['calls']:,}")
        col2.metric(t("usage.images"), f"{totals['images']:,}")
        col3.metric(
            t("usage.tokens"),
            f"{totals['tokens']:,}",
            help=t("usage.tokens_help", input=totals["input_tokens"], output=totals["output_tokens"]),
        )
        col4.metric(t("usage.cost"), f"${totals['cost_usd']:.2f}")
        st.caption(t("usage.note"))
        by_book, by_operation = st.tabs([t("usage.by_book"), t("usage.by_operation")])
        titles = {book.id: book.title for book in books.list_books()}
        with by_book:
            rows = usage.breakdown(entries, "book")
            for row in rows:
                row["book"] = titles.get(row["book"], t("usage.no_book") if row["book"] == "—" else row["book"])
            st.dataframe(rows, width="stretch", hide_index=True)
        with by_operation:
            st.dataframe(usage.breakdown(entries, "operation"), width="stretch", hide_index=True)


def _open_book(slug: str) -> None:
    st.session_state.current_book = slug
    for key in ("view", "last_view", "wb_page"):
        st.session_state.pop(key, None)


def _render_create_form() -> None:
    st.subheader(t("home.new_book"))
    if not get_settings().configured:
        st.info(t("home.unconfigured"))
    with st.form("create_book", clear_on_submit=True):
        title = st.text_input(t("book.title"), placeholder=t("home.title_placeholder"))
        subtitle = st.text_input(t("book.subtitle"), placeholder=t("home.subtitle_placeholder"))
        col1, col2, col3 = st.columns(3)
        style = col1.selectbox(t("book.style"), STYLES, format_func=lambda s: t(f"style.{s}"))
        age_group = col2.selectbox(t("book.age_group"), AGE_GROUPS, index=1, format_func=lambda a: t(f"age.{a}"))
        language = col3.selectbox(
            t("book.language"),
            LANGUAGES,
            index=LANGUAGES.index(i18n.language()),
            format_func=LANGUAGE_NAMES.get,
            help=t("book.language_help"),
        )
        submitted = st.form_submit_button(t("home.create"), type="primary")

    if submitted:
        if not title.strip():
            st.error(t("home.title_required"))
        else:
            book = books.create_book(title, subtitle=subtitle.strip(), style=style, age_group=age_group, language=language)
            _open_book(book.slug)
            st.rerun()


def _render_book_list() -> None:
    st.subheader(t("home.your_books"))
    all_books = books.list_books()
    if not all_books:
        st.info(t("home.no_books"))
        return

    for book in all_books:
        page_list = pages.load_pages(book.slug)
        with st.container(border=True):
            thumb_col, info_col, actions_col = st.columns([1.2, 4, 1])
            with thumb_col:
                thumb = pages.book_thumbnail(book.slug, book.cover_page_id)
                if thumb:
                    st.image(str(thumb), width="stretch")
                else:
                    st.caption(t("home.no_image"))
            with info_col:
                st.markdown(f"**{book.title}**")
                if book.subtitle:
                    st.caption(book.subtitle)
                approved = sum(p.status == "approved" for p in page_list)
                st.caption(
                    " · ".join(
                        [
                            t("home.progress", approved=approved, total=len(page_list)),
                            t(f"style.{book.style}"),
                            t(f"age.{book.age_group}"),
                            LANGUAGE_NAMES[book.language],
                            t("home.created", date=book.created_at[:10]),
                        ]
                    )
                )
            with actions_col:
                st.button(
                    t("home.open"),
                    key=f"open_{book.slug}",
                    type="primary",
                    width="stretch",
                    on_click=_open_book,
                    args=(book.slug,),
                )
                if st.button(t("home.delete"), key=f"delete_{book.slug}", width="stretch"):
                    st.session_state.pending_delete = book.slug

    pending = st.session_state.get("pending_delete")
    target = books.load_book(pending) if pending else None
    if target:
        st.warning(t("home.confirm_delete", title=target.title))
        col_yes, col_no, _ = st.columns([1, 1, 4])
        if col_yes.button(t("home.yes_delete"), type="primary"):
            books.delete_book(pending)
            st.session_state.pending_delete = None
            st.rerun()
        if col_no.button(t("home.cancel")):
            st.session_state.pending_delete = None
            st.rerun()


def render_home() -> None:
    language_switch()
    st.title("🖍️ Colorín Colorado")
    st.caption(t("home.tagline"))
    show_flash()
    _render_settings_panel()
    _render_usage_panel()
    _render_create_form()
    st.divider()
    _render_book_list()
