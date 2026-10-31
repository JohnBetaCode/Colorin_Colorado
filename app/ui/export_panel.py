"""Export view: PDF options, a preflight of what the book will contain, build, preview, download."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.core import books, export
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import EXTRAS, PAGE_SIZES, Book, Page
from app.ui.common import seed

FIRST_PAGE = "first"  # cover option stored as None; not None itself, which a selectbox shows as empty


def _save_option(slug: str, field: str) -> None:
    book = books.load_book(slug)
    value = st.session_state[f"export_{field}_{slug}"]
    setattr(book, field, None if value == FIRST_PAGE else value)
    books.save_book(book)


def _toggle_extra(slug: str, extra: str) -> None:
    book = books.load_book(slug)
    chosen = set(book.extras)
    if st.session_state[f"extra_{extra}_{slug}"]:
        chosen.add(extra)
    else:
        chosen.discard(extra)
    book.extras = [e for e in EXTRAS if e in chosen]
    books.save_book(book)


def _save_dots_page(slug: str) -> None:
    book = books.load_book(slug)
    value = st.session_state[f"export_dots_page_{slug}"]
    book.dots_page_id = None if value == FIRST_PAGE else value
    books.save_book(book)


def _render_extras(book: Book, report: export.Preflight) -> None:
    st.markdown(f"##### {t('export.extras')}")
    st.caption(t("export.extras_help"))
    col1, col2 = st.columns(2)
    for i, extra in enumerate(EXTRAS):
        seed(f"extra_{extra}_{book.slug}", extra in book.extras)
        (col1 if i % 2 == 0 else col2).checkbox(
            t(f"extra.{extra}"), key=f"extra_{extra}_{book.slug}", on_change=_toggle_extra, args=(book.slug, extra)
        )
    if "dots" in book.extras and report.included:
        titles = {p.id: p.title.strip() or p.original_name for p in report.included}
        options = [FIRST_PAGE, *titles]
        seed(f"export_dots_page_{book.slug}", book.dots_page_id if book.dots_page_id in titles else FIRST_PAGE)
        st.selectbox(
            t("export.dots_page"),
            options,
            format_func=lambda pid: t("export.dots_auto") if pid == FIRST_PAGE else titles[pid],
            key=f"export_dots_page_{book.slug}",
            on_change=_save_dots_page,
            args=(book.slug,),
        )
    for extra in report.extras_missing:
        st.info(t(f"export.extra_missing.{extra}"))


def _names(page_list: list[Page]) -> str:
    return ", ".join(p.title.strip() or p.original_name for p in page_list)


def _latest_export(book: Book) -> Path | None:
    files = sorted(export.exports_dir(book).glob("*.pdf"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


def _render_options(book: Book, report: export.Preflight) -> None:
    col1, col2 = st.columns(2)
    seed(f"export_page_size_{book.slug}", book.page_size)
    col1.selectbox(
        t("export.page_size"),
        PAGE_SIZES,
        format_func=lambda s: t(f"page_size.{s}"),
        key=f"export_page_size_{book.slug}",
        on_change=_save_option,
        args=(book.slug, "page_size"),
    )
    cover_options = [FIRST_PAGE, *(p.id for p in report.included)]
    titles = {p.id: p.title.strip() or p.original_name for p in report.included}
    seed(f"export_cover_page_id_{book.slug}", book.cover_page_id if book.cover_page_id in cover_options else FIRST_PAGE)
    col2.selectbox(
        t("export.cover"),
        cover_options,
        format_func=lambda pid: t("export.cover_first") if pid == FIRST_PAGE else titles[pid],
        key=f"export_cover_page_id_{book.slug}",
        on_change=_save_option,
        args=(book.slug, "cover_page_id"),
    )
    for field, label, help_key in (
        ("include_reference_photo", "export.include_photo", None),
        ("include_owner_page", "export.owner_page", None),
        ("blank_backs", "export.blank_backs", "export.blank_backs_help"),
    ):
        seed(f"export_{field}_{book.slug}", getattr(book, field))
        st.checkbox(
            t(label),
            help=t(help_key) if help_key else None,
            key=f"export_{field}_{book.slug}",
            on_change=_save_option,
            args=(book.slug, field),
        )
    _render_extras(book, report)
    seed(f"export_legal_{book.slug}", book.legal)
    st.text_area(
        t("export.legal"),
        placeholder=t("export.legal_placeholder"),
        help=t("export.legal_help"),
        height=100,
        key=f"export_legal_{book.slug}",
        on_change=_save_option,
        args=(book.slug, "legal"),
    )
    st.caption(t("export.labels", language=LANGUAGE_NAMES[book.language]))


def _render_preflight(report: export.Preflight) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric(t("export.included"), len(report.included))
    col2.metric(t("export.not_approved"), len(report.not_approved))
    col3.metric(t("export.skipped"), len(report.without_version))
    if report.not_approved:
        st.info(t("export.not_approved_list", names=_names(report.not_approved)))
    if report.without_version:
        st.info(t("export.skipped_list", names=_names(report.without_version)))
    if report.overflowing:
        st.warning(t("export.overflow_list", names=_names(report.overflowing)))


def render(book: Book) -> None:
    report = export.preflight(book)
    _render_options(book, report)
    st.divider()
    _render_preflight(report)

    if not report.included:
        st.info(t("export.nothing"))
        return
    if st.button(t("export.build"), type="primary"):
        with st.spinner(t("export.building")):
            try:
                export.export_book_pdf(book)
            except Exception as exc:
                st.error(t("export.failed", error=exc))

    latest = _latest_export(book)
    if latest:
        st.download_button(
            t("export.download"), data=latest.read_bytes(), file_name=latest.name, mime="application/pdf"
        )
        st.caption(t("export.latest", name=latest.name, size=latest.stat().st_size / 1e6))
        st.pdf(latest.read_bytes(), height=900)
