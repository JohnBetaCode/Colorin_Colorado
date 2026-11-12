import base64
import json
from io import BytesIO
from types import SimpleNamespace as NS

import pytest
import requests
from PIL import Image, ImageDraw

from app.core import books, config, imaging, kdp, lineart, local_image, pages, usage
from app.core.schema import Version

from .conftest import png_bytes

QWEN = "Qwen/Qwen-Image-2.1"


def _drawing(size: tuple[int, int]) -> bytes:
    """What the server sends back: a few black outlines on white."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), outline="black", width=6)
    draw.rectangle((20, 20, size[0] - 20, size[1] - 20), outline="black", width=6)
    return png_bytes(image)


class FakeServer:
    """Answers like local_image/server.py; ``fail`` lists what the next calls do (a status or an exception)."""

    def __init__(self, model=QWEN, status="ready"):
        self.model, self.status = model, status
        self.fail = []
        self.posts, self.gets = [], []

    def post(self, url, json, timeout):
        self.posts.append(NS(url=url, json=json, timeout=timeout))
        if self.fail:
            outcome = self.fail.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return NS(status_code=outcome, json=lambda: {"detail": "downloading the model weights: 3 of 33 GB"},
                      text="error", content=b"", headers={})
        return NS(status_code=200, content=_drawing((600, 800)), headers={"X-Model": self.model})

    def get(self, url, timeout):
        self.gets.append(url)
        if self.status is None:
            raise requests.ConnectionError("Name or service not known")
        return NS(json=lambda: {"status": self.status, "model": self.model, "gpu": "Test GPU"},
                  raise_for_status=lambda: None)


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_IMAGE_URL", "http://gpu.test:8000/")
    monkeypatch.delenv("LOCAL_IMAGE_PAGE_SIZE", raising=False)
    monkeypatch.setattr(usage, "USAGE_FILE", tmp_path / "usage.jsonl")
    monkeypatch.setattr(local_image, "_health_cache", None)
    fake = FakeServer()
    monkeypatch.setattr(local_image.requests, "post", fake.post)
    monkeypatch.setattr(local_image.requests, "get", fake.get)
    return fake


def test_settings_default_to_the_compose_service_at_1k(monkeypatch):
    for key in ("LOCAL_IMAGE_URL", "LOCAL_IMAGE_PAGE_SIZE"):
        monkeypatch.delenv(key, raising=False)
    settings = config.get_settings()
    assert (settings.local_url, settings.local_size) == ("http://local-image:8000", "1k")
    monkeypatch.setenv("LOCAL_IMAGE_URL", " http://localhost:8602/ ")
    monkeypatch.setenv("LOCAL_IMAGE_PAGE_SIZE", "huge")
    settings = config.get_settings()
    assert (settings.local_url, settings.local_size) == ("http://localhost:8602", "1k")
    monkeypatch.setenv("LOCAL_IMAGE_PAGE_SIZE", "2K")
    assert config.get_settings().local_size == "2k"


def test_the_photo_is_the_reference_and_the_page_is_free(server, tmp_path):
    png, model = local_image.edit_image(Image.new("RGB", (1200, 900), "gray"), "Make it a coloring page.", "4:3")
    sent = server.posts[0]
    assert sent.url == "http://gpu.test:8000/generate" and sent.timeout >= 600
    assert (sent.json["prompt"], sent.json["aspect_ratio"], sent.json["size"]) == ("Make it a coloring page.", "4:3", "1k")
    reference = Image.open(BytesIO(base64.b64decode(sent.json["reference_images"][0])))
    assert reference.format == "JPEG" and reference.size == (1200, 900)
    assert model == QWEN and Image.open(BytesIO(png)).size == (600, 800)
    entry = json.loads((tmp_path / "usage.jsonl").read_text())
    assert (entry["model"], entry["images"], entry["cost_usd"]) == ("qwen-image-2.1-local", 1, 0.0)


def test_failures_raise_a_clear_error(server):
    server.fail = [requests.ConnectionError("refused")]
    with pytest.raises(local_image.LocalImageError, match="not reachable"):
        local_image.edit_image(Image.new("RGB", (100, 100)), "x", "1:1")
    server.fail = [503]
    with pytest.raises(local_image.LocalImageError, match="downloading the model weights"):
        local_image.edit_image(Image.new("RGB", (100, 100)), "x", "1:1")


def test_a_broken_image_is_rejected(server, monkeypatch):
    monkeypatch.setattr(server, "post", lambda url, json, timeout: NS(status_code=200, content=b"not a png", headers={}))
    monkeypatch.setattr(local_image.requests, "post", server.post)
    with pytest.raises(local_image.LocalImageError, match="no usable image"):
        local_image.edit_image(Image.new("RGB", (100, 100)), "x", "1:1")


def test_availability_follows_the_server_state_and_is_cached(server):
    assert local_image.available() and server.gets == ["http://gpu.test:8000/health"]
    assert local_image.available() and len(server.gets) == 1  # cached
    server.status = "downloading"
    assert not local_image.available(max_age=0)
    server.status = "idle"  # the next page reloads the model
    assert local_image.available(max_age=0)
    server.status = None  # the service is not running
    assert not local_image.available(max_age=0)
    with pytest.raises(local_image.LocalImageError):
        local_image.health(max_age=60)  # the failure is cached too


def test_the_local_prompt_is_the_gemini_coloring_page_prompt():
    prompt = imaging.build_local_prompt("cartoon", "3-5", "remove", "Toucan", "only the bird")
    assert prompt == imaging.build_prompt("cartoon", "3-5", "remove", "Toucan", "only the bird")
    assert "only the bird" in prompt and "Toucan" in prompt


def test_a_local_page_is_cleaned_declared_as_ai_and_remembers_its_model(server, photo):
    book = books.create_book("Aves")
    page = pages.add_photo(book.slug, "ave.png", photo)
    page = imaging.convert_page(book, page, "local_gpu")
    version = page.selected_version
    assert (version.engine, version.model) == ("local_gpu", QWEN)
    assert Image.open(pages.version_path(book.slug, page.id, version.n)).mode == "1"
    assert server.posts[0].json["aspect_ratio"] == "4:3"
    assert kdp._uses_ai(page)


def _book_with(photo, line_art, engine, model):
    book = books.create_book("Aves del jardín")
    clean = lineart.clean(line_art, "6-8").image
    page = pages.add_photo(book.slug, "ave.png", photo)
    version = Version(n=0, engine=engine, style="realistic", age_group="6-8", background="simplify",
                      model=model, created_at="now")
    pages.add_version(book.slug, page.id, version, line_art, clean)
    pages.update_page(book.slug, page.id, title="Tucán", status="approved")
    return books.load_book(book.slug)


def test_kdp_warns_about_pages_from_a_model_that_cannot_be_sold(photo, line_art):
    issues = {i.key: i for i in kdp.review(_book_with(photo, line_art, "local_gpu", QWEN)).issues}
    assert issues["model_not_for_sale"].level == "warning"
    assert issues["model_not_for_sale"].params == {"names": "Tucán", "models": QWEN}
    assert "ai_disclosure" in issues
    allowed = {i.key for i in kdp.review(_book_with(photo, line_art, "local_gpu", "some/permissive-model")).issues}
    assert "model_not_for_sale" not in allowed and "ai_disclosure" in allowed


def test_old_versions_without_a_model_still_load():
    version = Version.model_validate({"n": 1, "engine": "gemini", "style": "realistic", "age_group": "6-8",
                                      "background": "keep", "created_at": "now"})
    assert version.model is None
