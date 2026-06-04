from __future__ import annotations

from pathlib import Path

from .constants import resource_path

TERMS_VERSION = "1.0"
TERMS_PATH = resource_path("assets", "legal", "terms_of_service.md")


def terms_of_service_text() -> str:
    return TERMS_PATH.read_text(encoding="utf-8")


def terms_of_service_path() -> Path:
    return TERMS_PATH
