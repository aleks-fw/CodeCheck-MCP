"""Изображения: только измеримое (битые, искажённые, мыльные, тяжёлые, без alt)."""
from __future__ import annotations

from ..browser import goto, new_page
from ..screenshots import annotate

HEAVY_BYTES = 500 * 1024

IMAGES_JS = """
async () => {
  // подгрузить ленивые картинки
  for (let y = 0; y < document.body.scrollHeight; y += innerHeight) { scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
  scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 400));
  const sizes = {};
  for (const e of performance.getEntriesByType('resource'))
    if (e.initiatorType === 'img' || /\\.(png|jpe?g|webp|gif|avif|svg)(\\?|$)/i.test(e.name)) sizes[e.name] = e.encodedBodySize || 0;
  const out = [];
  for (const img of document.images) {
    const cs = getComputedStyle(img), r = img.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    out.push({sel: __qaPath(img), src: (img.currentSrc || img.src || '').slice(0, 120), complete: img.complete,
      nw: img.naturalWidth, nh: img.naturalHeight, w: r.width, h: r.height, fit: cs.objectFit,
      hasAlt: img.hasAttribute('alt'), alt: img.getAttribute('alt') || '', dpr: devicePixelRatio,
      bytes: sizes[img.currentSrc || img.src] || 0, rect: __qaRect(img),
      inLink: !!img.closest('a, button')});
  }
  return out;
}
"""


def check_images(browser, url, report, **_):
    ctx, page = new_page(browser, report, url)
    try:
        goto(page, url)
        images = page.evaluate(IMAGES_JS)

        def add(sev, msg, im):
            shot = annotate(page, report, [im["rect"]], "image") if im["rect"]["width"] else ""
            report.add("images", sev, msg, page=url, selector=im["sel"], screenshot=shot)

        for im in images:
            name = im["src"].rsplit("/", 1)[-1] or im["src"]
            if im["complete"] and im["nw"] == 0:
                add("high", f"Картинка не загрузилась: {name}", im)
                continue
            if not im["complete"]:
                continue
            # искажённые пропорции (object-fit решает проблему, поэтому только fill/none)
            if im["fit"] in ("fill", "none") and im["w"] > 20 and im["h"] > 20 and im["nh"]:
                natural, shown = im["nw"] / im["nh"], im["w"] / im["h"]
                if abs(natural - shown) / natural > 0.05:
                    add("medium", f"Картинка {name} растянута или сплющена: оригинал {natural:.2f}:1, "
                                  f"на странице {shown:.2f}:1", im)
            # низкое разрешение
            if im["w"] > 40 and im["nw"] < im["w"] * im["dpr"] * 0.8:
                add("low", f"Картинка {name} мыльная: {im['nw']}px растянуты до {round(im['w'])}px", im)
            if im["bytes"] > HEAVY_BYTES:
                add("low", f"Тяжёлая картинка {name}: {im['bytes'] // 1024} КБ", im)
            if not im["hasAlt"]:
                add("low", f"У картинки {name} нет атрибута alt", im)
            elif not im["alt"].strip() and im["inLink"]:
                add("medium", f"Картинка {name} внутри ссылки или кнопки с пустым alt: у элемента нет названия", im)
    finally:
        ctx.close()
