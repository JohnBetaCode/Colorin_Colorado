"""Home page: settings, usage, create a book or open an existing one."""

from __future__ import annotations

import streamlit as st

from app.core import books, gemini, i18n, local_image, pages, stable_diffusion, templates, usage
from app.core.config import (
    AUTH_METHODS,
    LANGUAGES,
    LOCAL_PAGE_SIZES,
    SD_SIZE_RANGE,
    SD_STEPS_RANGE,
    get_settings,
    save_settings,
)
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import AGE_GROUPS, STYLES, TEMPLATES
from app.ui.common import flash, language_switch, plain, seed, show_flash


def _forget_api_key() -> None:
    save_settings({"GEMINI_API_KEY": ""})
    gemini.reset_clients()
    st.session_state.pop("settings_api_key", None)


def _render_gemini_settings() -> None:
    settings = get_settings()
    for field in ("auth", "project", "text_location", "image_location", "text_model", "image_model"):
        seed(f"settings_{field}", getattr(settings, field))
    # The saved API key never goes to the browser: the field starts empty, and an empty field
    # keeps the saved key.
    seed("settings_api_key", "")
    st.caption(t("settings.help"))
    with st.form("settings_form"):
        col1, col2 = st.columns(2)
        auth = col1.selectbox(
            t("settings.auth"), AUTH_METHODS, format_func=lambda a: t(f"auth.{a}"), key="settings_auth"
        )
        api_key = col2.text_input(
            t("settings.api_key"),
            type="password",
            placeholder=t("settings.api_key_saved", tail=settings.api_key[-4:]) if settings.api_key else "",
            help=t("settings.api_key_help"),
            key="settings_api_key",
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

    if settings.api_key:
        st.button(t("settings.api_key_forget"), on_click=_forget_api_key)
    if saved or tested:
        values = {
            "GEMINI_AUTH": auth,
            "GOOGLE_CLOUD_PROJECT": project.strip(),
            "GOOGLE_CLOUD_LOCATION": text_location.strip(),
            "GEMINI_IMAGE_LOCATION": image_location.strip(),
            "GEMINI_TEXT_MODEL": text_model.strip(),
            "GEMINI_IMAGE_MODEL": image_model.strip(),
        }
        if api_key.strip():
            values["GEMINI_API_KEY"] = api_key.strip()
        save_settings(values)
        gemini.reset_clients()
        st.success(t("settings.saved"))
    if tested:
        with st.spinner(t("settings.testing")):
            try:
                st.success(t("settings.ok", reply=gemini.check_connection()))
            except gemini.GeminiError as exc:
                st.error(t("settings.failed", error=exc))


def _render_sd_settings() -> None:
    settings = get_settings()
    seed("settings_sd_url", settings.sd_url)
    seed("settings_sd_steps", settings.sd_steps)
    seed("settings_sd_size", settings.sd_size)
    st.caption(t("settings.sd_help"))
    with st.form("sd_settings_form"):
        url = st.text_input(t("settings.sd_url"), placeholder="http://192.168.1.20:8081", key="settings_sd_url")
        col1, col2 = st.columns(2)
        steps = col1.slider(t("settings.sd_steps"), *SD_STEPS_RANGE, help=t("settings.sd_steps_help"), key="settings_sd_steps")
        size = col2.slider(
            t("settings.sd_size"), *SD_SIZE_RANGE, step=64, help=t("settings.sd_size_help"), key="settings_sd_size"
        )
        save_col, test_col, _ = st.columns([1, 1, 3])
        saved = save_col.form_submit_button(t("settings.save"), type="primary")
        tested = test_col.form_submit_button(t("settings.save_test"))
    if saved or tested:
        save_settings(
            {"STABLE_DIFFUSION_URL": url.strip().rstrip("/"), "STABLE_DIFFUSION_STEPS": str(steps), "STABLE_DIFFUSION_SIZE": str(size)}
        )
        st.success(t("settings.saved"))
    if tested:
        with st.spinner(t("settings.sd_testing")):
            try:
                st.success(t("settings.sd_ok", state=stable_diffusion.check_connection()))
            except stable_diffusion.StableDiffusionError as exc:
                st.error(t("settings.failed", error=exc))


def _render_local_status(fresh: bool = False) -> None:
    """The local GPU server's state, in the UI language."""
    url = get_settings().local_url
    try:
        info = local_image.health(max_age=0 if fresh else 15)
    except local_image.LocalImageError:
        st.warning(t("settings.local_unreachable", url=url))
        return
    status = info.get("status")
    model, gpu = info.get("model") or "?", info.get("gpu") or "GPU"
    if status in ("ready", "idle"):
        st.success(t("settings.local_ready", model=model, gpu=gpu))
    elif status == "downloading" and info.get("progress"):
        progress = info["progress"]
        st.info(t("settings.local_downloading", done=progress.get("downloaded_gb", 0),
                  total=progress.get("total_gb", 0), percent=progress.get("percent") or 0))
    elif status in ("checking", "loading", "downloading"):
        st.info(t("settings.local_loading", model=model))
    else:
        st.error(t("settings.local_error", error=info.get("error") or status))
    if local_image.is_non_commercial(info.get("model")):
        st.caption(t("settings.local_license", model=model))


def _render_local_settings() -> None:
    settings = get_settings()
    seed("settings_local_url", settings.local_url)
    seed("settings_local_size", settings.local_size)
    st.caption(t("settings.local_help"))
    with st.form("local_settings_form"):
        col1, col2 = st.columns([2, 1])
        url = col1.text_input(t("settings.local_url"), help=t("settings.local_url_help"), key="settings_local_url")
        size = col2.selectbox(
            t("settings.local_size"), LOCAL_PAGE_SIZES, format_func=lambda s: t(f"settings.local_size_{s}"),
            help=t("settings.local_size_help"), key="settings_local_size",
        )
        save_col, test_col, _ = st.columns([1, 1, 3])
        saved = save_col.form_submit_button(t("settings.save"), type="primary")
        tested = test_col.form_submit_button(t("settings.save_test"))
    if saved or tested:
        save_settings({"LOCAL_IMAGE_URL": url.strip().rstrip("/"), "LOCAL_IMAGE_PAGE_SIZE": size})
        st.success(t("settings.saved"))
    _render_local_status(fresh=bool(tested))


def _render_settings_panel() -> None:
    settings = get_settings()
    any_engine = settings.configured or settings.sd_configured or local_image.available()
    with st.expander(t("settings.title"), expanded=not any_engine):
        gemini_tab, local_tab, sd_tab = st.tabs([t("settings.tab_gemini"), t("settings.tab_local"), t("settings.tab_sd")])
        with gemini_tab:
            _render_gemini_settings()
        with local_tab:
            _render_local_settings()
        with sd_tab:
            _render_sd_settings()


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
    settings = get_settings()
    if not (settings.configured or settings.sd_configured or local_image.available()):
        st.info(t("home.unconfigured"))
    with st.form("create_book", clear_on_submit=True):
        title = st.text_input(t("book.title"), placeholder=t("home.title_placeholder"))
        subtitle = st.text_input(t("book.subtitle"), placeholder=t("home.subtitle_placeholder"))
        template = st.selectbox(
            t("book.template"), TEMPLATES, format_func=lambda k: t(f"template.{k}"), help=t("book.template_help")
        )
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
            book = books.create_book(
                title,
                subtitle=subtitle.strip(),
                template=template,
                background=templates.BACKGROUND[template],
                style=style,
                age_group=age_group,
                language=language,
            )
            _open_book(book.slug)
            st.rerun()


def _duplicate(slug: str) -> None:
    source = books.load_book(slug)
    copy = books.duplicate_book(slug, t("home.copy_title", title=source.title))
    flash("success", t("home.duplicated", title=plain(copy.title)))


def _render_import() -> None:
    with st.expander(t("home.import")):
        st.caption(t("home.import_help"))
        # A new key empties the uploader once the book is imported.
        key = f"import_{st.session_state.get('import_round', 0)}"
        file = st.file_uploader(t("home.import_label"), type=["zip"], key=key)
        if file and st.button(t("home.import_button"), type="primary"):
            try:
                book = books.import_zip(file.getvalue())
            except ValueError as exc:
                st.error(t("home.import_failed", error=exc))
                return
            st.session_state.import_round = st.session_state.get("import_round", 0) + 1
            flash("success", t("home.imported", title=plain(book.title)))
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
                st.markdown(f"**{plain(book.title)}**")
                if book.subtitle:
                    st.caption(plain(book.subtitle))
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
                st.button(
                    t("home.duplicate"),
                    key=f"duplicate_{book.slug}",
                    width="stretch",
                    on_click=_duplicate,
                    args=(book.slug,),
                )
                if st.session_state.get("zip_ready") == book.slug:
                    st.download_button(
                        t("home.download_zip"),
                        data=books.export_zip(book.slug),
                        file_name=f"{book.slug}.zip",
                        mime="application/zip",
                        key=f"zip_download_{book.slug}",
                        width="stretch",
                        on_click="ignore",
                    )
                elif st.button(t("home.zip"), key=f"zip_{book.slug}", help=t("home.zip_help"), width="stretch"):
                    st.session_state.zip_ready = book.slug
                    st.rerun()
                if st.button(t("home.delete"), key=f"delete_{book.slug}", width="stretch"):
                    st.session_state.pending_delete = book.slug

    pending = st.session_state.get("pending_delete")
    target = books.load_book(pending) if pending else None
    if target:
        st.warning(t("home.confirm_delete", title=plain(target.title)))
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
    _render_import()
    st.divider()
    _render_book_list()
