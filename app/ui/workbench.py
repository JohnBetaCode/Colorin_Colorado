"""Workbench: one page at a time. Photo, crop and caption on the left; coloring page,
versions and conversion on the right.

Fields save themselves through ``on_change`` callbacks keyed by page id, so they are
already on disk when a button in the same rerun converts or approves the page.
"""

from __future__ import annotations

import streamlit as st
from PIL import Image

from app.core import books, captions, commons, export, gemini, imaging, mosaic, pages, templates, tones
from app.core.config import get_settings
from app.core.i18n import LANGUAGE_NAMES, t
from app.core.schema import (
    BACKGROUNDS,
    LICENSES,
    MOSAIC_CELLS,
    MOSAIC_FILLS,
    STYLES,
    Book,
    Caption,
    Crop,
    Engine,
    MosaicSettings,
    Page,
    Version,
)
from app.ui.common import flash, seed
from app.ui.curve_editor import curve_editor

MIN_CROP = 10  # percent of the photo on each axis
PREVIEW_PX = 1000  # long side of the mosaic solution shown in the workbench
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


def _ask_delete_version(page_id: str, n: int) -> None:
    st.session_state.pending_version_delete = (page_id, n)


def _cancel_delete_version() -> None:
    st.session_state.pending_version_delete = None


def _delete_version(slug: str, page_id: str, n: int) -> None:
    pages.delete_version(slug, page_id, n)
    st.session_state.pending_version_delete = None
    st.session_state.pop(f"version_{page_id}", None)  # re-seeded from the new selection
    flash("success", t("wb.version_deleted", n=n))


def _render_delete_version(book: Book, page: Page) -> None:
    """Delete the version on screen, after a confirmation."""
    if page.selected is None:
        return
    n = page.selected
    if st.session_state.get("pending_version_delete") != (page.id, n):
        st.button(
            t("wb.delete_version", n=n), key=f"delete_version_{page.id}",
            on_click=_ask_delete_version, args=(page.id, n),
        )
        return
    st.warning(t("wb.delete_version_confirm", n=n))
    col_yes, col_no = st.columns(2)
    col_yes.button(
        t("wb.delete_version_yes"), type="primary", width="stretch", key=f"delete_version_yes_{page.id}",
        on_click=_delete_version, args=(book.slug, page.id, n),
    )
    col_no.button(
        t("home.cancel"), width="stretch", key=f"delete_version_no_{page.id}", on_click=_cancel_delete_version
    )


def _approve(slug: str, page_id: str, next_id: str | None) -> None:
    pages.approve(slug, page_id)
    flash("success", t("wb.approved"))
    if next_id:
        st.session_state.wb_page = next_id


MOSAIC_FIELDS = ("fill", "cells", "tones", "columns", "contrast", "brightness", "number_white")


def _mosaic_from_widgets(page_id: str) -> MosaicSettings:
    return MosaicSettings(**{field: st.session_state[f"mosaic_{field}_{page_id}"] for field in MOSAIC_FIELDS})


def _save_mosaic(slug: str, page_id: str) -> None:
    pages.update_page(slug, page_id, mosaic=_mosaic_from_widgets(page_id))


def _mosaic_for_book(book: Book, page_id: str) -> None:
    book.mosaic = _mosaic_from_widgets(page_id)
    books.save_book(book)
    flash("success", t("wb.mosaic_made_default"))


