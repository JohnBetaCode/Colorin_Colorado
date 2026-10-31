"""Workbench: one page at a time. Photo, crop and caption on the left; coloring page,
versions and conversion on the right.

Fields save themselves through ``on_change`` callbacks keyed by page id, so they are
already on disk when a button in the same rerun converts or approves the page.
"""

from __future__ import annotations

import streamlit as st

from app.core import captions, commons, export, gemini, imaging, pages, templates
from app.core.config import get_settings
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import BACKGROUNDS, LICENSES, STYLES, Book, Caption, Crop, Engine, Page
from app.ui.common import flash, seed

MIN_CROP = 10  # percent of the photo on each axis
# Option meaning "use the book's setting" (stored as None). Not None itself: a selectbox
# whose state is None shows as empty.
BOOK_DEFAULT = "book"


def _go(page_id: str) -> None:
    st.session_state.wb_page = page_id


def _save_field(slug: str, page_id: str, field: str) -> None:
    value = st.session_state[f"{field}_{page_id}"]
    if field in ("style", "background") and value == BOOK_DEFAULT:
        value = None
    pages.update_page(slug, page_id, **{field: value})


def _save_crop(slug: str, page_id: str) -> None:
    left, right = st.session_state[f"crop_x_{page_id}"]
    top, bottom = st.session_state[f"crop_y_{page_id}"]
    if right - left >= MIN_CROP and bottom - top >= MIN_CROP:
        pages.set_crop(slug, page_id, Crop(left=left / 100, top=top / 100, right=right / 100, bottom=bottom / 100))


TRANSLATION_FIELDS = ("title", "subtitle", "info")


def _save_translation(slug: str, page_id: str) -> None:
    values = {field: st.session_state[f"tr_{field}_{page_id}"] for field in TRANSLATION_FIELDS}
    pages.update_page(slug, page_id, translation=Caption(**values))


def _forget_translation_widgets(page_list: list[Page]) -> None:
    """Drop the translation fields' state so they show the stored text on the next run."""
    for page in page_list:
        for field in TRANSLATION_FIELDS:
            st.session_state.pop(f"tr_{field}_{page.id}", None)


def _render_translation(book: Book, page: Page, page_list: list[Page]) -> None:
    if len(book.languages) < 2:
        return
    language = LANGUAGE_NAMES[book.languages[1]]
    with st.expander(t("wb.translation", language=language), expanded=not page.translation.is_empty):
        for field in TRANSLATION_FIELDS:
            seed(f"tr_{field}_{page.id}", getattr(page.translation, field))
            widget = st.text_area if field == "info" else st.text_input
            widget(
                t(f"wb.caption_{field}"),
                key=f"tr_{field}_{page.id}",
                on_change=_save_translation,
                args=(book.slug, page.id),
            )
        configured = get_settings().configured
        missing = captions.missing_translations(book, page_list)
        col1, col2 = st.columns(2)
        one = col1.button(
            t("wb.translate"),
            key=f"translate_{page.id}",
            width="stretch",
            disabled=not configured or not page.has_caption,
            help=None if configured else t("wb.ai_disabled"),
        )
        everything = col2.button(
            t("wb.translate_all", n=len(missing)),
            key=f"translate_all_{page.id}",
            width="stretch",
            disabled=not configured or not missing,
        )
        if not (one or everything):
            return
        todo = [page] if one else missing
        failed = []
        with st.spinner(t("wb.translating")):
            for item in todo:
                try:
                    captions.translate_page(book, item)
                except gemini.GeminiError as exc:
                    failed.append(str(exc))
        _forget_translation_widgets(todo)
        if failed:
            flash("error", t("wb.translate_failed", error=failed[0]))
        else:
            flash("success", t("wb.translated", n=len(todo)))
        st.rerun()


def _use_template(book: Book, page_id: str) -> None:
    labels = templates.labels(book)
    pages.update_page(book.slug, page_id, info=labels)
    st.session_state[f"info_{page_id}"] = labels


def _fill_from_commons(slug: str, page_id: str) -> None:
    try:
        photo = commons.lookup(st.session_state[f"source_url_{page_id}"])
    except commons.CommonsError as exc:
        flash("error", t("wb.commons_failed", error=exc))
        return
    pages.update_page(slug, page_id, credit=photo.credit, license=photo.license, source_url=photo.page_url)
    st.session_state[f"credit_{page_id}"] = photo.credit
    st.session_state[f"license_{page_id}"] = photo.license
    st.session_state[f"source_url_{page_id}"] = photo.page_url
    flash("success", t("wb.commons_filled"))


