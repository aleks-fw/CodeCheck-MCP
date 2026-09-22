"""Accessibility: axe-core (WCAG 2.x A/AA) и то, чего в axe нет: onclick без клавиатуры и невидимый фокус."""
from __future__ import annotations

import io
from functools import cache
from pathlib import Path

from PIL import Image, ImageChops

from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "accessibility"
PER_VIEWPORT = False

AXE_PATH = Path(__file__).resolve().parents[2] / "vendor" / "axe.min.js"
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
IMPACT = {"critical": "critical", "serious": "warning", "moderate": "notice", "minor": "notice"}

# рекомендации для правил axe берутся из самого axe (help + helpUrl) во время прогона
RECOMMENDATIONS = {
    "accessibility/onclick-not-focusable": "Use a <button> (or <a href>) instead of a clickable <div>/<span>; if that "
                                           "is impossible, add tabindex=\"0\", role=\"button\" and Enter/Space key "
                                           "handlers.",
    "accessibility/focus-not-visible": "Do not remove the focus outline without a replacement: add a visible "
                                       ":focus-visible style (outline, box-shadow or border) for this element.",
}

AXE_RUN_JS = """async (tags) => {
  const res = await axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']});
  return res.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
    description: v.description,
    nodes: v.nodes.map(n => {
      const t = n.target && n.target.length === 1 && typeof n.target[0] === 'string' ? n.target[0] : null;
      let el = null; try { el = t ? document.querySelector(t) : null; } catch (e) {}
      return {sel: (el && __ccSelector(el)) || (n.target || []).flat(Infinity).join(' '),
              html: (n.html || '').slice(0, 300), summary: n.failureSummary || ''};
    })}));
}"""

ONCLICK_JS = """() => {
  const native = 'a[href], button, input, select, textarea, summary, iframe, [contenteditable=""], [contenteditable=true]';
  const out = [];
  for (const el of document.querySelectorAll('[onclick]')) {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1 || r.height < 1) continue;
    if (el.matches(native) || el.hasAttribute('tabindex') || el.closest('a[href], button')) continue;
    out.push({sel: __ccSelector(el), tag: el.tagName.toLowerCase(),
              text: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 40)});
  }
  return out;
}"""

NO_MOTION_CSS = "*, *::before, *::after { transition: none !important; animation: none !important; }"

FOCUSED_BOX_JS = """() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement || el.tagName === 'IFRAME') return null;
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return null;
  const m = 6;  // outline и тень рисуются снаружи рамки элемента
  const x = Math.max(0, r.x - m), y = Math.max(0, r.y - m);
  const width = Math.min(innerWidth, r.right + m) - x, height = Math.min(innerHeight, r.bottom + m) - y;
  if (width < 2 || height < 2) return {skip: true};  // элемент вне экрана (например, внутри fixed-блока)
  return {sel: __ccSelector(el), tag: el.tagName.toLowerCase(),
    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40), x, y, width, height};
}"""


@cache
def _axe_source() -> str:
    return AXE_PATH.read_text(encoding="utf-8")


def _axe(page, ctx) -> list[Finding]:
    page.evaluate(_axe_source())  # через CDP: CSP страницы не мешает
    out = []
    for v in page.evaluate(AXE_RUN_JS, AXE_TAGS):
        rule = f"accessibility/{v['id']}"
        RECOMMENDATIONS.setdefault(rule, f"{v['help']}. How to fix: {v['helpUrl']}")
        sev = IMPACT.get(v["impact"] or "", "notice")
        for n in v["nodes"][: T.AXE_MAX_NODES_PER_RULE]:
            out.append(Finding(
                severity=sev, category=CATEGORY, rule=rule, page=ctx.path, selector=n["sel"] or None,
                message=v["help"], details=f"{v['description']} {n['summary']}".strip(),
                evidence={"axeRule": v["id"], "impact": v["impact"], "helpUrl": v["helpUrl"], "html": n["html"],
                          "nodesWithThisRule": len(v["nodes"])}))
    return out


