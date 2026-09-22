"""Стабильный отпечаток находки для сравнения прогонов."""
from __future__ import annotations

import hashlib
import re

# одно и то же наблюдение, найденное разными проверками, сводится к одному правилу
ALIASES: dict[str, str] = {
    "accessibility/image-alt": "images/missing-alt",
    "accessibility/html-has-lang": "seo/missing-lang",
    "accessibility/document-title": "seo/missing-title",
    "images/broken": "network/image-failed",
}
# для этих правил одна и та же проблема узнаётся по URL ресурса, а не по селектору элемента
URL_KEYED = {"network/image-failed"}


# у локальной папки порт сервера случайный при каждом запуске: в отпечаток он не входит
_LOCAL_ORIGIN = re.compile(r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?(?=/|$)", re.I)


def fingerprint(rule: str, page: str, target: str | None) -> str:
    """Хэш от rule + page + (selector или url): не зависит от порядка, времени, нумерации и порта localhost."""
    raw = "\n".join((rule, page, _LOCAL_ORIGIN.sub("", target or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def dedupe_key(rule: str, page: str, target: str | None, url: str | None = None) -> str:
    """Ключ для дедупликации: как fingerprint, но с учётом синонимов правил."""
    canon = ALIASES.get(rule, rule)
    return fingerprint(canon, page, url if canon in URL_KEYED and url else target)
