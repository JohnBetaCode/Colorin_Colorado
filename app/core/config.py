"""Application settings.

Values are read from environment variables, with ``config/.env`` loaded
first (git-ignored; see ``config/.env.example``). Defaults below mirror
``config/.env.example`` and are used when a variable is absent.

Authentication (``GEMINI_AUTH``) is one of:
  - ``adc``: Vertex AI with Google Application Default Credentials, either a mounted
    ADC file (``GOOGLE_APPLICATION_CREDENTIALS``) or ``gcloud auth application-default login``,
    and ``GOOGLE_CLOUD_PROJECT``.
  - ``vertex_key``: Vertex AI with an API key (``GEMINI_API_KEY``), no project needed.
  - ``studio_key``: the Gemini Developer API with a Google AI Studio key (``GEMINI_API_KEY``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
ENV_FILE = CONFIG_DIR / ".env"

LANGUAGES = ("es", "en")
AUTH_METHODS = ("adc", "vertex_key", "studio_key")

load_dotenv(ENV_FILE)


@dataclass
class Settings:
    auth: str
    api_key: str
    project: str
    text_location: str
    image_location: str
    text_model: str
    image_model: str
    ui_language: str

    @property
    def configured(self) -> bool:
        return bool(self.project) if self.auth == "adc" else bool(self.api_key)


def get_settings() -> Settings:
    language = os.environ.get("UI_LANGUAGE", "es")
    auth = os.environ.get("GEMINI_AUTH", "adc")
    return Settings(
        auth=auth if auth in AUTH_METHODS else "adc",
        api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        text_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        image_location=os.environ.get("GEMINI_IMAGE_LOCATION", "global"),
        text_model=os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.8-flash"),
        image_model=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image"),
        ui_language=language if language in LANGUAGES else "es",
    )


def save_settings(values: dict[str, str]) -> None:
    """Merge ``values`` into config/.env and apply them to the running process.

    Keys not in ``values`` keep their current value, so saving the UI language alone
    does not wipe the Vertex AI settings.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None} if ENV_FILE.exists() else {}
    current.update(values)
    lines = ["# Colorín Colorado — managed from the app's Settings panel"]
    for key, value in current.items():
        lines.append(f"{key}={value}")
        os.environ[key] = value
    ENV_FILE.write_text("\n".join(lines) + "\n")
