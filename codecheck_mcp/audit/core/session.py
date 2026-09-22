"""Открытие страницы для аудита и контекст, который получает каждая проверка."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ...browser import PAGE_TIMEOUT_MS, external_route_handler
from .selector import SELECTOR_JS


@dataclass
class Site:
    """Общее на весь прогон: origin, стартовый URL, проверки «один раз на сайт»."""
    start_url: str
    critical_selectors: list[str] = field(default_factory=list)
    _once: set[str] = field(default_factory=set)

    @property
    def origin(self) -> str:
        u = urlparse(self.start_url)
        return f"{u.scheme}://{u.netloc}"

    def first_time(self, key: str) -> bool:
        if key in self._once:
            return False
        self._once.add(key)
        return True


@dataclass
class PageContext:
    """То, что проверка знает о текущей странице: адрес, viewport и события, собранные до загрузки."""
    site: Site
    url: str
    width: int
    height: int
    primary: bool                   # самый широкий viewport: на нём идут проверки «один раз на страницу»
    browser_context: Any = None
    response: Any = None            # ответ на загрузку документа
    events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return page_path(self.url)

    @property
    def viewport(self) -> str:
        return f"{self.width}x{self.height}"


def page_path(url: str) -> str:
    u = urlparse(url)
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def open_page(browser, site: Site, url: str, width: int, height: int):
    """Изолированный контекст: внешние переходы заблокированы, генератор селекторов подключён до загрузки."""
    bctx = browser.new_context(viewport={"width": width, "height": height})
    bctx.set_default_timeout(PAGE_TIMEOUT_MS)
    bctx.route("**/*", external_route_handler(urlparse(url).netloc))
    page = bctx.new_page()
    page.add_init_script(SELECTOR_JS)
    return bctx, page
