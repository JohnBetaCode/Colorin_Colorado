"""A tone curve editor like GIMP's Curves: drag points over the photo's histogram. The
frontend is one static HTML file in ``frontend/curve_editor``."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_component = components.declare_component(
    "curve_editor", path=str(Path(__file__).parent / "frontend" / "curve_editor")
)


def curve_editor(points: list[tuple[int, int]], histogram: list[float], key: str) -> list[tuple[int, int]] | None:
    """Show the curve through ``points`` over ``histogram`` and return the new points once,
    after a drag, a new point or a removed one; None otherwise. The component keeps returning
    its last change on every rerun, so changes already handled are recognized by their id."""
    value = _component(points=[list(p) for p in points], histogram=histogram, key=key, default=None)
    seen = f"{key}_seen"
    if not value or st.session_state.get(seen) == value.get("change"):
        return None
    st.session_state[seen] = value["change"]
    return [(int(x), int(y)) for x, y in value["points"]]
