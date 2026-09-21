"""Вёрстка: наложение текста, переполнение, горизонтальный скролл, контраст, зоны нажатия."""
from __future__ import annotations

import io

from PIL import Image

from browser import goto, new_page
from screenshots import annotate

VIEWPORTS = [(320, 700), (375, 800), (768, 900), (1024, 800), (1440, 900)]

ANALYZE_JS = """
() => {
  const vw = innerWidth, out = {overflowX: null, overlaps: [], clipped: [], small: [], offscreen: [], contrast: []};
  const de = document.documentElement;
  if (de.scrollWidth > vw + 1) out.overflowX = de.scrollWidth - vw;

  const lab = (el) => (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 30);
  const visible = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05 && r.width > 1 && r.height > 1;
  };
  const rgba = (s) => { const m = s.match(/[\\d.]+/g).map(Number); return {r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1}; };
  const lum = (c) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
    return .2126 * f(c.r) + .7152 * f(c.g) + .0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05); };

  // элементы, у которых есть собственный непустой текст
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName) || !visible(el)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    texts.push({el, rect: r});
  }

  // наложение текста на текст
  for (let i = 0; i < texts.length && out.overlaps.length < 15; i++) {
    for (let j = i + 1; j < texts.length; j++) {
      const a = texts[i], b = texts[j];
      if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
      // рамка строки включает запас шрифта над и под буквами: сравниваем центральные 60% высоты
      const core = (r) => ({top: r.top + r.height * 0.2, bottom: r.bottom - r.height * 0.2, h: r.height * 0.6});
      const ca = core(a.rect), cb = core(b.rect);
      const x = Math.min(a.rect.right, b.rect.right) - Math.max(a.rect.left, b.rect.left);
      const y = Math.min(ca.bottom, cb.bottom) - Math.max(ca.top, cb.top);
      if (x <= 2 || y <= 2) continue;
      const minH = Math.min(ca.h, cb.h), minW = Math.min(a.rect.width, b.rect.width);
      if (x * y / (minW * minH) > 0.35 && y > minH * 0.3) {
        out.overlaps.push({a: __qaPath(a.el), b: __qaPath(b.el), ta: lab(a.el),
          tb: lab(b.el),
          rect: {x: Math.max(a.rect.left, b.rect.left), y: Math.max(a.rect.top, b.rect.top), width: x, height: y}});
      }
    }
  }

  // текст обрезан контейнером
  for (const el of document.body.querySelectorAll('*')) {
    if (out.clipped.length >= 15) break;
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const clips = ['hidden', 'clip'].includes(cs.overflowX);
    if (clips && el.scrollWidth > el.clientWidth + 2 && el.innerText && el.innerText.trim() &&
        cs.textOverflow !== 'ellipsis') {
      out.clipped.push({sel: __qaPath(el), text: lab(el), rect: __qaRect(el)});
    }
  }

  // элементы за правой границей экрана
  // (внутри контейнера с горизонтальной прокруткой, который сам помещается в экран, это норма: карусели, табы)
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX) &&
          p.getBoundingClientRect().right <= vw + 2) return true;
    }
    return false;
  };
  for (const {el, rect} of texts) {
    if (out.offscreen.length < 10 && rect.right > vw + 2 && de.scrollWidth > vw + 1 && !inScroller(el))
      out.offscreen.push({sel: __qaPath(el), text: lab(el), rect: __qaRect(el)});
  }

  // мелкие зоны нажатия (актуально для мобильных)
  if (vw <= 768) {
    for (const el of document.querySelectorAll('a[href], button, [role=button], input:not([type=hidden]), select')) {
      if (!visible(el) || out.small.length >= 60) continue;
      const r = el.getBoundingClientRect();
      if (Math.round(r.width) < 44 || Math.round(r.height) < 44) out.small.push({sel: __qaPath(el), w: Math.round(r.width),
        h: Math.round(r.height), rect: __qaRect(el)});
    }
  }

  // контраст: фон складываем из слоёв родителей (шапка с rgba-фоном и т.п.);
  // если под текстом картинка или фон неизвестен, отдаём на проверку по пикселям
  const over = (t, b0) => { const a = t.a + b0.a * (1 - t.a);
    return {r: (t.r * t.a + b0.r * b0.a * (1 - t.a)) / a, g: (t.g * t.a + b0.g * b0.a * (1 - t.a)) / a,
            b: (t.b * t.a + b0.b * b0.a * (1 - t.a)) / a, a}; };
  const seen = new Set();
  for (const {el, rect: tr} of texts) {
    if (seen.has(el) || out.contrast.length >= 40) continue;
    if (!/[\\p{L}\\p{N}]/u.test(el.innerText || '')) continue;  // только символы (звёзды, стрелки)
    seen.add(el);
    const cs = getComputedStyle(el), fg0 = rgba(cs.color);
    let op = fg0.a;
    for (let p = el; p; p = p.parentElement) op *= +getComputedStyle(p).opacity;
    if (op < 0.6) continue;  // почти прозрачный текст: обычно идёт анимация появления
    const layers = []; let imageBg = false, base = null;
    for (let p = el; p; p = p.parentElement) {
      const pcs = getComputedStyle(p);
      if (pcs.backgroundImage !== 'none') { imageBg = true; break; }
      const c = rgba(pcs.backgroundColor);
      if (c.a > 0) layers.push(c);
      if (c.a > .95) { base = c; break; }
    }
    const size = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const label = lab(el);
    if (imageBg || !base) {
      out.contrast.push({sel: __qaPath(el), text: label, image: true, fg: fg0, op, large, rect: __qaRect(el),
        trect: {x: tr.x, y: tr.y, width: tr.width, height: tr.height}});
    } else {
      let cur = base;
      for (let i = layers.length - 2; i >= 0; i--) cur = over(layers[i], cur);
      const fg = {r: fg0.r * op + cur.r * (1 - op), g: fg0.g * op + cur.g * (1 - op), b: fg0.b * op + cur.b * (1 - op)};
      const cr = ratio(fg, cur), need = large ? 3 : 4.5;
      if (cr < need) out.contrast.push({sel: __qaPath(el), text: label, ratio: +cr.toFixed(2), need, rect: __qaRect(el)});
    }
  }
  return out;
}
"""


