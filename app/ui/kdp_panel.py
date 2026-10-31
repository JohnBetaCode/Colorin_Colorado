"""Amazon KDP view: interior ink and price, what KDP charges and pays, what to fix before
uploading, the upload settings, and the wraparound cover with its front image."""

from __future__ import annotations

import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

from app.core import books, captions, cover, cover_art, export, gemini, kdp, marketing, pages
from app.core.config import get_settings
from app.core.i18n import t
from app.core.schema import ART_MODES, COVER_COLORS, INKS, MARKETPLACES, Book, Listing, Page
from app.ui.common import flash, seed

# Front image option meaning "no cover image": the cover page's line art (stored as None).
LINE_ART = "line"
PREVIEW_PX = 600


def _key(book: Book, field: str) -> str:
    return f"kdp_{field}_{book.slug}"


def _save(slug: str, field: str) -> None:
    book = books.load_book(slug)
    setattr(book, field, st.session_state[_key(book, field)])
    books.save_book(book)


def _select_art(slug: str) -> None:
    book = books.load_book(slug)
    value = st.session_state[_key(book, "cover_art_selected")]
    cover_art.select(book, None if value == LINE_ART else value)


def _new_art(book: Book, n: int) -> None:
    """Show the new image as selected on the next run."""
    st.session_state.pop(_key(book, "cover_art_selected"), None)
    flash("success", t("kdp.art_added", n=n))
    st.rerun()


LISTING_FIELDS = ("description", "keywords", "categories", "reading_age")
LIST_FIELDS = ("keywords", "categories")  # one per line in their text area


def _listing_value(listing: Listing, field: str) -> str:
    value = getattr(listing, field)
    return "\n".join(value) if field in LIST_FIELDS else value


def _save_listing(slug: str) -> None:
    book = books.load_book(slug)
    values = {}
    for field in LISTING_FIELDS:
        text = st.session_state[_key(book, f"listing_{field}")]
        values[field] = [line.strip() for line in text.splitlines() if line.strip()] if field in LIST_FIELDS else text
    book.listing = Listing(**values)
    books.save_book(book)


def _render_listing(book: Book) -> None:
    st.markdown(f"#### {t('kdp.listing')}")
    st.caption(t("kdp.listing_help"))
    configured = get_settings().configured
    if st.button(t("kdp.listing_suggest"), disabled=not configured, help=None if configured else t("wb.ai_disabled")):
        with st.spinner(t("kdp.listing_suggesting")):
            try:
                book.listing = captions.suggest_listing(book, pages.load_pages(book.slug))
            except gemini.GeminiError as exc:
                st.error(t("kdp.listing_failed", error=exc))
                return
        books.save_book(book)
        for field in LISTING_FIELDS:
            st.session_state.pop(_key(book, f"listing_{field}"), None)
        flash("success", t("kdp.listing_done"))
        st.rerun()
    for field in LISTING_FIELDS:
        seed(_key(book, f"listing_{field}"), _listing_value(book.listing, field))
    st.text_area(t("kdp.listing_description"), height=220, key=_key(book, "listing_description"), on_change=_save_listing, args=(book.slug,))
    col1, col2 = st.columns(2)
    col1.text_area(
        t("kdp.listing_keywords", n=len(book.listing.keywords)),
        height=200,
        help=t("kdp.listing_keywords_help"),
        key=_key(book, "listing_keywords"),
        on_change=_save_listing,
        args=(book.slug,),
    )
    col2.text_area(
        t("kdp.listing_categories"),
        height=120,
        key=_key(book, "listing_categories"),
        on_change=_save_listing,
        args=(book.slug,),
    )
    col2.text_input(t("kdp.listing_reading_age"), key=_key(book, "listing_reading_age"), on_change=_save_listing, args=(book.slug,))
    too_long = [k for k in book.listing.keywords if len(k) > captions.MAX_KEYWORD_CHARS]
    if len(book.listing.keywords) > captions.MAX_KEYWORDS or too_long:
        st.warning(t("kdp.listing_keywords_warning", max=captions.MAX_KEYWORDS, chars=captions.MAX_KEYWORD_CHARS))


