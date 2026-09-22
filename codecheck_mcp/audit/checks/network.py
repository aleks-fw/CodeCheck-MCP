"""Network: ошибки API, незагрузившиеся ресурсы, упавшие и медленные запросы."""
from __future__ import annotations

import time
from typing import Any

from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "network"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "network/api-5xx": "The API endpoint in evidence fails on the server: check its server logs, fix the handler, "
                       "and make the page show an error state when the request fails.",
    "network/api-4xx": "The page calls an API endpoint that rejects the request: fix the URL, parameters or auth "
                       "the frontend sends, or stop calling an endpoint that does not exist.",
    "network/script-failed": "Fix the path of this JavaScript file or deploy it: every feature that depends on it "
                             "is broken while it does not load.",
    "network/stylesheet-failed": "Fix the path of this stylesheet or deploy it: the page renders unstyled or "
                                 "partly styled without it.",
    "network/image-failed": "Fix the image path or upload the missing file.",
    "network/font-failed": "Fix the @font-face src path or host the font file; the browser falls back to another "
                           "font until then.",
    "network/request-failed": "The request never got a response (network error, CORS or blocked): check the URL, "
                              "the server's CORS headers and whether the host is reachable.",
    "network/slow-request": "Speed up this response (caching, smaller payload, faster query) or load it lazily "
                            "so it does not delay the page.",
}

_API = ("fetch", "xhr")
_FAILED_ASSET = {"script": ("network/script-failed", "critical", "JavaScript file did not load"),
                 "stylesheet": ("network/stylesheet-failed", "critical", "Stylesheet did not load"),
                 "image": ("network/image-failed", "warning", "Image did not load"),
                 "font": ("network/font-failed", "warning", "Font did not load")}

LOGIN_JS = """() => !!document.querySelector('input[type=password]') ||
  /(^|[\\/_-])(login|log-in|signin|sign-in|auth)([\\/_.-]|$)/i.test(location.pathname)"""


def _duration(req, rec: dict[str, Any]) -> float | None:
    t = req.timing
    if rec["state"] == "finished" and t.get("responseEnd", -1) >= 0:
        return round(t["responseEnd"], 1)
    if rec["state"] == "pending" and t.get("startTime", -1) > 0:  # так и не ответил: сколько уже ждём
        return round(time.time() * 1000 - t["startTime"], 1)
    return None


def run(page, ctx) -> list[Finding]:
    try:  # даём запросам после load завершиться
        page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE_WAIT_MS)
    except Exception:
        pass
    login = bool(page.evaluate(LOGIN_JS))
    out: list[Finding] = []

    for req, rec in list(ctx.events.requests.items()):
        url = req.url
        if not url.startswith(("http://", "https://")) or url in ctx.events.blocked:
            continue
        rtype, status, error = req.resource_type, rec["status"], rec["error"]
        dur = _duration(req, rec)
        ev = {"method": req.method, "url": url, "status": status, "durationMs": dur, "resourceType": rtype}
        if error:
            ev["error"] = error
        ev = {k: v for k, v in ev.items() if v is not None}

        def add(rule, sev, message, details, ev=ev, url=url):
            out.append(Finding(severity=sev, category=CATEGORY, rule=rule, page=ctx.path, url=url,
                               message=message, details=details, evidence=ev))

        main_doc = rtype == "document" and req.frame == page.main_frame
        bad_status = status is not None and status >= 400
        if bad_status and not main_doc:  # код главного документа разбирает обход страниц
            if rtype in _API:
                if status >= 500:
                    add("network/api-5xx", "critical", f"API request returned HTTP {status}",
                        f"{req.method} {url} answered HTTP {status} on {ctx.path}.")
                elif not (status in (401, 403) and login):
                    add("network/api-4xx", "warning", f"API request returned HTTP {status}",
                        f"{req.method} {url} answered HTTP {status} on {ctx.path}.")
                continue
            if rtype == "font" and "fonts" in ctx.site.checks:  # сообщит проверка fonts, с именем шрифта
                continue
            if rtype in _FAILED_ASSET:
                rule, sev, title = _FAILED_ASSET[rtype]
                add(rule, sev, title, f"{url} answered HTTP {status} on {ctx.path}.")
                continue
        elif rec["state"] == "failed" and status is None:
            if "ERR_ABORTED" in (error or ""):  # запрос отменила сама страница (навигация, abort())
                continue
            if rtype == "font" and "fonts" in ctx.site.checks:
                continue
            if rtype in _FAILED_ASSET:
                rule, sev, title = _FAILED_ASSET[rtype]
                add(rule, sev, title, f"Loading {url} on {ctx.path} failed: {error}.")
            else:
                add("network/request-failed", "warning", "Request failed",
                    f"{req.method} {url} on {ctx.path} failed without a response: {error}.")
            continue

        if dur is not None and dur > T.SLOW_REQUEST_NOTICE_MS:
            sev = "warning" if dur > T.SLOW_REQUEST_WARNING_MS else "notice"
            state = "is still pending after" if rec["state"] == "pending" else "took"
            add("network/slow-request", sev, f"Slow request: {dur / 1000:.1f} s",
                f"{req.method} {url} on {ctx.path} {state} {dur:.0f} ms.")
    return out