def _lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _ratio(a, b):
    l1, l2 = _lum(a), _lum(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


HIDE_ALL_CSS = ("html.qa-hide-all, html.qa-hide-all * { color: transparent !important; "
                "-webkit-text-fill-color: transparent !important; text-shadow: none !important; }")

TEXT_BOX_JS = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = document.createRange(); r.selectNodeContents(el);
  const b = r.getBoundingClientRect();
  return {x: b.x, y: b.y, width: b.width, height: b.height, vw: innerWidth, vh: innerHeight};
}"""


def _image_bg_contrast(page, item) -> float | None:
    """Худший контраст текста с фоном под ним: прячем ВЕСЬ текст страницы, снимаем область этого текста.
    Положение считаем заново: анимации и скриншоты других находок сдвигают вёрстку."""
    try:
        page.evaluate("""(css) => { if (!document.getElementById('__qa_hide')) {
            const s = document.createElement('style'); s.id = '__qa_hide'; s.textContent = css;
            document.head.appendChild(s); } }""", HIDE_ALL_CSS)
        box = page.evaluate(TEXT_BOX_JS, item["sel"])
        if not box:
            return None
        x0, y0 = max(0, box["x"]), max(0, box["y"])
        x1, y1 = min(box["vw"], box["x"] + box["width"]), min(box["vh"], box["y"] + box["height"])
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        page.evaluate("document.documentElement.classList.add('qa-hide-all')")
        try:
            png = page.screenshot(clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
        finally:
            page.evaluate("document.documentElement.classList.remove('qa-hide-all')")
        img = Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((60, 60))
        f, a = item["fg"], item["op"]
        ratios = []
        for px in getattr(img, "get_flattened_data", img.getdata)():
            eff = (f["r"] * a + px[0] * (1 - a), f["g"] * a + px[1] * (1 - a), f["b"] * a + px[2] * (1 - a))
            ratios.append(_ratio(eff, px))
        ratios.sort()
        # 10-й перцентиль худшего контраста, чтобы единичный пиксель не давал ложной тревоги
        return ratios[int(len(ratios) * 0.1)]
    except Exception:
        return None


def check_layout(browser, url, report, viewports=None, **_):
    for w, h in (viewports or VIEWPORTS):
        vp = f"{w}px"
        ctx, page = new_page(browser, report, url, {"width": w, "height": h})
        try:
            goto(page, url)
            res = page.evaluate(ANALYZE_JS)

            def emit(sev, msg, rects, sel="", name="layout"):
                shot = annotate(page, report, rects, f"{name}-{w}") if rects else ""
                report.add("layout", sev, msg, page=url, selector=sel, viewport=vp, screenshot=shot)

            if res["overflowX"]:
                emit("high", f"Горизонтальный скролл страницы: контент шире экрана на {res['overflowX']}px",
                     [o["rect"] for o in res["offscreen"]], name="overflow")
            for o in res["overlaps"]:
                emit("high", f"Текст накладывается на текст: «{o['ta']}» и «{o['tb']}»", [o["rect"]],
                     f"{o['a']}  ×  {o['b']}", "overlap")
            for c in res["clipped"]:
                emit("medium", f"Текст обрезан контейнером: «{c['text']}»", [c["rect"]], c["sel"], "clipped")
            if res["small"]:
                sm = res["small"]
                example = ", ".join(f"{x['sel'].split(' > ')[-1]} {x['w']}×{x['h']}" for x in sm[:3])
                emit("low", f"{len(sm)} элем. с зоной нажатия меньше 44×44px, например {example}",
                     [x["rect"] for x in sm], sm[0]["sel"], "tap")
            image_checked = 0
            for c in res["contrast"]:
                if c.get("image"):
                    if image_checked >= 10:
                        continue
                    image_checked += 1
                    r = _image_bg_contrast(page, c)
                    need = 3 if c["large"] else 4.5
                    if r is not None and r < need:
                        emit("medium", f"Низкий контраст текста «{c['text']}» на картинке: {r:.1f}:1 (нужно {need}:1)",
                             [c["rect"]], c["sel"], "contrast")
                else:
                    emit("medium", f"Низкий контраст текста «{c['text']}»: {c['ratio']}:1 (нужно {c['need']}:1)",
                         [c["rect"]], c["sel"], "contrast")
        finally:
            ctx.close()
