"""Fonts: шрифт из @font-face не загрузился; текст показан запасным шрифтом вместо объявленного."""
from __future__ import annotations

from ..core.finding import Finding

CATEGORY = "fonts"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "fonts/load-failed": "Fix the src URL in this @font-face rule (the file in evidence did not load) or remove the "
                         "rule; check the file format and the server's CORS headers for fonts on another domain.",
    "fonts/fallback-used": "The declared font had not loaded when the page was shown: preload it "
                           "(<link rel=\"preload\" as=\"font\" crossorigin>), serve it faster, or use "
                           "font-display: swap with a similar fallback font.",
}

FONTS_JS = """() => {
  const faces = [...document.fonts].map(f => ({family: f.family.replace(/^["']|["']$/g, ''), status: f.status,
    weight: f.weight, style: f.style}));
  // первое семейство из font-family у видимого текста
  const used = {};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement;
    if (!n.textContent.trim() || !el || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1) continue;
    const fam = cs.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
    if (!used[fam]) used[fam] = {sel: __ccSelector(el), text: n.textContent.trim().slice(0, 40), count: 0};
    used[fam].count++;
  }
  return {faces, used};
}"""


def _failed_font_urls(ctx) -> list[str]:
    urls = []
    for req, rec in list(ctx.events.requests.items()):
        if req.resource_type == "font" and (rec["state"] == "failed" or (rec["status"] or 0) >= 400):
            urls.append(req.url)
    return urls


def run(page, ctx) -> list[Finding]:
    try:  # goto ждёт шрифты не дольше 3 с; здесь ещё раз, коротко
        page.evaluate("Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 1000))]).then(() => 1)")
    except Exception:
        pass
    d = page.evaluate(FONTS_JS)
    out: list[Finding] = []
    p = ctx.path
    failed_urls = _failed_font_urls(ctx)

    errored = sorted({f["family"] for f in d["faces"] if f["status"] == "error"})
    for fam in errored:
        user = d["used"].get(fam)
        out.append(Finding(
            severity="warning", category=CATEGORY, rule="fonts/load-failed", page=p, selector=user["sel"] if user else None,
            message=f"Font «{fam}» failed to load",
            details=f"The @font-face font «{fam}» on {p} has status error"
                    + (f"; text such as «{user['text']}» ({user['sel']}) is shown in a fallback font" if user else "")
                    + (f". Font files that failed on this page: {', '.join(failed_urls[:5])}" if failed_urls else "")
                    + ".",
            evidence={"family": fam, "failedFontUrls": failed_urls[:10]}))

    by_family: dict[str, list[str]] = {}
    for f in d["faces"]:
        by_family.setdefault(f["family"], []).append(f["status"])
    for fam, info in d["used"].items():
        statuses = by_family.get(fam)
        # объявлен через @font-face, используется видимым текстом, но так и не загрузился (и не упал с ошибкой)
        if not statuses or fam in errored or "loaded" in statuses:
            continue
        out.append(Finding(
            severity="notice", category=CATEGORY, rule="fonts/fallback-used", page=p, selector=info["sel"],
            message=f"Text is shown in a fallback font instead of «{fam}»",
            details=f"{info['count']} text node(s) on {p}, e.g. «{info['text']}» ({info['sel']}), use font-family "
                    f"«{fam}», declared with @font-face, but the font was still {'/'.join(sorted(set(statuses)))} "
                    f"after the page loaded, so the browser shows a fallback font.",
            evidence={"family": fam, "status": sorted(set(statuses)), "textNodes": info["count"]}))
    return out
