"""Images: не загрузились, нет alt, тяжёлые файлы, натуральный размер намного больше отображаемого."""
from __future__ import annotations

from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "images"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "images/broken": "Fix the image path or replace the file: the browser could not decode or load it.",
    "images/missing-alt": "Add an alt attribute: describe the image in a few words, or use alt=\"\" if it is purely "
                          "decorative.",
    "images/heavy": "Compress the image (WebP/AVIF, quality 75-85) and resize it to the size it is displayed at.",
    "images/oversized": "Serve a smaller file or use srcset/sizes so the browser downloads an image close to the "
                        "displayed size.",
}

IMAGES_JS = """async () => {
  // догружаем ленивые картинки
  for (let y = 0; y < document.body.scrollHeight; y += innerHeight) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 100));
  }
  scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 300));
  const sizes = {};
  for (const e of performance.getEntriesByType('resource')) sizes[e.name] = e.encodedBodySize || 0;
  const out = [];
  for (const img of document.images) {
    const cs = getComputedStyle(img), r = img.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1 || r.height < 1) continue;
    const src = img.currentSrc || img.src || '';
    const role = (img.getAttribute('role') || '').toLowerCase();
    out.push({sel: __ccSelector(img), src, complete: img.complete, nw: img.naturalWidth, nh: img.naturalHeight,
      w: r.width, h: r.height, dpr: devicePixelRatio, perfBytes: sizes[src] || 0,
      hasAlt: img.hasAttribute('alt'),
      decorative: role === 'presentation' || role === 'none' || img.getAttribute('aria-hidden') === 'true' ||
                  img.hasAttribute('aria-label') || img.hasAttribute('aria-labelledby')});
  }
  return out;
}"""


def _bytes_by_url(ctx) -> dict[str, int]:
    """Переданный размер тела ответа для картинок (из сетевых событий, работает и для чужих доменов)."""
    out = {}
    for req, rec in list(ctx.events.requests.items()):
        if req.resource_type == "image" and rec["state"] == "finished":
            try:
                out[req.url] = req.sizes()["responseBodySize"]
            except Exception:
                continue
    return out


def run(page, ctx) -> list[Finding]:
    images = page.evaluate(IMAGES_JS)
    sizes = _bytes_by_url(ctx)
    out: list[Finding] = []
    heavy_seen: set[str] = set()
    p = ctx.path

    def add(rule, sev, message, details, selector=None, url=None, evidence=None):
        out.append(Finding(severity=sev, category=CATEGORY, rule=rule, page=p, message=message, details=details,
                           selector=selector, url=url, evidence=evidence))

    for im in images:
        src = im["src"]
        name = src.rsplit("/", 1)[-1][:80] if src and not src.startswith("data:") else "(inline image)"
        url = src if src.startswith(("http://", "https://")) else None
        if not im["hasAlt"] and not im["decorative"]:
            add("images/missing-alt", "warning", f"Image {name} has no alt attribute",
                f"<img> {im['sel']} on {p} has no alt attribute, so screen readers cannot describe it.",
                selector=im["sel"])
        if not src:
            continue
        if im["complete"] and im["nw"] == 0:
            add("images/broken", "warning", f"Image did not load: {name}",
                f"<img> {im['sel']} on {p} finished loading {src[:200]} but has no pixels (naturalWidth 0).",
                selector=im["sel"], url=url, evidence={"src": src[:500]})
            continue
        if not im["complete"]:
            continue
        size = sizes.get(src) or im["perfBytes"]
        if size > T.IMAGE_NOTICE_BYTES and url and url not in heavy_seen:
            heavy_seen.add(url)
            sev = "warning" if size > T.IMAGE_WARNING_BYTES else "notice"
            add("images/heavy", sev, f"Heavy image: {name} is {size // 1024} KB",
                f"{src[:200]} on {p} transfers {size // 1024} KB "
                f"(limit {T.IMAGE_NOTICE_BYTES // 1024} KB, warning above {T.IMAGE_WARNING_BYTES // 1024} KB).",
                url=url, evidence={"bytes": size})
        is_svg = src.lower().split("?")[0].endswith(".svg") or src.startswith("data:image/svg")
        ratio = T.IMAGE_OVERSIZE_RATIO
        if not is_svg and im["nw"] > ratio * im["w"] * im["dpr"] and im["nh"] > ratio * im["h"] * im["dpr"]:
            add("images/oversized", "notice", f"Image {name} is much larger than displayed",
                f"<img> {im['sel']} on {p} is {im['nw']}×{im['nh']} px but displayed at "
                f"{round(im['w'])}×{round(im['h'])} px (more than {ratio:g}× larger in both directions).",
                selector=im["sel"], url=url,
                evidence={"natural": [im["nw"], im["nh"]], "displayed": [round(im["w"]), round(im["h"])],
                          "viewport": ctx.viewport})
    return out
