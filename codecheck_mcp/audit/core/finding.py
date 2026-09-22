"""Модель находки audit_project и её JSON-представление."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fingerprint import dedupe_key, fingerprint

SEVERITIES = ("critical", "warning", "notice")
CATEGORIES = ("interaction", "layout", "images", "fonts", "console",
              "accessibility", "seo", "performance", "security", "network")

# порядок полей в JSON как в описании формата
_FIELDS = ("id", "fingerprint", "severity", "category", "rule", "page", "message", "details",
           "selector", "url", "viewport", "screenshot", "evidence")
_OPTIONAL = ("selector", "url", "viewport", "screenshot", "evidence")


@dataclass
class Finding:
    severity: str
    category: str
    rule: str          # машинный код правила, например "seo/missing-title"
    page: str          # путь страницы, например "/checkout"
    message: str       # короткое описание
    details: str       # однозначное описание наблюдаемого факта
    selector: str | None = None
    url: str | None = None
    viewport: str | None = None     # например "375x812"
    screenshot: str | None = None   # путь относительно папки отчёта
    evidence: dict[str, Any] | None = None
    id: str = ""                    # CC-001..., выдаётся в конце прогона
    fingerprint: str = field(default="")

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {self.severity}")
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category: {self.category}")
        if not self.fingerprint:
            self.fingerprint = fingerprint(self.rule, self.page, self.target)

    @property
    def dedupe_key(self) -> str:
        return dedupe_key(self.rule, self.page, self.target, self.url)

    @property
    def target(self) -> str:
        """Что именно найдено на странице: селектор, иначе URL ресурса, иначе текст (ошибки консоли)."""
        return self.selector or self.url or self.message

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in _FIELDS}
        return {k: v for k, v in d.items() if not (k in _OPTIONAL and v is None)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        return cls(**{k: d[k] for k in _FIELDS if k in d})
