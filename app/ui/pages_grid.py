"""Pages view: upload photos and manage the book's pages (order, cover, inclusion, deletion)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from PIL import Image

from app.core import books, commons, imaging, pages
from app.core.config import get_settings
from app.core.i18n import t
from app.core.schema import Book, Page
from app.ui.common import flash, seed

COLUMNS = 4
THUMB_PX = 480


def _square(path: Path) -> Image.Image:
    """Thumbnail padded to a white square, so every card in a row has the same height."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((THUMB_PX, THUMB_PX))
    square = Image.new("RGB", (THUMB_PX, THUMB_PX), "white")
    square.paste(image, ((THUMB_PX - image.width) // 2, (THUMB_PX - image.height) // 2))
    return square


def _render_uploader(book: Book, expanded: bool) -> None:
    with st.expander(t("pages.add_photos"), expanded=expanded):
        # A new key empties the uploader once its files are stored.
        key = f"uploader_{st.session_state.get('upload_round', 0)}"
        files = st.file_uploader(
            t("pages.upload_label"), type=list(pages.UPLOAD_TYPES), accept_multiple_files=True, key=key
        )
        if files and st.button(t("pages.add_n", n=len(files)), type="primary"):
            progress = st.progress(0.0)
            failed = []
            for i, file in enumerate(files, start=1):
                try:
                    pages.add_photo(book.slug, file.name, file.getvalue())
                except ValueError:
                    failed.append(file.name)
                progress.progress(i / len(files))
            st.session_state.upload_round = st.session_state.get("upload_round", 0) + 1
            if failed:
                flash("warning", t("pages.unreadable", names=", ".join(failed)))
            else:
                flash("success", t("pages.added", n=len(files)))
            st.rerun()
        col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
        url = col1.text_input(
            t("pages.commons"),
            placeholder=t("wb.source_url_placeholder"),
            key=f"commons_url_{st.session_state.get('upload_round', 0)}",
        )
        if col2.button(t("pages.commons_add"), width="stretch") and url.strip():
            try:
                page = commons.add_page(book.slug, url)
            except (commons.CommonsError, ValueError) as exc:
                st.error(t("wb.commons_failed", error=exc))
                return
            st.session_state.upload_round = st.session_state.get("upload_round", 0) + 1
            flash("success", t("pages.commons_added", name=page.original_name, license=t(f"license.{page.license}")))
            st.rerun()


def _open(page_id: str) -> None:
    st.session_state.wb_page = page_id
    st.session_state.view = "workbench"


def _toggle(slug: str, page_id: str) -> None:
    pages.update_page(slug, page_id, in_book=st.session_state[f"in_book_{page_id}"])


def _make_cover(book: Book, page_id: str) -> None:
    book.cover_page_id = page_id
    books.save_book(book)


def _render_card(book: Book, page: Page, index: int, total: int) -> None:
    with st.container(border=True):
        image = pages.selected_path(book.slug, page) or pages.original_path(book.slug, page)
        st.image(_square(image), width="stretch")
        st.markdown(f"**{index + 1}. {page.title.strip() or page.original_name}**")
        badges = [t(f"status.{page.status}")]
        if page.id == book.cover_page_id:
            badges.append(t("pages.is_cover"))
        st.caption(" · ".join(badges))
        seed(f"in_book_{page.id}", page.in_book)
        st.checkbox(
            t("pages.in_book"),
            key=f"in_book_{page.id}",
            on_change=_toggle,
            args=(book.slug, page.id),
        )
        left, right, edit, delete = st.columns(4)
        left.button(
            "◀", key=f"left_{page.id}", help=t("pages.move_left"), disabled=index == 0,
            on_click=pages.move_page, args=(book.slug, page.id, -1),
        )
        right.button(
            "▶", key=f"right_{page.id}", help=t("pages.move_right"), disabled=index == total - 1,
            on_click=pages.move_page, args=(book.slug, page.id, 1),
        )
        edit.button("✏️", key=f"edit_{page.id}", help=t("pages.open"), on_click=_open, args=(page.id,))
        if delete.button("🗑️", key=f"delete_{page.id}", help=t("pages.delete")):
            st.session_state.pending_page_delete = page.id
        st.button(
            t("pages.make_cover"),
            key=f"cover_{page.id}",
            width="stretch",
            disabled=page.selected is None or page.id == book.cover_page_id,
            on_click=_make_cover,
            args=(book, page.id),
        )


def _render_delete_confirmation(book: Book, page_list: list[Page]) -> None:
    pending = st.session_state.get("pending_page_delete")
    page = next((p for p in page_list if p.id == pending), None)
    if not page:
        return
    st.warning(t("pages.confirm_delete", title=page.title.strip() or page.original_name))
    col_yes, col_no, _ = st.columns([1, 1, 4])
    if col_yes.button(t("home.yes_delete"), type="primary"):
        pages.delete_page(book.slug, page.id)
        if book.cover_page_id == page.id:
            book.cover_page_id = None
            books.save_book(book)
        st.session_state.pending_page_delete = None
        flash("success", t("pages.deleted"))
        st.rerun()
    if col_no.button(t("home.cancel")):
        st.session_state.pending_page_delete = None
        st.rerun()


def _convert_all(book: Book, pending: list[Page], engine: str) -> None:
    progress = st.progress(0.0, text=t("pages.converting_all", done=0, total=len(pending)))

    def on_done(count: int, page: Page, error: str | None) -> None:
        progress.progress(count / len(pending), text=t("pages.converting_all", done=count, total=len(pending)))

    failures = imaging.convert_pages(book, pending, engine, on_done)
    if failures:
        names = ", ".join(p.title.strip() or p.original_name for p, _ in failures)
        flash("warning", t("pages.converted_all_failed", done=len(pending) - len(failures), names=names, error=failures[0][1]))
    else:
        flash("success", t("pages.converted_all", n=len(pending)))
    st.rerun()


def _render_convert_all(book: Book, page_list: list[Page]) -> None:
    pending = [p for p in page_list if p.status == "pending" and p.in_book]
    if not pending:
        return
    with st.container(border=True):
        st.markdown(t("pages.convert_all_title", n=len(pending)))
        configured = get_settings().configured
        col1, col2, col3 = st.columns(3)
        if col1.button(
            t("pages.convert_all_ai", cost=len(pending) * imaging.AI_PAGE_COST_USD),
            type="primary",
            disabled=not configured,
            help=t("pages.convert_all_ai_help") if configured else t("wb.ai_disabled"),
            width="stretch",
        ):
            _convert_all(book, pending, "gemini")
        if col2.button(t("pages.convert_all_draft"), help=t("wb.draft_help"), width="stretch"):
            _convert_all(book, pending, "draft")
        if col3.button(t("pages.convert_all_mosaic"), help=t("wb.mosaic_help"), width="stretch"):
            _convert_all(book, pending, "mosaic")


def render(book: Book, page_list: list[Page]) -> None:
    _render_uploader(book, expanded=not page_list)
    if not page_list:
        return
    _render_convert_all(book, page_list)
    approved = sum(p.status == "approved" for p in page_list)
    st.caption(t("pages.summary", total=len(page_list), approved=approved))
    _render_delete_confirmation(book, page_list)
    for start in range(0, len(page_list), COLUMNS):
        for offset, column in enumerate(st.columns(COLUMNS)):
            index = start + offset
            if index < len(page_list):
                with column:
                    _render_card(book, page_list[index], index, len(page_list))
