"""Реестр проверок audit_project.

Проверка это модуль с полями:
  CATEGORY: str                   одна из core.finding.CATEGORIES
  PER_VIEWPORT: bool              True: запускать на каждом viewport, False: один раз на страницу (самый широкий)
  RECOMMENDATIONS: dict[str, str] рекомендация на каждое правило, которое проверка может выдать
  run(page, ctx) -> list[Finding]
Проверки идут в порядке списка: network первой, она ждёт тишины в сети, и console видит поздние ошибки.
"""
from __future__ import annotations

from types import ModuleType

from . import accessibility, console, fonts, images, interaction, layout, network, performance, security, seo

# performance сразу после network: до прокрутки и нажатий, которые останавливают замер LCP;
# accessibility нажимает Tab и меняет фокус; interaction последней: она перезагружает страницу и кликает
REGISTRY: list[ModuleType] = [network, performance, console, seo, fonts, images, layout, security, accessibility,
                              interaction]


def recommendations(modules: list[ModuleType]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in modules:
        out.update(m.RECOMMENDATIONS)
    return out
