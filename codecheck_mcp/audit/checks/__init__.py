"""Реестр проверок audit_project.

Проверка это модуль с полями:
  CATEGORY: str                   одна из core.finding.CATEGORIES
  PER_VIEWPORT: bool              True: запускать на каждом viewport, False: один раз на страницу (самый широкий)
  RECOMMENDATIONS: dict[str, str] рекомендация на каждое правило, которое проверка может выдать
  run(page, ctx) -> list[Finding]
"""
from __future__ import annotations

from types import ModuleType

REGISTRY: list[ModuleType] = []


def recommendations(modules: list[ModuleType]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in modules:
        out.update(m.RECOMMENDATIONS)
    return out
