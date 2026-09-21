"""Скриншоты с красными рамками на проблемных элементах."""
from __future__ import annotations

import itertools

from .report import Report

_counter = itertools.count(1)

_DRAW = """(rects) => {
  const wrap = document.createElement('div');
  wrap.id = '__qa_overlay';
  wrap.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;z-index:2147483647';
  for (const r of rects) {
    const b = document.createElement('div');
    b.style.cssText = `position:absolute;left:${r.x + scrollX}px;top:${r.y + scrollY}px;` +
      `width:${r.width}px;height:${r.height}px;outline:3px solid #ff0033;background:rgba(255,0,51,.12)`;
    wrap.appendChild(b);
  }
  document.body.appendChild(wrap);
}"""


def annotate(page, report: Report, rects: list[dict], name: str) -> str:
    """Делает скриншот с рамками, возвращает путь относительно папки отчёта ('' при неудаче)."""
    try:
        d = report.ensure_dir()
        rel = f"shots/{next(_counter):03d}-{name}.png"
        page.evaluate(_DRAW, rects)
        page.screenshot(path=str(d / rel), full_page=True)
        page.evaluate("document.getElementById('__qa_overlay')?.remove()")
        return rel
    except Exception:
        return ""
