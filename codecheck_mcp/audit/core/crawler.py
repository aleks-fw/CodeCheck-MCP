"""Сбор внутренних ссылок страницы: только тот же origin, без файлов и якорей."""
from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse

SKIP_EXT = (".pdf", ".zip", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif", ".mp4", ".mp3")


def page_key(url: str) -> str:
    """/ и /index.html считаем одной страницей."""
    u = urlparse(url)
    path = u.path[: -len("index.html")] if u.path.endswith("/index.html") else u.path
    return f"{u.scheme}://{u.netloc}{path or '/'}" + (f"?{u.query}" if u.query else "")


def same_origin_links(page, base_url: str) -> list[str]:
    origin = urlparse(base_url).netloc
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    out = []
    for h in hrefs:
        if not h or h.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full = urldefrag(urljoin(base_url, h))[0]
        u = urlparse(full)
        if u.scheme in ("http", "https") and u.netloc == origin and not u.path.lower().endswith(SKIP_EXT):
            out.append(full)
    return out
