"""Шрифты: единообразие семейств, размеров, загрузка веб-шрифтов."""
from __future__ import annotations

from collections import Counter

from ..browser import goto, new_page

FONTS_JS = """
() => {
  const items = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement;
    if (!n.textContent.trim() || !el || seen.has(el) || ['SCRIPT','STYLE','NOSCRIPT'].includes(el.tagName)) continue;
    seen.add(el);
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1) continue;
    items.push({sel: __qaPath(el), tag: el.tagName.toLowerCase(), family: cs.fontFamily,
      size: parseFloat(cs.fontSize), weight: cs.fontWeight, chars: n.textContent.trim().length,
      text: n.textContent.trim().slice(0, 25)});
  }
  const declared = [...document.fonts].map(f => ({family: f.family.replace(/["']/g, ''), status: f.status}));
  return {items, declared};
}
"""

GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
           "ui-monospace", "-apple-system", "blinkmacsystemfont", "emoji", "math"}


def _primary(family: str) -> str:
    return family.split(",")[0].strip().strip("\"'").lower()


def check_fonts(browser, url, report, **_):
    ctx, page = new_page(browser, report, url)
    try:
        goto(page, url)
        page.evaluate("document.fonts.ready")
        data = page.evaluate(FONTS_JS)
        items = data["items"]
        if not items:
            return

        # 1. сколько разных основных шрифтов по объёму текста
        weight_by_family = Counter()
        for i in items:
            weight_by_family[_primary(i["family"])] += i["chars"]
        families = list(weight_by_family)
        if len(families) > 2:
            listing = ", ".join(f"{f} ({n} симв.)" for f, n in weight_by_family.most_common())
            report.add("fonts", "medium" if len(families) == 3 else "high",
                       f"Используется {len(families)} разных шрифтов: {listing}", page=url)
        # выбивающиеся шрифты: одна находка на семейство; шрифт только для заголовков считаем осознанной парой
        main, main_chars = weight_by_family.most_common(1)[0]
        total = sum(weight_by_family.values())
        if len(families) > 1 and main_chars / total > 0.6:
            for fam in families:
                if fam == main or weight_by_family[fam] / total >= 0.15:
                    continue
                users = [i for i in items if _primary(i["family"]) == fam]
                if all(i["tag"] in ("h1", "h2", "h3", "h4", "h5", "h6") for i in users):
                    continue
                sample = "; ".join(f"«{i['text']}»" for i in users[:3])
                report.add("fonts", "low", f"Шрифт «{fam}» выбивается на фоне основного «{main}» "
                           f"({len(users)} элем., например {sample})", page=url, selector=users[0]["sel"])

        # 2. веб-шрифты, которые не загрузились
        for d in data["declared"]:
            if d["status"] == "error":
                report.add("fonts", "high", f"Шрифт «{d['family']}» не загрузился, сработал запасной", page=url)

        # 3. шрифт из font-family не применился (первое семейство недоступно и не generic)
        for fam in set(_primary(i["family"]) for i in items):
            if fam in GENERIC:
                continue
            ok = page.evaluate("(f) => document.fonts.check('16px \"' + f + '\"')", fam)
            loaded = any(d["family"].lower() == fam and d["status"] == "loaded" for d in data["declared"])
            if not ok and not loaded:
                report.add("fonts", "medium", f"Шрифт «{fam}» указан в CSS, но недоступен: браузер показывает запасной",
                           page=url)

        # 4. хаотичные размеры и иерархия заголовков
        sizes = sorted({round(i["size"]) for i in items})
        if len(sizes) > 9:
            report.add("fonts", "low", f"Слишком много разных размеров шрифта ({len(sizes)}): {sizes}", page=url)
        avg = {}
        for i in items:
            if i["tag"] in ("h1", "h2", "h3", "h4", "h5", "h6"):
                avg.setdefault(i["tag"], []).append(i["size"])
        tags = sorted(avg)
        for a, b in zip(tags, tags[1:]):
            if max(avg[b]) > min(avg[a]) + 0.5:
                report.add("fonts", "low", f"Нарушена иерархия: {b} ({max(avg[b]):.0f}px) крупнее {a} "
                           f"({min(avg[a]):.0f}px)", page=url)
    finally:
        ctx.close()