def _render_mosaic_options(book: Book, page: Page) -> None:
    settings = mosaic.settings_for(book, page)
    with st.expander(t("wb.mosaic_options")):
        for field in MOSAIC_FIELDS:
            seed(f"mosaic_{field}_{page.id}", getattr(settings, field))
        save = {"on_change": _save_mosaic, "args": (book.slug, page.id)}
        st.selectbox(
            t("wb.mosaic_fill"), MOSAIC_FILLS, format_func=lambda f: t(f"mosaic_fill.{f}"),
            key=f"mosaic_fill_{page.id}", **save,
        )
        col1, col2 = st.columns(2)
        col1.radio(
            t("wb.mosaic_cells"), MOSAIC_CELLS, format_func=lambda c: t(f"mosaic_cells.{c}"), horizontal=True,
            key=f"mosaic_cells_{page.id}", **save,
        )
        col2.slider(
            t("wb.mosaic_tones"), mosaic.MIN_TONES, mosaic.MAX_TONES, help=t("wb.mosaic_tones_help"),
            key=f"mosaic_tones_{page.id}", **save,
        )
        st.slider(
            t("wb.mosaic_columns"), mosaic.MIN_COLUMNS, mosaic.MAX_COLUMNS["square"],
            help=t("wb.mosaic_columns_help", max=mosaic.MAX_COLUMNS["diagonal"]),
            key=f"mosaic_columns_{page.id}", **save,
        )
        col1, col2 = st.columns(2)
        col1.slider(t("wb.mosaic_contrast"), -mosaic.LIMIT, mosaic.LIMIT, step=5, key=f"mosaic_contrast_{page.id}", **save)
        col2.slider(t("wb.mosaic_brightness"), -mosaic.LIMIT, mosaic.LIMIT, step=5, key=f"mosaic_brightness_{page.id}", **save)
        st.checkbox(
            t("wb.mosaic_number_white"), help=t("wb.mosaic_number_white_help"),
            key=f"mosaic_number_white_{page.id}", **save,
        )
        st.caption(t("wb.mosaic_preview"))
        _render_mosaic_tabs(book, page, draft=True)
        col1, col2 = st.columns(2)
        if col1.button(t("wb.mosaic_new"), type="primary", width="stretch", key=f"mosaic_new_{page.id}"):
            _convert(book, page, "mosaic")
        current = page.selected_version
        if current and current.engine == "mosaic" and col2.button(
            t("wb.mosaic_replace", n=current.n), help=t("wb.mosaic_replace_help", n=current.n),
            width="stretch", key=f"mosaic_replace_{page.id}",
        ):
            _convert(book, page, "mosaic", replace=current.n)
        st.button(
            t("wb.mosaic_make_default"), help=t("wb.mosaic_make_default_help"), key=f"mosaic_default_{page.id}",
            on_click=_mosaic_for_book, args=(book, page.id),
        )


@st.cache_data(max_entries=16, show_spinner=False)
def _mosaic_images(book_json: str, page_json: str, draft: bool) -> tuple[Image.Image, Image.Image]:
    """The mosaic as printed and its solution: the selected version's, or with ``draft`` the one
    the current options make. Keyed by the saved book and page, so each change renders once."""
    book, page = Book.model_validate_json(book_json), Page.model_validate_json(page_json)
    grid, settings = imaging.mosaic_draft(book, page) if draft else export.mosaic_of(book, page)
    solution = mosaic.render_solution(grid, settings).convert("L")
    solution.thumbnail((PREVIEW_PX, PREVIEW_PX))
    return export.mosaic_preview(book, page, grid, settings), solution


def _render_mosaic_tabs(book: Book, page: Page, draft: bool) -> None:
    printed, solution = _mosaic_images(book.model_dump_json(), page.model_dump_json(), draft)
    puzzle_tab, solution_tab = st.tabs([t("wb.mosaic_puzzle"), t("wb.mosaic_solution")])
    puzzle_tab.image(printed, width="stretch")
    solution_tab.image(solution, width="stretch")


def _convert(book: Book, page: Page, engine: Engine, replace: int | None = None) -> None:
    spinner = {"gemini": "wb.converting", "draft": "wb.drafting", "mosaic": "wb.mosaic_drawing"}[engine]
    with st.spinner(t(spinner)):
        try:
            updated = imaging.convert_page(book, page, engine, replace=replace)
        except gemini.GeminiError as exc:
            st.error(t("wb.failed", error=exc))
            return
    st.session_state.pop(f"version_{page.id}", None)
    if replace is None:
        flash("success", t("wb.converted", n=updated.selected))
    else:
        flash("success", t("wb.mosaic_replaced", old=replace, n=updated.selected))
    st.rerun()




