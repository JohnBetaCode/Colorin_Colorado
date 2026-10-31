"""Click points on a photo: left click for the subject, right click (or Shift+click) for the
background. The frontend is one static HTML file in ``frontend/point_picker``."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

_component = components.declare_component(
    "point_picker", path=str(Path(__file__).parent / "frontend" / "point_picker")
)


def _data_url(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def point_picker(image: Image.Image, points: list[dict], key: str) -> dict | None:
    """Show ``image`` with ``points`` ({x, y, subject}, percent) and return a new click once,
    as {x, y, subject}, or None. The component keeps returning its last click on every
    rerun, so clicks already handled are recognized by their id and ignored."""
    value = _component(image=_data_url(image), points=points, key=key, default=None)
    seen = f"{key}_seen"
    if not value or st.session_state.get(seen) == value.get("click"):
        return None
    st.session_state[seen] = value["click"]
    return {"x": value["x"], "y": value["y"], "subject": value["subject"]}