def _reset_crop(slug: str, page_id: str) -> None:
    pages.set_crop(slug, page_id, Crop())
    st.session_state.pop(f"crop_x_{page_id}", None)
    st.session_state.pop(f"crop_y_{page_id}", None)


def _select_version(slug: str, page_id: str) -> None:
    pages.select_version(slug, page_id, st.session_state[f"version_{page_id}"])


def _approve(slug: str, page_id: str, next_id: str | None) -> None:
    pages.approve(slug, page_id)
    flash("success", t("wb.approved"))
    if next_id:
        st.session_state.wb_page = next_id


def _convert(book: Book, page: Page, engine: Engine) -> None:
    with st.spinner(t("wb.converting") if engine == "gemini" else t("wb.drafting")):
        try:
            updated = imaging.convert_page(book, page, engine)
        except gemini.GeminiError as exc:
            st.error(t("wb.failed", error=exc))
            return
    st.session_state.pop(f"version_{page.id}", None)
    flash("success", t("wb.converted", n=updated.selected))
    st.rerun()




def _render_photo(book: Book, page: Page) -> None:
    st.markdown(f"#### {t('wb.photo')}")
    st.image(pages.cropped_photo(book.slug, page), width="stretch")
    crop = page.crop
    seed(f"crop_x_{page.id}", (round(crop.left * 100), round(crop.right * 100)))
    seed(f"crop_y_{page.id}", (round(crop.top * 100), round(crop.bottom * 100)))
    with st.expander(t("wb.crop"), expanded=not crop.is_full):
        st.caption(t("wb.crop_help"))
        st.slider(
            t("wb.crop_horizontal"),
            0,
            100,
            key=f"crop_x_{page.id}",
            on_change=_save_crop,
            args=(book.slug, page.id),
        )
        st.slider(
            t("wb.crop_vertical"),
            0,
            100,
            key=f"crop_y_{page.id}",
            on_change=_save_crop,
            args=(book.slug, page.id),
        )
        st.button(
            t("wb.crop_reset"),
            key=f"crop_reset_{page.id}",
            disabled=crop.is_full,
            on_click=_reset_crop,
            args=(book.slug, page.id),
        )


def _render_caption(book: Book, page: Page) -> None:
    st.markdown(f"#### {t('wb.caption')}")
    st.caption(t("wb.caption_help"))
    col1, col2 = st.columns(2)
    for col, field in ((col1, "title"), (col2, "subtitle")):
        seed(f"{field}_{page.id}", getattr(page, field))
        col.text_input(
            t(f"wb.caption_{field}"),
            placeholder=t(f"template_subtitle.{book.template}") if field == "subtitle" else t("wb.caption_title_placeholder"),
            key=f"{field}_{page.id}",
            on_change=_save_field,
            args=(book.slug, page.id, field),
        )
    labels = templates.labels(book)
    if labels and not page.info.strip():
        st.button(t("wb.use_template"), key=f"template_{page.id}", on_click=_use_template, args=(book, page.id))
    seed(f"info_{page.id}", page.info)
    st.text_area(
        t("wb.caption_info"),
        placeholder=labels or t("wb.caption_info_placeholder"),
        height=150,
        key=f"info_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "info"),
    )
    if not export.caption_fits(book, page):
        st.warning(t("wb.caption_too_long"))
    col1, col2 = st.columns(2)
    seed(f"credit_{page.id}", page.credit)
    col1.text_input(
        t("wb.credit"),
        placeholder=t("wb.credit_placeholder"),
        help=t("wb.credit_help"),
        key=f"credit_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "credit"),
    )
    seed(f"license_{page.id}", page.license)
    col2.selectbox(
        t("wb.license"),
        LICENSES,
        format_func=lambda license: t(f"license.{license}"),
        help=t("wb.license_help"),
        key=f"license_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "license"),
    )
    col1, col2 = st.columns([3, 2], vertical_alignment="bottom")
    seed(f"source_url_{page.id}", page.source_url)
    col1.text_input(
        t("wb.source_url"),
        placeholder=t("wb.source_url_placeholder"),
        key=f"source_url_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "source_url"),
    )
    col2.button(
        t("wb.commons_fill"),
        key=f"commons_{page.id}",
        width="stretch",
        on_click=_fill_from_commons,
        args=(book.slug, page.id),
    )