def _onclick(page, ctx) -> list[Finding]:
    return [Finding(
        severity="warning", category=CATEGORY, rule="accessibility/onclick-not-focusable", page=ctx.path,
        selector=e["sel"], message=f"Clickable <{e['tag']}> cannot be reached with the keyboard",
        details=f"<{e['tag']}> {e['sel']} «{e['text']}» on {ctx.path} has an onclick handler but is not focusable "
                f"(not a native control and has no tabindex), so keyboard users cannot activate it.")
        for e in page.evaluate(ONCLICK_JS)]


def _changed(a: bytes, b: bytes) -> bool:
    ia, ib = Image.open(io.BytesIO(a)).convert("RGB"), Image.open(io.BytesIO(b)).convert("RGB")
    if ia.size != ib.size:
        return True
    hist = ImageChops.difference(ia, ib).convert("L").histogram()
    return sum(hist[25:]) >= T.FOCUS_MIN_CHANGED_PIXELS  # пиксели, изменившиеся заметно (яркость > 24 из 255)


def _focus(page, ctx) -> list[Finding]:
    """Tab по первым элементам: снимок в фокусе и без фокуса; если пиксели не изменились, фокус не виден."""
    out: list[Finding] = []
    page.evaluate("""(css) => { const s = document.createElement('style'); s.id = '__cc_nomotion';
                     s.textContent = css; document.head.appendChild(s); }""", NO_MOTION_CSS)
    try:
        page.evaluate("() => { document.activeElement && document.activeElement.blur(); scrollTo(0, 0); }")
        seen = set()
        for _ in range(T.FOCUS_TAB_STOPS):
            page.keyboard.press("Tab")
            box = page.evaluate(FOCUSED_BOX_JS)
            if box is None or box.get("skip"):
                continue
            if box["sel"] in seen:  # фокус пошёл по второму кругу
                break
            seen.add(box["sel"])
            clip = {k: box[k] for k in ("x", "y", "width", "height")}
            focused = page.screenshot(clip=clip)
            page.evaluate("() => { window.__ccFocused = document.activeElement; document.activeElement.blur(); }")
            blurred = page.screenshot(clip=clip)
            page.evaluate("() => window.__ccFocused && window.__ccFocused.focus()")  # продолжить обход с того же места
            if not _changed(focused, blurred):
                label = f"«{box['text']}»" if box["text"] else f"<{box['tag']}>"
                out.append(Finding(
                    severity="warning", category=CATEGORY, rule="accessibility/focus-not-visible", page=ctx.path,
                    selector=box["sel"], message=f"No visible focus indicator on {label}",
                    details=f"When {box['sel']} on {ctx.path} receives keyboard focus (Tab), nothing around it "
                            f"changes on screen: no outline, shadow, border, background or other visual change.",
                    evidence={"method": "screenshot of the element with and without focus, 6px margin"}))
    finally:
        page.evaluate("() => { document.getElementById('__cc_nomotion')?.remove(); "
                      "document.activeElement && document.activeElement.blur(); scrollTo(0, 0); }")
    return out


def run(page, ctx) -> list[Finding]:
    out: list[Finding] = []
    failed = []
    for part in (_axe, _onclick, _focus):  # сбой одной части не отменяет результаты остальных
        try:
            out += part(page, ctx)
        except Exception as e:
            failed.append(f"{part.__name__.strip('_')}: {type(e).__name__}: {str(e)[:150]}")
    if failed:
        raise PartialFailure(out, "; ".join(failed))
    return out


class PartialFailure(Exception):
    """Часть проверки упала: найденное остальными частями сохраняется, ошибка идёт в Run errors."""

    def __init__(self, findings: list[Finding], message: str) -> None:
        super().__init__(message)
        self.findings = findings