def _render_listing_images(book: Book, included: list[Page]) -> None:
    st.markdown(f"#### {t('kdp.images')}")
    st.caption(t("kdp.images_help"))
    if st.button(t("kdp.images_build")):
        with st.spinner(t("kdp.images_building")):
            try:
                marketing.export_listing_images(book, included)
            except Exception as exc:
                st.error(t("kdp.images_failed", error=exc))
    archives = sorted(marketing.marketing_dir(book).glob("*.zip"), key=lambda f: f.stat().st_mtime)
    if not archives:
        return
    latest = archives[-1]
    with zipfile.ZipFile(latest) as archive:
        names = sorted(archive.namelist(), key=["mockup.jpg", "inside.jpg", "front.jpg"].index)
        columns = st.columns([2, 3, 1.4])
        for column, name in zip(columns, names):
            column.image(archive.read(name), caption=name, width="stretch")
    st.download_button(t("kdp.images_download"), data=latest.read_bytes(), file_name=latest.name, mime="application/zip")


def _latest_cover(book: Book) -> Path | None:
    files = sorted(cover.covers_dir(book).glob("*.pdf"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


def _render_numbers(book: Book, review: kdp.Review) -> None:
    symbol = kdp.CURRENCY[book.marketplace]
    col1, col2, col3 = st.columns(3)
    seed(_key(book, "kdp_ink"), book.kdp_ink)
    col1.selectbox(
        t("kdp.ink"),
        INKS,
        format_func=lambda ink: t(f"ink.{ink}"),
        help=t("kdp.ink_help"),
        key=_key(book, "kdp_ink"),
        on_change=_save,
        args=(book.slug, "kdp_ink"),
    )
    seed(_key(book, "marketplace"), book.marketplace)
    col2.selectbox(
        t("kdp.marketplace"),
        MARKETPLACES,
        format_func=lambda market: t(f"marketplace.{market}"),
        key=_key(book, "marketplace"),
        on_change=_save,
        args=(book.slug, "marketplace"),
    )
    seed(_key(book, "list_price"), book.list_price)
    col3.number_input(
        t("kdp.price", symbol=symbol),
        min_value=0.0,
        max_value=kdp.MAX_PRICE,
        step=1.0,
        format="%.2f",
        help=t("kdp.price_help", symbol=symbol, threshold=kdp.ROYALTY_THRESHOLD[book.marketplace]),
        key=_key(book, "list_price"),
        on_change=_save,
        args=(book.slug, "list_price"),
    )
    money = lambda value: "—" if value is None else f"{symbol}{value:.2f}"  # noqa: E731
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("kdp.pages"), review.pages)
    col2.metric(t("kdp.spine"), f"{review.spine:.3f} in")
    col3.metric(t("kdp.cost"), money(review.cost))
    col4.metric(t("kdp.royalty"), money(review.royalty))
    if review.min_price is not None:
        st.caption(t("kdp.min_price", price=review.min_price, symbol=symbol))


def _render_checks(book: Book, review: kdp.Review) -> None:
    st.markdown(f"#### {t('kdp.checks')}")
    if review.ready:
        st.success(t("kdp.ready"))
    for issue in review.issues:
        getattr(st, issue.level)(t(f"kdp.issue.{issue.key}", **issue.params))
    st.markdown(f"#### {t('kdp.upload')}")
    st.markdown(
        t("kdp.upload_steps", trim=t(f"kdp.trim.{book.page_size}"), ink=t(f"ink.{book.kdp_ink}"), pages=review.pages)
    )


def _render_upload(book: Book) -> None:
    width, height = kdp.front_art_size(book.page_size)
    st.caption(t("kdp.art_upload_help", width=round(width * kdp.MIN_PPI), height=round(height * kdp.MIN_PPI)))
    # A new key empties the uploader once the image is stored.
    key = f"art_uploader_{st.session_state.get('art_upload_round', 0)}"
    file = st.file_uploader(t("kdp.art_upload_label"), type=list(pages.UPLOAD_TYPES), key=key)
    if file and st.button(t("kdp.art_use"), type="primary"):
        try:
            updated = cover_art.add_upload(book, file.getvalue())
        except ValueError:
            st.error(t("kdp.art_unreadable"))
            return
        st.session_state.art_upload_round = st.session_state.get("art_upload_round", 0) + 1
        _new_art(book, updated.cover_art_selected)


def _render_generate(book: Book, included: list[Page]) -> None:
    mode = st.radio(
        t("kdp.art_mode"),
        ART_MODES,
        format_func=lambda m: t(f"art_mode.{m}"),
        horizontal=True,
        key=_key(book, "art_mode"),
    )
    st.caption(t(f"art_mode_help.{mode}"))
    page_ids: list[str] = []
    if mode == "collage":
        titles = {p.id: p.title.strip() or p.original_name for p in included}
        key = _key(book, "art_pages")
        default = list(titles)[: cover_art.MAX_COLLAGE_PAGES]
        st.session_state[key] = [pid for pid in st.session_state.get(key, default) if pid in titles]
        page_ids = st.multiselect(
            t("kdp.art_pages", max=cover_art.MAX_COLLAGE_PAGES),
            list(titles),
            format_func=titles.get,
            max_selections=cover_art.MAX_COLLAGE_PAGES,
            key=key,
        )
    text = st.text_area(
        t("kdp.art_text") if mode == "text" else t("kdp.art_extra"),
        placeholder=t("kdp.art_text_placeholder") if mode == "text" else t("kdp.art_extra_placeholder"),
        height=90,
        key=_key(book, f"art_text_{mode}"),
    )
    configured = get_settings().configured
    clicked = st.button(
        t("kdp.art_generate"),
        type="primary",
        disabled=not configured,
        help=None if configured else t("wb.ai_disabled"),
    )
    st.caption(t("kdp.art_cost"))
    if not clicked:
        return
    if mode == "text" and not text.strip():
        st.error(t("kdp.art_need_text"))
        return
    if mode == "collage" and not page_ids:
        st.error(t("kdp.art_need_pages"))
        return
    with st.spinner(t("kdp.art_generating")):
        try:
            updated = cover_art.generate(book, mode, text, page_ids)
        except gemini.GeminiError as exc:
            st.error(t("kdp.art_failed", error=exc))
            return
    _new_art(book, updated.cover_art_selected)


def _render_cover_art(book: Book, included: list[Page]) -> None:
    st.markdown(f"##### {t('kdp.art')}")
    sources = {art.n: art.source for art in book.cover_art}
    seed(_key(book, "cover_art_selected"), book.cover_art_selected if book.cover_art_selected in sources else LINE_ART)
    col1, col2 = st.columns([3, 2])
    col1.radio(
        t("kdp.art_choice"),
        [LINE_ART, *sources],
        format_func=lambda o: (
            t("kdp.art_line") if o == LINE_ART else t("kdp.art_version", n=o, source=t(f"art_source.{sources[o]}"))
        ),
        key=_key(book, "cover_art_selected"),
        on_change=_select_art,
        args=(book.slug,),
    )
    path = cover_art.selected_path(book)
    if path:
        with Image.open(path) as image:
            image.thumbnail((PREVIEW_PX, PREVIEW_PX))
            col2.image(image.convert("RGB"), width="stretch")
    upload_tab, ai_tab = st.tabs([t("kdp.art_upload_tab"), t("kdp.art_ai_tab")])
    with upload_tab:
        _render_upload(book)
    with ai_tab:
        _render_generate(book, included)


def _render_cover(book: Book, review: kdp.Review) -> None:
    st.markdown(f"#### {t('kdp.cover')}")
    width, height = kdp.cover_size(review.pages, book.kdp_ink, book.page_size)
    st.caption(t("kdp.cover_help", width=width, height=height, spine=review.spine))
    _render_cover_art(book, export.preflight(book).included)
    st.markdown(f"##### {t('kdp.cover_text')}")
    seed(_key(book, "cover_color"), book.cover_color)
    st.selectbox(
        t("kdp.cover_color"),
        COVER_COLORS,
        format_func=lambda color: t(f"cover_color.{color}"),
        key=_key(book, "cover_color"),
        on_change=_save,
        args=(book.slug, "cover_color"),
    )
    seed(_key(book, "back_text"), book.back_text)
    st.text_area(
        t("kdp.back_text"),
        placeholder=t("kdp.back_text_placeholder"),
        height=120,
        key=_key(book, "back_text"),
        on_change=_save,
        args=(book.slug, "back_text"),
    )
    if st.button(t("kdp.build_cover"), type="primary"):
        with st.spinner(t("kdp.building_cover")):
            try:
                cover.export_cover_pdf(book)
            except Exception as exc:
                st.error(t("kdp.cover_failed", error=exc))

    latest = _latest_cover(book)
    if latest:
        built_for = cover.cover_pages(latest)
        if built_for != review.pages:
            st.warning(t("kdp.cover_stale", old=built_for, new=review.pages))
        st.download_button(
            t("kdp.download_cover"), data=latest.read_bytes(), file_name=latest.name, mime="application/pdf"
        )
        st.caption(t("kdp.cover_latest", name=latest.name, size=latest.stat().st_size / 1e6))
        st.pdf(latest.read_bytes(), height=600)


def render(book: Book) -> None:
    st.caption(t("kdp.intro"))
    review = kdp.review(book)
    _render_numbers(book, review)
    st.divider()
    _render_checks(book, review)
    st.divider()
    _render_listing(book)
    if any(issue.key == "no_pages" for issue in review.issues):
        return
    st.divider()
    _render_cover(book, review)
    st.divider()
    _render_listing_images(book, export.preflight(book).included)
