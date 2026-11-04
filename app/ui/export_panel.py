"""Export view: PDF options, a preflight of what the book will contain, build, preview, download."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.core import books, export, page_templates, pages
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import EXTRAS, PAGE_SIZES, Book, Page
from app.ui.common import flash, plain, seed

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
    return plain(", ".join(p.title.strip() or p.original_name for p in page_list))


AREA_SIDES = ("left", "top", "right", "bottom")


def _template_label(book: Book, option: str) -> str:
    if option == page_templates.NO_TEMPLATE:
        return t("wb.page_template_none")
    return page_templates.name(book, option, t)


def _save_default_template(slug: str) -> None:
    book = books.load_book(slug)
    value = st.session_state[f"export_page_template_{slug}"]
    book.page_template = None if value == page_templates.NO_TEMPLATE else value
    books.save_book(book)


def _save_area(slug: str, template_id: str) -> None:
    area = tuple(st.session_state[f"template_{side}_{template_id}"] / 100 for side in AREA_SIDES)
    try:
        page_templates.set_area(books.load_book(slug), template_id, area)
    except ValueError:
        flash("warning", t("export.page_template_area_small"))


def _delete_template(slug: str, template_id: str) -> None:
    page_templates.delete_upload(books.load_book(slug), template_id)
    flash("success", t("export.page_template_deleted"))


def _render_page_templates(book: Book) -> None:
    st.markdown(f"##### {t('export.page_templates')}")
    st.caption(t("export.page_templates_help"))
    options = [page_templates.NO_TEMPLATE, *page_templates.choices(book)]
    seed(f"export_page_template_{book.slug}", book.page_template if book.page_template in options else options[0])
    st.selectbox(
        t("export.page_template_default"),
        options,
        format_func=lambda o: _template_label(book, o),
        key=f"export_page_template_{book.slug}",
        on_change=_save_default_template,
        args=(book.slug,),
    )
    size = export.content_box(book)[2:]
    with st.expander(t("export.page_templates_gallery")):
        columns = st.columns(6)
        for i, template_id in enumerate(page_templates.choices(book)):
            columns[i % 6].image(
                page_templates.thumbnail(book, template_id, size, px=220), caption=plain(_template_label(book, template_id))
            )
    with st.expander(t("export.page_template_upload")):
        st.caption(t("export.page_template_upload_help"))
        round_ = st.session_state.get("template_upload_round", 0)  # a new key empties the uploader
        file = st.file_uploader(t("export.page_template_upload_label"), type=list(pages.UPLOAD_TYPES), key=f"template_file_{round_}")
        name = st.text_input(t("export.page_template_name"), key=f"template_name_{round_}")
        if file and st.button(t("export.page_template_add"), type="primary"):
            try:
                updated = page_templates.add_upload(book, file.getvalue(), name or file.name.rsplit(".", 1)[0])
            except ValueError as exc:
                st.error(t("export.page_template_unreadable", error=exc))
                return
            st.session_state.template_upload_round = round_ + 1
            flash("success", t("export.page_template_added", name=plain(updated.page_templates[-1].name)))
            st.rerun()
    for template in book.page_templates:
        with st.expander(t("export.page_template_edit", name=plain(template.name))):
            controls, picture = st.columns([3, 2])
            for side, value, low, high in zip(AREA_SIDES, template.area, (0, 0, 50, 50), (50, 50, 100, 100)):
                seed(f"template_{side}_{template.id}", round(value * 100))
                controls.slider(
                    t(f"export.page_template_{side}"),
                    low,
                    high,
                    format="%d %%",
                    key=f"template_{side}_{template.id}",
                    on_change=_save_area,
                    args=(book.slug, template.id),
                )
            picture.image(page_templates.thumbnail(book, template.id, size, px=260), width="stretch")
            controls.button(
                t("export.page_template_delete"),
                key=f"template_delete_{template.id}",
                on_click=_delete_template,
                args=(book.slug, template.id),
            )


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
    _render_page_templates(book)
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
