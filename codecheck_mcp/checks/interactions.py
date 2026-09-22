"""Интерактив: мёртвые кнопки, ложные реакции, перекрытые кнопки, формы, битые якоря."""
from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag

from ..browser import goto, new_page
from ..screenshots import annotate

MAX_CANDIDATES = 40
CLICK_TIMEOUT_MS = 3000

# помечает кандидатов data-qa-i и возвращает их описание; порядок детерминирован, поэтому
# на свежей странице тот же индекс указывает на тот же элемент
COLLECT_JS = """
() => {
  const CONTROL = 'button, a[href], [role=button], [role=link], [role=tab], [onclick], ' +
    'input[type=submit], input[type=button], input[type=reset], summary';
  const vis = (el) => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 1 && r.height > 1; };
  const items = [], stubs = [], broken = [];
  let n = 0;
  for (const el of document.querySelectorAll(CONTROL)) {
    if (!vis(el)) continue;
    const item = {i: n, kind: 'control', sel: __qaPath(el), rect: __qaRect(el),
      text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30),
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      tag: el.tagName.toLowerCase(), skip: false, formEmpty: false};
    if (el.tagName === 'A') {
      const href = (el.getAttribute('href') || '').trim();
      if (href === '' || href === '#' || /^javascript:(void\\(0\\))?;?$/i.test(href)) {
        stubs.push({sel: item.sel, text: item.text, href, rect: item.rect}); item.skip = true;
      } else if (href.startsWith('#')) {
        const id = decodeURIComponent(href.slice(1));
        if (id === 'top') item.skip = true;  // ведёт наверх: на верху страницы клик ничего не меняет
        else if (!document.getElementById(id) && !document.getElementsByName(id).length) {
          broken.push({sel: item.sel, text: item.text, href, rect: item.rect}); item.skip = true;
        }
      } else if (/^(mailto|tel|sms):/i.test(href) || el.hasAttribute('download')) {
        item.skip = true;
      } else {
        try {
          const u = new URL(el.href, location.href);
          const strip = (x) => x.origin + x.pathname.replace(/index\\.html$/, '') + x.search;
          if (u.host !== location.host) item.skip = true;
          else if (!u.hash && strip(u) === strip(location)) item.skip = true;  // ссылка на эту же страницу
        } catch (e) { item.skip = true; }
      }
    }
    const isSubmit = el.type === 'submit' || (el.tagName === 'BUTTON' && !el.getAttribute('type'));
    if (isSubmit && el.form && [...el.form.querySelectorAll('[required]')].some(f => !f.value)) item.formEmpty = true;
    el.setAttribute('data-qa-i', n++);
    items.push(item);
  }
  // «выглядит кликабельным», но не является элементом управления
  let fakes = 0;
  const skipTags = new Set(['HTML', 'BODY', 'LABEL', 'SELECT', 'OPTION', 'INPUT', 'TEXTAREA', 'VIDEO', 'AUDIO']);
  for (const el of document.body.querySelectorAll('*')) {
    if (fakes >= 15) break;
    if (skipTags.has(el.tagName) || !vis(el) || el.closest(CONTROL + ', label')) continue;
    if (getComputedStyle(el).cursor !== 'pointer') continue;
    if (el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer') continue;
    if (el.querySelector(CONTROL)) continue;
    items.push({i: n, kind: 'fake', sel: __qaPath(el), rect: __qaRect(el),
      text: (el.innerText || el.alt || '').trim().slice(0, 30), disabled: false, tag: el.tagName.toLowerCase(),
      skip: false, formEmpty: false});
    el.setAttribute('data-qa-i', n++); fakes++;
  }
  return {items, stubs, broken};
}
"""

STATE_JS = """
() => { const s = document.documentElement.outerHTML; let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return {url: location.href, dom: h, y: scrollY}; }
"""


