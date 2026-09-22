"""Interactions: клик по кнопкам, ссылкам-заглушкам и role=button; ищем элементы, которые ничего не делают."""
from __future__ import annotations

import re
import time
from urllib.parse import urldefrag, urlparse

from ...browser import goto
from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "interaction"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "interaction/no-effect": "Attach the missing click handler (or fix the one that throws / exits early), or make "
                             "the element a link with a real href; if it is decorative, make it look non-clickable.",
    "interaction/not-clickable": "Another element covers this control or it is outside the viewport: fix the "
                                 "z-index / overlay, or the position so the control can be clicked.",
    "interaction/action-request-failed": "The click works in the page but the request it sends fails: fix the "
                                         "endpoint in evidence (server logs for 5xx, URL / payload for 4xx) and "
                                         "show the user an error state when it fails.",
    "interaction/critical-not-checked": "Check the selector against the page markup (it must match a visible, "
                                        "enabled element on a crawled page), or make the key action reachable "
                                        "without prior steps so it can be clicked.",
}

# почему критичный селектор не проверен; чем дальше в списке, тем ближе к проверке
CRITICAL_STATES = ("invalid", "missing", "hidden", "limit", "unstable", "destructive", "checked")
CRITICAL_REASONS = {
    "invalid": "is not a valid CSS selector",
    "missing": "matched no element",
    "hidden": "matched only hidden or disabled elements",
    "unstable": "matched an element that changed after the page was reloaded, so it could not be clicked reliably",
    "destructive": "matched an element whose label looks destructive (delete, log out), so it was not clicked",
    "limit": "was not reached: the per-page click limit ran out",
}

DESTRUCTIVE = re.compile(r"log\s*-?out|sign\s*-?out|delete|remove|destroy|unsubscribe|удал|выйти|выход", re.I)
STATEFUL = re.compile(r"cart|basket|checkout|pay|order|buy|login|log\s*in|sign\s*in|account|profile|корзин|"
                      r"оформ|оплат|заказ|купить|войти|профил|кабинет", re.I)

COLLECT_JS = """(given) => {
  const critical = given.filter(c => { try { document.querySelector(c); return true; } catch (e) { return false; } });
  const vis = (el) => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0.05 && r.width > 1 && r.height > 1; };
  const sel = 'button, input[type=button], input[type=submit], input[type=reset], a[href="#"], ' +
              'a[href^="javascript:" i], [role=button]';
  const matchesCritical = (el) => critical.some(c => { try { return el.matches(c); } catch (e) { return false; } });
  const crit = [], rest = [];
  for (const el of document.querySelectorAll(sel + (critical.length ? ', ' + critical.join(', ') : ''))) {
    if (!vis(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    (matchesCritical(el) ? crit : rest).push(el);
  }
  return [...crit, ...rest].map((el, i) => {
    el.setAttribute('data-cc-i', i);
    return {i, sel: __ccSelector(el), tag: el.tagName.toLowerCase(), critical: matchesCritical(el),
      inForm: !!el.closest('form'),
      hits: critical.filter(c => { try { return el.matches(c); } catch (e) { return false; } }),
      label: [el.innerText, el.value, el.getAttribute('aria-label'), el.id, el.className && String(el.className)]
             .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim().slice(0, 80)};
  });
}"""

# что есть на странице по каждому критичному селектору, до кликов
PRESENCE_JS = """(given) => given.map(c => {
  let els;
  try { els = [...document.querySelectorAll(c)]; } catch (e) { return 'invalid'; }
  if (!els.length) return 'missing';
  const vis = (el) => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0.05 && r.width > 1 && r.height > 1; };
  return els.some(el => vis(el) && !el.disabled && el.getAttribute('aria-disabled') !== 'true') ? 'visible' : 'hidden';
})"""

# ставится после прокрутки к элементу и до клика
WATCH_JS = """() => {
  const w = {mut: 0, invalid: 0, x: scrollX, y: scrollY, hash: location.hash};
  new MutationObserver(ms => { w.mut += ms.length; })
    .observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  document.addEventListener('invalid', () => { w.invalid++; }, true);  // браузер показал ошибку в форме
  window.__ccWatch = w;
}"""

STATE_JS = """() => { const w = window.__ccWatch; if (!w) return null;
  return {mut: w.mut, invalid: w.invalid, scrolled: Math.abs(scrollX - w.x) > 1 || Math.abs(scrollY - w.y) > 1,
          hash: location.hash !== w.hash && location.hash.length > 1}; }"""


def _click_error(text: str) -> str:
    """Первая строка ошибки Playwright плюс причина из журнала вызова (кто перехватил клик и т. п.)."""
    lines = [x.strip(" -") for x in text.splitlines() if x.strip()]
    reason = next((x for x in lines if "intercepts pointer events" in x or "not visible" in x
                   or "outside of the viewport" in x or "not stable" in x), "")
    return (lines[0] + (f" Reason: {reason}" if reason else ""))[:300] if lines else "click failed"


API_TYPES = ("fetch", "xhr", "document")


