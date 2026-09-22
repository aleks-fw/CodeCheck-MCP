"""Запуск Playwright, статический сервер для папки, обход страниц."""
from __future__ import annotations

import functools
import http.server
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

from playwright.sync_api import sync_playwright  # noqa: E402

from .report import Report  # noqa: E402

PAGE_TIMEOUT_MS = 15000
EXTERNAL_TIMEOUT_MS = 5000
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}

# CSS-путь элемента для читаемых отчётов
SELECTOR_JS = """
window.__qaPath = (el) => {
  if (!el || el.nodeType !== 1) return '';
  if (el.id) return '#' + CSS.escape(el.id);
  const parts = [];
  while (el && el.nodeType === 1 && el !== document.documentElement && parts.length < 5) {
    let s = el.tagName.toLowerCase();
    const cls = [...el.classList].slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
    s += cls;
    const sib = el.parentElement ? [...el.parentElement.children].filter(x => x.tagName === el.tagName) : [];
    if (!cls && sib.length > 1) s += `:nth-of-type(${sib.indexOf(el) + 1})`;
    parts.unshift(s);
    el = el.parentElement;
  }
  return parts.join(' > ');
};
window.__qaRect = (el) => { const r = el.getBoundingClientRect();
  return {x: r.x, y: r.y, width: r.width, height: r.height}; };
"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # без шума в stdout MCP
        pass


@contextmanager
def open_target(target: str):
    """Отдаёт стартовый URL: для http(s) как есть, для папки/файла поднимает локальный сервер."""
    if target.startswith(("http://", "https://")):
        yield target
        return
    p = Path(target).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Путь не найден: {target}")
    root, start = (p, "index.html") if p.is_dir() else (p.parent, p.name)
    handler = functools.partial(_QuietHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/{start}"
    finally:
        srv.shutdown()
        srv.server_close()


def external_route_handler(origin: str, on_blocked=None, proxy_external: bool = True):
    """Обработчик маршрутов: переходы на чужие домены блокируются, чужие подресурсы грузятся с таймаутом.
    proxy_external=False: чужие подресурсы идут напрямую (без задержки прокси, важно для замеров скорости)."""
    def handle_route(route, request):
        external = urlparse(request.url).netloc not in (origin, "")
        if external and request.is_navigation_request():
            if on_blocked:
                on_blocked(request.url)
            route.abort()
        elif external and proxy_external and request.url.startswith(("http://", "https://")):
            # внешний подресурс (шрифт, скрипт, картинка): подвисший сервер не должен вешать всю проверку
            try:
                route.fulfill(response=route.fetch(timeout=EXTERNAL_TIMEOUT_MS))
            except Exception:
                route.abort()
        else:
            route.continue_()
    return handle_route


def launch_chromium(pw):
    """Запуск Chromium с понятной ошибкой, если браузер не скачан."""
    try:
        return pw.chromium.launch()
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            raise RuntimeError("Браузер Chromium для Playwright не установлен. "
                               "Выполните один раз: python -m playwright install chromium") from e
        raise


def new_page(browser, report: Report, page_url: str, viewport: dict | None = None):
    """Чистый изолированный контекст со слушателями ошибок; внешние переходы блокируются."""
    ctx = browser.new_context(viewport=viewport or DEFAULT_VIEWPORT, ignore_https_errors=False)
    ctx.set_default_timeout(PAGE_TIMEOUT_MS)
    page = ctx.new_page()
    origin = urlparse(page_url).netloc

    # запросы, оборванные закрытием контекста, ошибками сайта не считаются
    state = {"closing": False}
    real_close = ctx.close

    def close(*args, **kwargs):
        state["closing"] = True
        return real_close(*args, **kwargs)
    ctx.close = close

    def on_console(msg):
        if msg.type == "error" and not state["closing"]:
            report.add("console", "medium", f"Ошибка в консоли: {msg.text[:200]}", page=page_url)

    def on_response(resp):
        if resp.status >= 400 and not state["closing"]:
            sev = "high" if resp.request.resource_type in ("document", "script", "stylesheet") else "medium"
            report.add("network", sev, f"HTTP {resp.status}: {resp.url[:150]}", page=page_url)

    def on_failed(req):
        if state["closing"]:
            return
        if urlparse(req.url).netloc == origin or req.resource_type in ("script", "stylesheet", "image", "font"):
            report.add("network", "medium", f"Запрос не выполнен: {req.url[:150]}", page=page_url)

    def on_blocked(url):
        report.add("interactions", "low", f"Переход на внешний домен заблокирован: {url[:150]}", page=page_url)

    page.on("console", on_console)
    page.on("pageerror", lambda e: report.add("console", "high", f"JS-исключение: {str(e)[:200]}", page=page_url))
    page.on("response", on_response)
    page.on("requestfailed", on_failed)
    ctx.route("**/*", external_route_handler(origin, on_blocked))  # на контексте, чтобы покрывать и всплывающие окна
    page.add_init_script(SELECTOR_JS)
    return ctx, page


def goto(page, url: str):
    """Ждём ответ сервера, затем DOMContentLoaded и load, каждый с ограничением по времени:
    внешний шрифт, карта или счётчик не должны ронять проверку."""
    resp = page.goto(url, wait_until="commit")
    for state, timeout in (("domcontentloaded", 10000), ("load", 5000)):
        try:
            page.wait_for_load_state(state, timeout=timeout)
        except Exception:
            break
    try:  # вёрстка зависит от шрифтов: меряем уже с загруженными (но ждём не дольше 3 с)
        page.evaluate("Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]).then(() => true)")
    except Exception:
        pass
    page.wait_for_timeout(300)  # дать отработать скриптам и анимациям входа
    return resp


def crawl(browser, report: Report, start_url: str, max_pages: int = 10) -> list[str]:
    """Обход внутренних ссылок в ширину; возвращает список страниц."""
    origin = urlparse(start_url).netloc
    seen: list[str] = []
    queue = [start_url]
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        ctx, page = new_page(browser, report, url)
        try:
            resp = goto(page, url)
            if resp and resp.status >= 400:
                report.add("network", "high", f"Страница недоступна: HTTP {resp.status}", page=url)
                continue
            seen.append(url)
            hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
            for h in hrefs:
                if not h or h.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                full = urldefrag(urljoin(url, h))[0]
                path = urlparse(full).path
                if urlparse(full).netloc == origin and full not in seen and full not in queue \
                        and not path.lower().endswith((".pdf", ".zip", ".jpg", ".jpeg", ".png", ".webp", ".svg")):
                    queue.append(full)
        except Exception as e:
            report.add("network", "high", f"Не удалось открыть страницу: {str(e)[:150]}", page=url)
        finally:
            ctx.close()
    return seen


def run(target: str, checks: list, report: Report | None = None, max_pages: int = 10, **opts) -> Report:
    """Открывает проект, обходит страницы и прогоняет каждую проверку на каждой странице."""
    if not target.startswith(("http://", "https://")):
        p = Path(target).expanduser().resolve()
        opts.setdefault("source_dir", p if p.is_dir() else p.parent)
    with open_target(target) as start_url:
        report = report or Report(target=target)
        with sync_playwright() as pw:
            browser = launch_chromium(pw)
            try:
                report.pages = crawl(browser, report, start_url, max_pages)
                for url in report.pages:
                    for check in checks:
                        try:
                            check(browser, url, report, **opts)
                        except Exception as e:  # падение одной проверки не роняет весь прогон
                            report.add("internal", "low", f"Проверка {check.__module__} упала: {str(e)[:150]}",
                                       page=url)
            finally:
                browser.close()
    report.write()
    return report
