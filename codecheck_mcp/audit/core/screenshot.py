"""Скриншоты для critical и warning: проблемный элемент обводится красным, после снимка обводка убирается."""
from __future__ import annotations

HIGHLIGHT_JS = """(sel) => {
  let el = null;
  try { el = document.querySelector(sel); } catch (e) { return false; }
  if (!el) return false;
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  window.__ccOutline = {el, value: el.style.getPropertyValue('outline'),
                        priority: el.style.getPropertyPriority('outline')};
  el.style.setProperty('outline', '3px solid red', 'important');
  return true;
}"""

UNHIGHLIGHT_JS = """() => {
  const s = window.__ccOutline;
  if (!s) return;
  if (s.value) s.el.style.setProperty('outline', s.value, s.priority);
  else s.el.style.removeProperty('outline');
  window.__ccOutline = null;
}"""


def capture(page, selector: str | None) -> bytes | None:
    """PNG текущего экрана; если элемент найден, он в центре и обведён. None, если снимок не удался."""
    try:
        highlighted = bool(selector) and page.evaluate(HIGHLIGHT_JS, selector)
        try:
            return page.screenshot()
        finally:
            if highlighted:
                page.evaluate(UNHIGHLIGHT_JS)
    except Exception:
        return None
