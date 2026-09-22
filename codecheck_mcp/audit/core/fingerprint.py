"""Стабильный отпечаток находки для сравнения прогонов."""
from __future__ import annotations

import hashlib
import re

# одно и то же наблюдение, найденное разными проверками (например, axe и SEO), сводится к одному правилу;
# заполняется в фазах с пересекающимися проверками
ALIASES: dict[str, str] = {}


# у локальной папки порт сервера случайный при каждом запуске: в отпечаток он не входит
_LOCAL_ORIGIN = re.compile(r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?=/|$)", re.I)


def fingerprint(rule: str, page: str, target: str | None) -> str:
    """Хэш от rule + page + (selector или url): не зависит от порядка, времени, нумерации и порта localhost."""
    raw = "\n".join((rule, page, _LOCAL_ORIGIN.sub("", target or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def dedupe_key(rule: str, page: str, target: str | None) -> str:
    """Ключ для дедупликации: как fingerprint, но с учётом синонимов правил."""
    return fingerprint(ALIASES.get(rule, rule), page, target)
