"""SEO: title, description, заголовки, lang, canonical, favicon, Open Graph; robots.txt и sitemap.xml раз на сайт."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..core.finding import Finding

CATEGORY = "seo"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "seo/missing-title": "Add a unique, descriptive <title> inside <head> (about 50-60 characters).",
    "seo/missing-description": "Add <meta name=\"description\" content=\"...\"> with a 1-2 sentence summary of the page.",
    "seo/missing-h1": "Give the page exactly one <h1> that names its main topic.",
    "seo/multiple-h1": "Keep one <h1> per page and turn the other top headings into <h2>.",
    "seo/heading-skip": "Do not skip heading levels: after an <h2> the next level is <h3>, not <h4>. Change the tag, "
                        "and restyle it with CSS if the size was the reason.",
    "seo/missing-lang": "Add the page language to the root element, for example <html lang=\"en\">.",
    "seo/missing-canonical": "Add <link rel=\"canonical\" href=\"<absolute URL of this page>\"> to <head>.",
    "seo/missing-favicon": "Add a favicon: <link rel=\"icon\" href=\"/favicon.png\"> or a /favicon.ico file.",
    "seo/missing-open-graph": "Add the missing Open Graph tags (og:title, og:description, og:image) so links to the "
                              "page get a proper preview in messengers and social networks.",
    "seo/missing-robots": "Add /robots.txt at the site root (it can simply allow everything and point to the sitemap).",
    "seo/missing-sitemap": "Add /sitemap.xml listing the public pages, and reference it from robots.txt.",
}

PAGE_JS = """() => {
  const meta = (sel) => { const m = document.querySelector(sel); return m ? (m.getAttribute('content') || '').trim() : null; };
  const headings = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map(h => ({
    level: +h.tagName[1], sel: __ccSelector(h), text: (h.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60)}));
  return {
    title: (document.querySelector('head > title, title')?.textContent || '').trim(),
    description: meta('meta[name="description" i]'),
    lang: (document.documentElement.getAttribute('lang') || '').trim(),
    canonical: !!document.querySelector('link[rel~="canonical" i][href]'),
    iconLink: !!document.querySelector('link[rel~="icon" i][href], link[rel="apple-touch-icon" i][href]'),
    og: {title: meta('meta[property="og:title"]'), description: meta('meta[property="og:description"]'),
         image: meta('meta[property="og:image"]')},
    headings,
  };
}"""


def _fetch(ctx, path: str) -> tuple[int | None, str, str]:
    """GET по тому же origin: (статус, content-type, начало тела). Результат кешируется на весь прогон."""
    key = f"seo-fetch:{path}"
    if key not in ctx.site.cache:
        try:
            r = ctx.browser_context.request.get(ctx.site.origin + path, timeout=10000, max_redirects=5)
            ctx.site.cache[key] = (r.status, r.headers.get("content-type", ""), r.body()[:2000].decode("utf-8", "replace"))
        except Exception:
            ctx.site.cache[key] = (None, "", "")
    return ctx.site.cache[key]


def _is_html(ctype: str, body: str) -> bool:
    # SPA и многие хостинги на любой путь отдают index.html с кодом 200
    return "html" in ctype.lower() or body.lstrip().lower().startswith(("<!doctype", "<html"))


def run(page, ctx) -> list[Finding]:
    d: dict[str, Any] = page.evaluate(PAGE_JS)
    out: list[Finding] = []

    def add(rule, sev, message, details, selector=None, url=None, evidence=None, path=None):
        out.append(Finding(severity=sev, category=CATEGORY, rule=rule, page=path or ctx.path, message=message,
                           details=details, selector=selector, url=url, evidence=evidence))

    p = ctx.path
    if not d["title"]:
        add("seo/missing-title", "warning", "Page has no title",
            f"{p} has no <title> element or its text is empty.", selector="html")
    if not d["description"]:
        state = "is empty" if d["description"] == "" else "is missing"
        add("seo/missing-description", "warning", "Page has no meta description",
            f"<meta name=\"description\"> on {p} {state}.")
    h1 = [h for h in d["headings"] if h["level"] == 1]
    if not h1:
        add("seo/missing-h1", "warning", "Page has no <h1>", f"{p} has no <h1> element.")
    elif len(h1) > 1:
        add("seo/multiple-h1", "notice", f"Page has {len(h1)} <h1> elements",
            f"{p} has {len(h1)} <h1> elements: " + "; ".join(f"«{h['text']}»" for h in h1[:5]) + ".",
            selector=h1[1]["sel"], evidence={"count": len(h1), "selectors": [h["sel"] for h in h1[:10]]})
    prev = None
    skips = 0
    for h in d["headings"]:
        if prev is not None and h["level"] > prev["level"] + 1 and skips < 10:
            skips += 1
            add("seo/heading-skip", "notice", f"Heading level skipped: h{prev['level']} → h{h['level']}",
                f"On {p} the heading «{h['text']}» is <h{h['level']}> but the previous heading «{prev['text']}» "
                f"is <h{prev['level']}>; level h{prev['level'] + 1} is skipped.", selector=h["sel"],
                evidence={"previous": prev["sel"], "previousLevel": prev["level"], "level": h["level"]})
        prev = h
    if not d["lang"]:
        add("seo/missing-lang", "warning", "<html> has no lang attribute",
            f"The root <html> element of {p} has no lang attribute.", selector="html")
    if not d["canonical"]:
        add("seo/missing-canonical", "notice", "No canonical link", f"{p} has no <link rel=\"canonical\">.")
    if not d["iconLink"]:
        status, ctype, body = _fetch(ctx, "/favicon.ico")
        if status != 200 or _is_html(ctype, body):
            add("seo/missing-favicon", "notice", "No favicon",
                f"{p} declares no <link rel=\"icon\"> and /favicon.ico answered "
                f"{status if status is not None else 'nothing'}.")
    missing_og = [f"og:{k}" for k, v in d["og"].items() if not v]
    if missing_og:
        add("seo/missing-open-graph", "notice", "Open Graph tags missing: " + ", ".join(missing_og),
            f"{p} has no " + ", ".join(missing_og) + " meta tags.", evidence={"missing": missing_og})

    if ctx.site.first_time("seo-site"):
        status, ctype, body = _fetch(ctx, "/robots.txt")
        robots_ok = status == 200 and not _is_html(ctype, body)
        if not robots_ok:
            add("seo/missing-robots", "notice", "No robots.txt",
                f"{ctx.site.origin}/robots.txt answered {status if status is not None else 'nothing'}"
                f"{' with an HTML page' if status == 200 else ''}.",
                url=ctx.site.origin + "/robots.txt", path="/robots.txt")
        sitemap_path = "/sitemap.xml"
        if robots_ok:
            for line in body.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_path = urlparse(line.split(":", 1)[1].strip()).path or sitemap_path
                    break
        status, ctype, body = _fetch(ctx, sitemap_path)
        if status != 200 or not ("<urlset" in body or "<sitemapindex" in body):
            add("seo/missing-sitemap", "notice", "No sitemap",
                f"{ctx.site.origin}{sitemap_path} answered {status if status is not None else 'nothing'}"
                f"{' but is not a sitemap' if status == 200 else ''}.",
                url=ctx.site.origin + sitemap_path, path=sitemap_path)
    return out