def _render_photo(book: Book, page: Page) -> None:
    st.markdown(f"#### {t('wb.photo')}")
    st.image(pages.cropped_photo(book.slug, page), width="stretch")
    crop = page.crop
    seed(f"crop_x_{page.id}", (round(crop.left * 100), round(crop.right * 100)))
    seed(f"crop_y_{page.id}", (round(crop.top * 100), round(crop.bottom * 100)))
    with st.expander(t("wb.crop"), expanded=not crop.is_full or page.curve is not None):
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
        col1, col2 = st.columns(2)
        col1.button(
            t("wb.crop_reset"),
            key=f"crop_reset_{page.id}",
            width="stretch",
            disabled=crop.is_full,
            on_click=_reset_crop,
            args=(book.slug, page.id),
        )
        col2.button(
            t("wb.curves"),
            key=f"curves_toggle_{page.id}",
            width="stretch",
            help=t("wb.curves_help"),
            on_click=_toggle_curves,
            args=(page.id,),
        )
        if st.session_state.get(f"curves_open_{page.id}"):
            _render_curves(book, page)
        elif page.curve is not None:
            st.caption(t("wb.curves_active"))


def _toggle_curves(page_id: str) -> None:
    key = f"curves_open_{page_id}"
    st.session_state[key] = not st.session_state.get(key, False)


def _set_curve(slug: str, page_id: str, points: list[tuple[int, int]] | None) -> None:
    """Save the page's curve; the identity is stored as None (the photo as shot)."""
    points = None if points is None or tones.is_identity(points) else tones.normalized(points)
    pages.update_page(slug, page_id, curve=points)


def _render_curves(book: Book, page: Page) -> None:
    """The curve over the photo's histogram, quick presets, and the photo before and after."""
    st.caption(t("wb.curves_editor_help"))
    plain = pages.cropped_photo(book.slug, page, curve=False)
    plain.thumbnail((600, 600))
    points = tones.normalized(page.curve)
    changed = curve_editor(points, tones.histogram(plain), key=f"curve_{page.id}")
    if changed is not None:
        _set_curve(book.slug, page.id, changed)
        st.rerun()
    columns = st.columns(len(tones.PRESETS) + 1)
    for column, (name, preset) in zip(columns, tones.PRESETS.items()):
        column.button(
            t(f"curves.{name}"), key=f"curve_{name}_{page.id}", width="stretch",
            on_click=_set_curve, args=(book.slug, page.id, preset),
        )
    columns[-1].button(
        t("wb.curves_reset"), key=f"curve_reset_{page.id}", width="stretch", disabled=page.curve is None,
        on_click=_set_curve, args=(book.slug, page.id, None),
    )
    before, after = st.columns(2)
    before.image(plain, caption=t("wb.curves_before"), width="stretch")
    after.image(tones.apply(plain, page.curve), caption=t("wb.curves_after"), width="stretch")


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
    if path and page.is_mosaic:
        _render_mosaic_tabs(book, page, draft=False)
        st.caption(t("wb.mosaic_hidden"))
    elif path:
        st.image(str(path), width="stretch")
        for warning in page.selected_version.warnings:
            st.warning(t(f"warning.{warning}"))
    else:
        st.info(t("wb.not_converted"))

    def version_label(version: Version) -> str:
        if version.mosaic:  # the style means nothing to a mosaic
            detail = t("wb.mosaic_version", columns=version.mosaic.columns, tones=version.mosaic.tones)
        else:
            detail = t(f"style.{version.style}")
        return t("wb.version_label", n=version.n, engine=t(f"engine.{version.engine}"), style=detail)

    if len(page.versions) > 1:
        by_n = {v.n: v for v in page.versions}
        seed(f"version_{page.id}", page.selected)
        st.radio(
            t("wb.versions"),
            list(by_n),
            horizontal=True,
            format_func=lambda n: version_label(by_n[n]),
            key=f"version_{page.id}",
            on_change=_select_version,
            args=(book.slug, page.id),
        )
    _render_delete_version(book, page)

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

    _render_mosaic_options(book, page)

    configured = get_settings().configured
    col1, col2, col3 = st.columns(3)
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
    if col3.button(t("wb.mosaic"), width="stretch", help=t("wb.mosaic_help"), key=f"mosaic_{page.id}"):
        _convert(book, page, "mosaic")

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