def _render_coloring_page(book: Book, page: Page, next_id: str | None) -> None:
    st.markdown(f"#### {t('wb.coloring_page')} · {t(f'status.{page.status}')}")
    path = pages.selected_path(book.slug, page)
    if path:
        st.image(str(path), width="stretch")
        version = next(v for v in page.versions if v.n == page.selected)
        for warning in version.warnings:
            st.warning(t(f"warning.{warning}"))
    else:
        st.info(t("wb.not_converted"))

    if len(page.versions) > 1:
        by_n = {v.n: v for v in page.versions}
        seed(f"version_{page.id}", page.selected)
        st.radio(
            t("wb.versions"),
            list(by_n),
            horizontal=True,
            format_func=lambda n: t(
                "wb.version_label", n=n, engine=t(f"engine.{by_n[n].engine}"), style=t(f"style.{by_n[n].style}")
            ),
            key=f"version_{page.id}",
            on_change=_select_version,
            args=(book.slug, page.id),
        )

    col1, col2 = st.columns(2)
    seed(f"style_{page.id}", page.style or BOOK_DEFAULT)
    col1.selectbox(
        t("wb.style"),
        [BOOK_DEFAULT, *STYLES],
        format_func=lambda s: (
            t("wb.book_default", value=t(f"style.{book.style}")) if s == BOOK_DEFAULT else t(f"style.{s}")
        ),
        key=f"style_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "style"),
    )
    seed(f"background_{page.id}", page.background or BOOK_DEFAULT)
    col2.selectbox(
        t("wb.background"),
        [BOOK_DEFAULT, *BACKGROUNDS],
        format_func=lambda b: (
            t("wb.book_default", value=t(f"background.{book.background}")) if b == BOOK_DEFAULT else t(f"background.{b}")
        ),
        key=f"background_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "background"),
    )
    seed(f"instructions_{page.id}", page.instructions)
    st.text_area(
        t("wb.instructions"),
        placeholder=t("wb.instructions_placeholder"),
        height=68,
        key=f"instructions_{page.id}",
        on_change=_save_field,
        args=(book.slug, page.id, "instructions"),
    )

    configured = get_settings().configured
    col1, col2 = st.columns(2)
    if col1.button(
        t("wb.regenerate") if page.versions else t("wb.convert"),
        type="primary",
        width="stretch",
        disabled=not configured,
        help=None if configured else t("wb.ai_disabled"),
        key=f"convert_{page.id}",
    ):
        _convert(book, page, "gemini")
    if col2.button(t("wb.draft"), width="stretch", help=t("wb.draft_help"), key=f"draft_{page.id}"):
        _convert(book, page, "draft")

    col1, col2 = st.columns(2)
    col1.button(
        t("wb.approve"),
        width="stretch",
        disabled=page.selected is None or page.status == "approved",
        key=f"approve_{page.id}",
        on_click=_approve,
        args=(book.slug, page.id, None),
    )
    col2.button(
        t("wb.approve_next"),
        width="stretch",
        disabled=page.selected is None or next_id is None,
        key=f"approve_next_{page.id}",
        on_click=_approve,
        args=(book.slug, page.id, next_id),
    )


def render(book: Book, page_list: list[Page]) -> None:
    if not page_list:
        st.info(t("wb.empty"))
        return

    ids = [p.id for p in page_list]
    if st.session_state.get("wb_page") not in ids:
        st.session_state.wb_page = ids[0]
    index = ids.index(st.session_state.wb_page)
    page = page_list[index]
    next_id = ids[index + 1] if index + 1 < len(ids) else None

    prev_col, select_col, next_col = st.columns([1, 8, 1])
    prev_col.button(
        "◀", key="wb_prev", width="stretch", disabled=index == 0, on_click=_go, args=(ids[max(index - 1, 0)],)
    )
    # Labels must not include titles or status: they are part of the widget's identity.
    select_col.selectbox(
        "page",
        ids,
        key="wb_page",
        format_func=lambda pid: t("wb.page_of", n=ids.index(pid) + 1, total=len(ids)),
        label_visibility="collapsed",
    )
    next_col.button(
        "▶", key="wb_next", width="stretch", disabled=next_id is None, on_click=_go, args=(next_id or page.id,)
    )

    photo_col, art_col = st.columns(2, gap="large")
    with photo_col:
        _render_photo(book, page)
        _render_caption(book, page)
        _render_translation(book, page, page_list)
    with art_col:
        _render_coloring_page(book, page, next_id)
