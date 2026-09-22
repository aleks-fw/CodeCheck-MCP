"""Открытие страницы для аудита и контекст, который получает каждая проверка."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ...browser import PAGE_TIMEOUT_MS, external_route_handler
from .selector import SELECTOR_JS

# pageerror ловит не все отклонённые промисы, поэтому слушаем unhandledrejection сами
REJECTIONS_JS = """
window.__ccRejections = [];
window.addEventListener('unhandledrejection', (e) => {
  const r = e.reason;
  window.__ccRejections.push({message: r && r.message !== undefined ? String(r.message) : String(r),
                              stack: r && r.stack ? String(r.stack) : ''});
});
"""


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
class Events:
    """События страницы, собранные с момента до загрузки."""
    console: list[dict[str, Any]] = field(default_factory=list)     # только console.error
    pageerrors: list[dict[str, str]] = field(default_factory=list)
    requests: dict[Any, dict[str, Any]] = field(default_factory=dict)  # Request -> {state, status, error}
    blocked: set[str] = field(default_factory=set)                  # переходы на чужие домены, прерванные нами


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
    events: Events = field(default_factory=Events)

    @property
    def path(self) -> str:
        return page_path(self.url)

    @property
    def viewport(self) -> str:
        return f"{self.width}x{self.height}"


def page_path(url: str) -> str:
    u = urlparse(url)
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def _listen(page, ev: Events) -> None:
    def on_console(msg):
        if msg.type == "error":
            ev.console.append({"text": msg.text, "location": msg.location})

    def on_pageerror(err):
        ev.pageerrors.append({"name": err.name or "", "message": err.message or "", "stack": err.stack or ""})

    def on_request(req):
        ev.requests[req] = {"state": "pending", "status": None, "error": None}

    def on_response(resp):
        rec = ev.requests.get(resp.request)
        if rec is not None:
            rec["status"] = resp.status

    def on_finished(req):
        if req in ev.requests:
            ev.requests[req]["state"] = "finished"

    def on_failed(req):
        if req in ev.requests:
            ev.requests[req].update(state="failed", error=req.failure)

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfinished", on_finished)
    page.on("requestfailed", on_failed)


def open_page(browser, site: Site, url: str, width: int, height: int):
    """Изолированный контекст: слушатели и init-скрипты подключены до загрузки, внешние переходы заблокированы."""
    ev = Events()
    bctx = browser.new_context(viewport={"width": width, "height": height})
    bctx.set_default_timeout(PAGE_TIMEOUT_MS)
    bctx.route("**/*", external_route_handler(urlparse(url).netloc, ev.blocked.add))
    page = bctx.new_page()
    page.add_init_script(SELECTOR_JS)
    page.add_init_script(REJECTIONS_JS)
    _listen(page, ev)
    return bctx, page, ev