def _failed_requests(page, sent: dict, blocked: set[str]) -> list[dict]:
    """Ждёт ответы на запросы, вызванные кликом, и возвращает те, что закончились ошибкой."""
    deadline = time.monotonic() + T.CLICK_REQUEST_WAIT_MS / 1000
    while any(not r["done"] for r in sent.values()) and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    out = []
    for req, r in sent.items():
        if req.url in blocked or not req.url.startswith(("http://", "https://")):
            continue  # переход на чужой домен прервали мы сами
        if r["status"] is not None and r["status"] >= 400:
            out.append({"method": req.method, "url": req.url, "status": r["status"],
                        "resourceType": req.resource_type})
        elif r["error"] and "ERR_ABORTED" not in r["error"]:  # ERR_ABORTED: запрос отменила сама страница
            out.append({"method": req.method, "url": req.url, "error": r["error"],
                        "resourceType": req.resource_type})
    return out


def _probe(page, item: dict, blocked: set[str] | None = None) -> tuple[str | None, str, list[dict]]:
    """Кликает элемент на свежей странице. Возвращает (что произошло или None, ошибка клика,
    запросы от этого клика, закончившиеся ошибкой)."""
    ev = {"requests": 0, "popup": 0, "dialog": 0, "download": 0}
    sent: dict = {}   # запросы API и документов, вызванные кликом: Request -> {status, error, done}

    def on_request(r):
        ev["requests"] += 1
        if r.resource_type in API_TYPES:
            sent[r] = {"status": None, "error": None, "done": False}

    def on_response(resp):
        if resp.request in sent:
            sent[resp.request]["status"] = resp.status

    def on_finished(r):
        if r in sent:
            sent[r]["done"] = True

    def on_failed(r):
        if r in sent:
            sent[r].update(done=True, error=r.failure)

    def on_popup(p):
        ev["popup"] += 1
        try:
            p.close()
        except Exception:
            pass

    def on_dialog(d):
        ev["dialog"] += 1
        d.dismiss()

    def on_download(_d):
        ev["download"] += 1

    # framenavigated не слушаем: клик по href="#" даёт его без всякого эффекта; настоящий переход виден
    # по смене адреса и по запросу документа
    handlers = {"request": on_request, "popup": on_popup, "dialog": on_dialog, "download": on_download,
                "response": on_response, "requestfinished": on_finished, "requestfailed": on_failed}
    loc = page.locator(f'[data-cc-i="{item["i"]}"]')
    loc.scroll_into_view_if_needed(timeout=2000)
    before = page.url
    page.evaluate(WATCH_JS)
    for name, h in handlers.items():  # до try: finally снимает только подключённые слушатели
        page.on(name, h)
    try:
        try:
            loc.click(timeout=3000, no_wait_after=True)
        except Exception as e:
            return None, _click_error(str(e)), []
        effect = _observe(page, ev, before)
        return effect, "", _failed_requests(page, sent, blocked or set()) if effect else []
    finally:
        for name, h in handlers.items():
            page.remove_listener(name, h)


def _observe(page, ev: dict, before: str) -> str | None:
    """До CLICK_OBSERVE_MS ждёт любой реакции на клик; возвращает её вид или None."""
    deadline = time.monotonic() + T.CLICK_OBSERVE_MS / 1000
    while True:
        if urldefrag(page.url)[0] != urldefrag(before)[0]:
            return "navigation"
        for k in ("requests", "popup", "dialog", "download"):
            if ev[k]:
                return k
        try:
            st = page.evaluate(STATE_JS)
        except Exception:  # контекст страницы уничтожен переходом
            return "navigation"
        if st is None:
            return "navigation"
        if st["hash"]:
            return "url change"
        if st["mut"] or st["invalid"] or st["scrolled"]:
            return "dom change" if st["mut"] else ("form validation" if st["invalid"] else "scroll")
        if time.monotonic() >= deadline:
            return None
        page.wait_for_timeout(100)


def _reload(page, url: str, attempts: int = 3) -> None:
    """Свежая загрузка страницы. Переход, начатый прошлым кликом (например, через setTimeout), может перебить
    нашу загрузку или увести на другую страницу: тогда ждём и грузим ещё раз."""
    for n in range(attempts):
        try:
            goto(page, url)
            if urldefrag(page.url)[0] == urldefrag(url)[0]:
                return
        except Exception:
            if n == attempts - 1:
                raise
        page.wait_for_timeout(500)
    raise RuntimeError(f"could not reload {url}: the page kept navigating to {page.url}")


