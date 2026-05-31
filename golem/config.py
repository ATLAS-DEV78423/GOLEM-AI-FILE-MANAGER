from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .constants import DEFAULT_CATEGORY
from .legal import TERMS_VERSION


@dataclass(slots=True)
class AppConfig:
    watched_folder: str = ""
    vault_folder: str = ""
    llm_provider: str = "groq"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    dry_run: bool = False
    watch_enabled: bool = True
    confidence_threshold: float = 0.8
    default_category: str = DEFAULT_CATEGORY
    terms_accepted: bool = False
    terms_version: str = TERMS_VERSION

    def as_settings(self) -> dict[str, str]:
        return {
            "watched_folder": self.watched_folder,
            "vault_folder": self.vault_folder,
            "llm_provider": self.llm_provider,
            "llm_api_key": self.llm_api_key,
            "groq_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "dry_run": "1" if self.dry_run else "0",
            "watch_enabled": "1" if self.watch_enabled else "0",
            "confidence_threshold": str(self.confidence_threshold),
            "default_category": self.default_category,
            "terms_accepted": "1" if self.terms_accepted else "0",
            "terms_version": self.terms_version,
        }

    @classmethod
    def from_settings(cls, settings: dict[str, str]) -> "AppConfig":
        api_key = settings.get("llm_api_key", settings.get("groq_api_key", ""))
        return cls(
            watched_folder=settings.get("watched_folder", ""),
            vault_folder=settings.get("vault_folder", ""),
            llm_provider=settings.get("llm_provider", "groq"),
            llm_api_key=api_key,
            llm_model=settings.get("llm_model", ""),
            llm_base_url=settings.get("llm_base_url", ""),
            dry_run=settings.get("dry_run", "0") == "1",
            watch_enabled=settings.get("watch_enabled", "1") == "1",
            confidence_threshold=float(settings.get("confidence_threshold", "0.8")),
            default_category=settings.get("default_category", DEFAULT_CATEGORY),
            terms_accepted=settings.get("terms_accepted", "0") == "1",
            terms_version=settings.get("terms_version", TERMS_VERSION),
        )

    @property
    def groq_api_key(self) -> str:
        return self.llm_api_key

    @groq_api_key.setter
    def groq_api_key(self, value: str) -> None:
        self.llm_api_key = value