def _probe(browser, report, url, idx, action="click", force=False):
    """Кликает элемент на свежей странице и возвращает, что произошло."""
    ctx, page = new_page(browser, report, url)
    ev: dict[str, Any] = {"popup": 0, "dialog": 0, "download": 0, "reqs": 0, "posts": 0, "error": ""}
    try:
        goto(page, url)
        page.evaluate(COLLECT_JS)
        before = page.evaluate(STATE_JS)
        ctx.on("page", lambda p: ev.__setitem__("popup", ev["popup"] + 1))
        def on_dialog(d):
            ev["dialog"] += 1
            d.dismiss()
        page.on("dialog", on_dialog)
        page.on("download", lambda d: ev.__setitem__("download", ev["download"] + 1))

        def on_req(r):
            if r.resource_type in ("xhr", "fetch", "document") or r.method != "GET":
                ev["reqs"] += 1
                if r.method != "GET":
                    ev["posts"] += 1
        page.on("request", on_req)

        loc = page.locator(f'[data-qa-i="{idx}"]')
        try:
            if action == "dblclick":
                loc.dblclick(timeout=CLICK_TIMEOUT_MS, force=force)
            else:
                loc.click(timeout=CLICK_TIMEOUT_MS, force=force)
        except Exception as e:
            ev["error"] = str(e)
            return ev, False
        page.wait_for_timeout(500)
        changed = False
        if urldefrag(page.url)[0] != urldefrag(before["url"])[0] or page.url != before["url"]:
            changed = True
        else:
            try:
                after = page.evaluate(STATE_JS)
                changed = after["dom"] != before["dom"] or abs(after["y"] - before["y"]) > 1
            except Exception:
                changed = True  # контекст уничтожен переходом
        ev["url_changed"] = urldefrag(page.url)[0] != urldefrag(before["url"])[0]
        effect = changed or any(ev[k] for k in ("popup", "dialog", "download", "reqs"))
        return ev, effect
    finally:
        ctx.close()


def _shot(browser, report, url, rect, name):
    """Скриншот страницы с рамкой на проблемном элементе (на свежей загрузке)."""
    ctx, page = new_page(browser, report, url)
    try:
        goto(page, url)
        return annotate(page, report, [rect], name)
    finally:
        ctx.close()


def check_interactions(browser, url, report, **_):
    ctx, page = new_page(browser, report, url)
    try:
        goto(page, url)
        data = page.evaluate(COLLECT_JS)
    finally:
        ctx.close()

    for s in data["stubs"]:
        report.add("interactions", "low", f"Ссылка-заглушка href=\"{s['href']}\": «{s['text']}» никуда не ведёт",
                   page=url, selector=s["sel"], screenshot=_shot(browser, report, url, s["rect"], "stub"))
    for b in data["broken"]:
        report.add("interactions", "high", f"Битый якорь {b['href']}: на странице нет такого элемента («{b['text']}»)",
                   page=url, selector=b["sel"], screenshot=_shot(browser, report, url, b["rect"], "anchor"))

    for it in [i for i in data["items"] if not i["skip"]][:MAX_CANDIDATES]:
        label = f"«{it['text']}»" if it["text"] else f"<{it['tag']}>"

        def add(sev, msg, it=it):
            report.add("interactions", sev, msg, page=url, selector=it["sel"],
                       screenshot=_shot(browser, report, url, it["rect"], "button"))

        ev, effect = _probe(browser, report, url, it["i"], force=it["disabled"])

        if ev["error"]:
            if "intercepts pointer events" in ev["error"]:
                add("high", f"Кнопка {label} перекрыта другим элементом, на неё нельзя нажать")
        elif it["kind"] == "fake":
            if not effect:
                add("low", f"{label} выглядит кликабельным (курсор-рука), но не реагирует")
        elif it["disabled"]:
            if effect:
                add("high", f"Отключённая кнопка {label} всё равно реагирует на клик")
        elif it["formEmpty"]:
            if ev["posts"] or ev.get("url_changed"):
                add("high", f"Форма отправляется с пустыми обязательными полями (кнопка {label})")
        elif not effect:
            add("medium", f"Кнопка {label} не реагирует на клик")
        elif ev["posts"] and it["tag"] != "a":
            ev2, _ = _probe(browser, report, url, it["i"], action="dblclick")
            if ev2["posts"] > ev["posts"]:
                add("medium", f"Двойной клик по {label} отправляет запрос повторно "
                              f"({ev2['posts']} вместо {ev['posts']})")
