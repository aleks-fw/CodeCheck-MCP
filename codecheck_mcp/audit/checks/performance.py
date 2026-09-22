"""Performance: load, LCP, CLS, вес страницы, число запросов, тяжёлые JS и CSS (Navigation Timing и Performance API)."""
from __future__ import annotations

from .. import thresholds as T
from ..core.finding import Finding

CATEGORY = "performance"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "performance/slow-load": "Reduce what blocks the load event: defer non-critical scripts, lazy-load images below "
                             "the fold, and speed up slow requests (see network/slow-request findings).",
    "performance/slow-lcp": "Speed up the largest element in evidence: preload its image or font, serve it smaller "
                            "and from the same origin, and avoid rendering it from JavaScript.",
    "performance/layout-shift": "Reserve space for content that appears late (width/height on images, min-height for "
                                "banners and embeds) and do not insert content above what is already shown.",
    "performance/page-weight": "Cut the total download: compress images, remove unused JS and CSS, and lazy-load "
                               "what is not needed for the first screen.",
    "performance/too-many-requests": "Bundle small files, use sprites or inline SVG for icons, and lazy-load images "
                                     "below the fold.",
    "performance/large-js": "Split this bundle (code splitting / dynamic import), remove unused dependencies and "
                            "make sure it is minified and served compressed.",
    "performance/large-css": "Remove unused CSS, split critical CSS from the rest and serve it minified and "
                             "compressed.",
}

METRICS_JS = """() => new Promise((resolve) => {
  const nav = performance.getEntriesByType('navigation')[0];
  const out = {load: nav && nav.loadEventEnd > 0 ? nav.loadEventEnd : null, now: performance.now(),
               lcp: null, lcpSel: null, cls: null};
  const observe = (type, cb) => { try { new PerformanceObserver(l => l.getEntries().forEach(cb))
                                        .observe({type, buffered: true}); return true; } catch (e) { return false; } };
  observe('largest-contentful-paint', (e) => { out.lcp = e.startTime; out.lcpSel = e.element ? __ccSelector(e.element) : null; });
  // CLS как в web-vitals: максимум по «сессиям» сдвигов (разрыв < 1 с, окно < 5 с), без сдвигов после ввода
  let best = 0, cur = 0, first = 0, last = 0;
  const clsOk = observe('layout-shift', (e) => {
    if (e.hadRecentInput) return;
    if (cur && e.startTime - last < 1000 && e.startTime - first < 5000) { cur += e.value; }
    else { cur = e.value; first = e.startTime; }
    last = e.startTime; best = Math.max(best, cur);
  });
  setTimeout(() => { if (clsOk) out.cls = best; resolve(out); }, 200);
})"""


def _sizes(ctx) -> list[tuple[str, str, int]]:
    """(url, тип, переданные байты) для завершённых запросов."""
    out = []
    for req, rec in list(ctx.events.requests.items()):
        if rec["state"] != "finished":
            continue
        try:
            s = req.sizes()
        except Exception:
            continue
        out.append((req.url, req.resource_type, max(0, s["responseBodySize"]) + max(0, s["responseHeadersSize"])))
    return out


def run(page, ctx) -> list[Finding]:
    m = page.evaluate(METRICS_JS)
    out: list[Finding] = []
    p = ctx.path

    def add(rule, sev, message, details, **kw):
        out.append(Finding(severity=sev, category=CATEGORY, rule=rule, page=p, message=message, details=details, **kw))

    if m["load"] is not None and m["load"] > T.LOAD_WARNING_MS:
        add("performance/slow-load", "warning", f"Page load took {m['load'] / 1000:.1f} s",
            f"The load event on {p} fired {m['load']:.0f} ms after navigation start (limit {T.LOAD_WARNING_MS} ms).",
            evidence={"loadEventEndMs": round(m["load"])})
    elif m["load"] is None and m["now"] > T.LOAD_WARNING_MS:
        add("performance/slow-load", "warning", "Page load event did not fire",
            f"The load event on {p} had not fired {m['now']:.0f} ms after navigation start.",
            evidence={"loadEventEndMs": None, "elapsedMs": round(m["now"])})
    if m["lcp"] is not None and m["lcp"] > T.LCP_NOTICE_MS:
        sev = "warning" if m["lcp"] > T.LCP_WARNING_MS else "notice"
        add("performance/slow-lcp", sev, f"Largest Contentful Paint is {m['lcp'] / 1000:.1f} s",
            f"The largest element on {p}{' (' + m['lcpSel'] + ')' if m['lcpSel'] else ''} was painted "
            f"{m['lcp']:.0f} ms after navigation start (good: under {T.LCP_NOTICE_MS} ms).",
            selector=m["lcpSel"] or None, evidence={"lcpMs": round(m["lcp"])})
    if m["cls"] is not None and m["cls"] > T.CLS_NOTICE:
        sev = "warning" if m["cls"] > T.CLS_WARNING else "notice"
        add("performance/layout-shift", sev, f"Cumulative Layout Shift is {m['cls']:.2f}",
            f"Content on {p} moved while loading: CLS {m['cls']:.3f} (good: under {T.CLS_NOTICE}).",
            evidence={"cls": round(m["cls"], 3)})

    sizes = _sizes(ctx)
    total = sum(b for _, _, b in sizes)
    if total > T.PAGE_WEIGHT_WARNING_BYTES:
        add("performance/page-weight", "warning", f"Page weighs {total / 1024 / 1024:.1f} MB",
            f"{p} transferred {total // 1024} KB in {len(sizes)} responses "
            f"(limit {T.PAGE_WEIGHT_WARNING_BYTES // 1024 // 1024} MB).",
            evidence={"bytes": total, "largest": [{"url": u, "bytes": b} for u, _, b in
                                                  sorted(sizes, key=lambda x: -x[2])[:5]]})
    count = len(ctx.events.requests)
    if count > T.REQUEST_COUNT_NOTICE:
        add("performance/too-many-requests", "notice", f"{count} requests on one page",
            f"{p} made {count} requests while loading (limit {T.REQUEST_COUNT_NOTICE}).", evidence={"requests": count})
    seen: set[str] = set()
    for url, rtype, b in sizes:
        if url in seen:
            continue
        seen.add(url)
        if rtype == "script" and b > T.JS_FILE_WARNING_BYTES:
            add("performance/large-js", "warning", f"Large JavaScript file: {b // 1024} KB",
                f"{url} transferred {b // 1024} KB (limit {T.JS_FILE_WARNING_BYTES // 1024} KB).", url=url,
                evidence={"bytes": b})
        elif rtype == "stylesheet" and b > T.CSS_FILE_NOTICE_BYTES:
            add("performance/large-css", "notice", f"Large CSS file: {b // 1024} KB",
                f"{url} transferred {b // 1024} KB (limit {T.CSS_FILE_NOTICE_BYTES // 1024} KB).", url=url,
                evidence={"bytes": b})
    return out
