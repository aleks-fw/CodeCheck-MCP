"""Layout: горизонтальный скролл, текст, обрезанный overflow, мелкие зоны нажатия (на каждом viewport)."""
from __future__ import annotations

from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "layout"
PER_VIEWPORT = True

RECOMMENDATIONS = {
    "layout/horizontal-overflow": "Make the element in selector fit the viewport: remove fixed widths wider than the "
                                  "screen (use max-width: 100%), allow text to wrap (overflow-wrap: anywhere) and "
                                  "check negative margins and transforms.",
    "layout/clipped-text": "Let the text fit: allow wrapping, reduce the font size at this width, or make the "
                           "container grow; if truncation is intended, add text-overflow: ellipsis and a full-text "
                           "tooltip.",
    "layout/small-tap-target": "Make the tap area at least 24×24 px (padding or min-width/min-height) so it can be "
                               "hit with a finger.",
}

LAYOUT_JS = """(opts) => {
  const vw = document.documentElement.clientWidth, de = document.documentElement;
  const vis = (el) => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const depth = (el) => { let d = 0; for (let p = el; p; p = p.parentElement) d++; return d; };
  const out = {scrollWidth: de.scrollWidth, clientWidth: vw, overflow: [], clipped: [], small: []};

  // 1. кто вылезает за правый край (кроме содержимого прокручиваемых каруселей, которые сами помещаются)
  const inFittingScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (['auto', 'scroll', 'hidden', 'clip'].includes(ox) && p.getBoundingClientRect().right <= vw + 1) return true;
    }
    return false;
  };
  if (de.scrollWidth > vw + 1) {
    const over = [...document.body.querySelectorAll('*')].filter(el =>
      vis(el) && el.getBoundingClientRect().right > vw + 1 && !inFittingScroller(el));
    over.sort((a, b) => depth(b) - depth(a));
    out.overflow = over.slice(0, 6).map(el => ({sel: __ccSelector(el), right: Math.round(el.getBoundingClientRect().right),
      tag: el.tagName.toLowerCase()}));
  }

  // 2. собственный текст элемента обрезан его overflow: hidden/clip (намеренное многоточие не считаем)
  for (const el of document.body.querySelectorAll('*')) {
    if (out.clipped.length >= 15) break;
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    if (!['hidden', 'clip'].includes(cs.overflowX) || cs.textOverflow === 'ellipsis') continue;
    if (el.scrollWidth <= el.clientWidth + 1 || el.clientWidth <= 1) continue;  // 1px: визуально скрытый текст
    const box = el.getBoundingClientRect(), right = box.left + el.clientLeft + el.clientWidth;
    for (const n of el.childNodes) {
      if (n.nodeType !== 3 || !n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      const tr = rg.getBoundingClientRect();
      if (tr.right > right + 1) {
        out.clipped.push({sel: __ccSelector(el), text: el.textContent.trim().replace(/\\s+/g, ' ').slice(0, 60),
          hiddenPx: Math.round(tr.right - right)});
        break;
      }
    }
  }

  // 3. мелкие зоны нажатия (ссылка внутри строки текста — исключение WCAG 2.5.8)
  if (opts.tap) {
    const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link]';
    for (const el of document.querySelectorAll(sel)) {
      if (out.small.length >= opts.maxSmall) break;
      if (!vis(el)) continue;
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (r.width >= opts.min && r.height >= opts.min) continue;
      if (cs.display === 'inline' && el.parentElement &&
          el.parentElement.textContent.trim().length > el.textContent.trim().length) continue;
      // вниз до 0.1 px: округление 23.6 до 24 давало в отчёте «24×24 меньше 24×24»
      const down = (v) => Math.floor(v * 10) / 10;
      out.small.push({sel: __ccSelector(el), w: down(r.width), h: down(r.height),
        tag: el.tagName.toLowerCase(), text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30)});
    }
  }
  return out;
}"""


def run(page, ctx) -> list[Finding]:
    tap = ctx.width == T.TAP_TARGET_VIEWPORT
    d = page.evaluate(LAYOUT_JS, {"tap": tap, "min": T.TAP_TARGET_MIN_PX, "maxSmall": T.MAX_SMALL_TARGETS})
    out: list[Finding] = []
    p, vp = ctx.path, ctx.viewport

    if d["overflow"]:
        deepest = d["overflow"][0]
        extra = d["scrollWidth"] - d["clientWidth"]
        out.append(Finding(
            severity="warning", category=CATEGORY, rule="layout/horizontal-overflow", page=p, viewport=vp,
            selector=deepest["sel"], message=f"Page scrolls horizontally at {ctx.width}px",
            details=f"At {vp} the page is {d['scrollWidth']}px wide in a {d['clientWidth']}px viewport "
                    f"({extra}px of horizontal scroll). The deepest element past the right edge is "
                    f"<{deepest['tag']}> {deepest['sel']} (right edge at {deepest['right']}px).",
            evidence={"scrollWidth": d["scrollWidth"], "clientWidth": d["clientWidth"],
                      "overflowingElements": [o["sel"] for o in d["overflow"]]}))
    for c in d["clipped"]:
        out.append(Finding(
            severity="notice", category=CATEGORY, rule="layout/clipped-text", page=p, viewport=vp, selector=c["sel"],
            message=f"Text is cut off: «{c['text'][:40]}»",
            details=f"At {vp} the text of {c['sel']} («{c['text']}») is {c['hiddenPx']}px wider than its container, "
                    f"which has overflow: hidden, so the end of the text is not visible.",
            evidence={"hiddenPx": c["hiddenPx"]}))
    for s in d["small"]:
        label = f"«{s['text']}»" if s["text"] else f"<{s['tag']}>"
        out.append(Finding(
            severity="notice", category=CATEGORY, rule="layout/small-tap-target", page=p, viewport=vp,
            selector=s["sel"], message=f"Tap target {label} is {s['w']}×{s['h']} px",
            details=f"At {vp} the interactive element {s['sel']} is {s['w']}×{s['h']} px, smaller than "
                    f"{T.TAP_TARGET_MIN_PX}×{T.TAP_TARGET_MIN_PX} px.",
            evidence={"width": s["w"], "height": s["h"]}))
    return out