def run(page, ctx) -> list[Finding]:
    critical = ctx.site.critical_selectors
    _reload(page, ctx.url)
    state = _critical_state(ctx)
    if critical:
        for c, seen in zip(critical, page.evaluate(PRESENCE_JS, critical), strict=True):  # PRESENCE_JS: по ответу на селектор
            state(c, "limit" if seen == "visible" else seen)  # видимый, но ещё не кликнутый
    items = page.evaluate(COLLECT_JS, critical)
    out: list[Finding] = []
    tried = 0
    for item in items:
        if tried >= T.MAX_CLICKS_PER_PAGE:
            break
        if DESTRUCTIVE.search(item["label"]):
            for c in item["hits"]:
                state(c, "destructive")
            continue
        tried += 1
        if tried > 1:  # каждый клик на свежей странице
            _reload(page, ctx.url)
            again = page.evaluate(COLLECT_JS, critical)
            if item["i"] >= len(again) or again[item["i"]]["sel"] != item["sel"]:
                for c in item["hits"]:
                    state(c, "unstable")
                continue  # после перезагрузки страница другая: этот элемент не проверить надёжно
        for c in item["hits"]:
            state(c, "checked")
        effect, error, failures = _probe(page, item, ctx.events.blocked)
        state_note = (" This control may depend on app state (cart, login): the page was reloaded before the "
                      "click, so the state may have been reset." if STATEFUL.search(item["label"]) else "")
        if effect:
            failed = _request_failure(ctx, item, failures, state_note)
            if failed:
                out.append(failed)
            continue
        sev = "critical" if item["critical"] else "warning"
        if error:
            out.append(Finding(
                severity=sev, category=CATEGORY, rule="interaction/not-clickable", page=ctx.path,
                selector=item["sel"], message=f"{item['sel']} cannot be clicked",
                details=f"Clicking {item['sel']} on {ctx.path} failed: {error}.{state_note}",
                evidence={"error": error, "critical": item["critical"]}))
        else:
            out.append(Finding(
                severity=sev, category=CATEGORY, rule="interaction/no-effect", page=ctx.path, selector=item["sel"],
                message=f"Clicking {item['sel']} does nothing",
                details=f"Clicking {item['sel']} on {ctx.path} produced no navigation, URL change, network request "
                        f"or visible DOM change within {T.CLICK_OBSERVE_MS / 1000:g} seconds.{state_note}",
                evidence={"observedMs": T.CLICK_OBSERVE_MS, "critical": item["critical"],
                          "watched": ["url", "navigation", "network request", "DOM mutation", "dialog", "new tab",
                                      "download", "scroll", "form validation"]}))
    _reload(page, ctx.url)  # вернуть страницу в исходное состояние для скриншотов
    return out


def _request_failure(ctx, item: dict, failures: list[dict], state_note: str) -> Finding | None:
    """Клик сработал, но вызванный им запрос закончился ошибкой. 401/403 и 4xx от пустой формы не считаем:
    вход сброшен перезагрузкой, а форму мы отправляем без данных."""
    real = [x for x in failures
            if not (x.get("status") in (401, 403) or (item["inForm"] and 400 <= x.get("status", 0) < 500))]
    if not real:
        return None
    first = real[0]
    server = any(x.get("status", 0) >= 500 for x in real)
    what = f"HTTP {first['status']}" if "status" in first else f"no response ({first['error']})"
    more = f"; {len(real) - 1} more request(s) from this click failed too" if len(real) > 1 else ""
    return Finding(
        severity="critical" if item["critical"] or server else "warning", category=CATEGORY,
        rule="interaction/action-request-failed", page=ctx.path, selector=item["sel"], url=first["url"],
        message=f"Clicking {item['sel']} sends {first['method']} {_short(first['url'])}, which answers {what}",
        details=f"Clicking {item['sel']} on {ctx.path} sent {first['method']} {first['url']}, which answered "
                f"{what}{more}. The click itself works; the action it triggers does not.{state_note}",
        evidence={"requests": real[:5], "critical": item["critical"]})


def _short(url: str) -> str:
    u = urlparse(url)
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def _critical_state(ctx):
    """Запоминает на весь прогон, насколько близко каждый критичный селектор подошёл к клику."""
    track = ctx.site.cache.setdefault("critical_selectors", {"pages": [], "state": {}})
    if ctx.path not in track["pages"]:
        track["pages"].append(ctx.path)

    def state(selector: str, new: str) -> None:
        old = track["state"].get(selector)
        if old is None or CRITICAL_STATES.index(new) > CRITICAL_STATES.index(old):
            track["state"][selector] = new
    return state


def unchecked_critical(site) -> list[Finding]:
    """После обхода: критичные селекторы, которые ни на одной странице так и не удалось кликнуть."""
    track = site.cache.get("critical_selectors", {"pages": [], "state": {}})
    pages = track["pages"]
    where = f"on any of the {len(pages)} audited page(s) ({', '.join(pages)})" if pages else "(no page was audited)"
    out = []
    for c in dict.fromkeys(site.critical_selectors):
        st = track["state"].get(c, "missing")
        if st == "checked":
            continue
        out.append(Finding(
            severity="critical" if st == "missing" else "warning", category=CATEGORY,
            rule="interaction/critical-not-checked", page=pages[0] if pages else "/", selector=c,
            message=f"Critical selector {c} was not checked",
            details=f"Critical selector {c} {CRITICAL_REASONS[st]}{'' if st == 'invalid' else ' ' + where}, "
                    f"so this key action was never clicked.",
            evidence={"reason": st, "pages": pages}))
    return out
