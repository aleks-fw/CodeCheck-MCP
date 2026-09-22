"""Фаза 4: вёрстка на разных viewport, шрифты, производительность."""
import functools
import http.server
import io
import os
import threading
import time

import pytest
from PIL import Image

from codecheck_mcp.audit.runner import audit

CLEAN = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Clean</title>
<style>body { margin: 16px; font-family: sans-serif; } button { min-width: 44px; min-height: 44px; }</style>
</head><body><h1>Clean layout</h1>
<p>Some text with an <a href="#x">inline link</a> inside the sentence.</p>
<button>OK</button></body></html>"""

LAYOUT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Layout</title>
<style>
body { margin: 0; font-family: sans-serif; }
.scroller { overflow-x: auto; width: 100%; white-space: nowrap; }
.slide { display: inline-block; width: 500px; }
.box, .ell { width: 60px; overflow: hidden; white-space: nowrap; }
.ell { text-overflow: ellipsis; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
a.tiny { display: inline-block; width: 16px; height: 16px; background: #333; }
button { min-width: 44px; min-height: 44px; }
</style></head><body>
<div class="outer"><div class="inner"><p class="wide" style="width: 600px">Wide paragraph</p></div></div>
<div class="scroller"><div class="slide">Slide one</div><div class="slide">Slide two</div></div>
<div class="box">Very long label text</div>
<div class="ell">Very long ellipsis text</div>
<span class="sr">Screen reader only text that is long</span>
<p>Read the <a href="#x">inline link</a> in text.</p>
<a class="tiny" href="#y" aria-label="icon"></a>
<button>OK</button>
</body></html>"""

FONTS = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Fonts</title>
<style>
@font-face { font-family: "Broken"; src: url("missing.woff2") format("woff2"); }
@font-face { font-family: "Slow"; src: url("/slow-font.woff2") format("woff2"); font-display: swap; }
h1 { font-family: "Broken", serif; } p { font-family: "Slow", sans-serif; }
</style></head><body><h1>Broken font heading</h1><p>Slow font text</p></body></html>"""

PERF = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Perf</title>
<link rel="stylesheet" href="big.css"><script src="big.js"></script></head><body>
<p class="lead">Text that moves down when the banner appears.</p>
<img class="hero" src="/slow.png" width="900" height="600" alt="Slow hero">
<img src="heavy.png" width="100" height="100" alt="Heavy">
DOTS
<script>setTimeout(() => { const b = document.createElement('div'); b.style.height = '400px';
  b.textContent = 'Late banner'; document.body.prepend(b); }, 300);</script>
</body></html>"""


def png_bytes(size, noise=False):
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if noise else Image.new("RGB", size, (40, 90, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    site = tmp_path_factory.mktemp("site")
    (site / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>i</title></head><body>'
        '<a href="clean.html">c</a> <a href="layout.html">l</a> <a href="fonts.html">f</a> <a href="perf.html">p</a>'
        '</body></html>', encoding="utf-8")
    (site / "clean.html").write_text(CLEAN, encoding="utf-8")
    (site / "layout.html").write_text(LAYOUT, encoding="utf-8")
    (site / "fonts.html").write_text(FONTS, encoding="utf-8")
    dots = "\n".join(f'<img src="dot.png?i={i}" width="1" height="1" alt="">' for i in range(101))
    (site / "perf.html").write_text(PERF.replace("DOTS", dots), encoding="utf-8")
    (site / "big.js").write_text("/*" + "x" * 600 * 1024 + "*/\nvar big = 1;\n")
    (site / "big.css").write_text("/*" + "y" * 200 * 1024 + "*/\nbody { color: #111; }\n")
    (site / "heavy.png").write_bytes(png_bytes((1100, 1000), noise=True))   # ~3.2 МБ
    (site / "dot.png").write_bytes(png_bytes((1, 1)))
    slow_png = png_bytes((900, 600))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/slow.png":
                time.sleep(4.2)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(slow_png)))
                self.end_headers()
                self.wfile.write(slow_png)
                return
            if self.path == "/slow-font.woff2":
                time.sleep(60)  # шрифт не приходит за время проверки (за 20 с Chromium уже сдаётся со статусом error)
                return
            super().do_GET()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(site)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        res = audit(f"http://127.0.0.1:{srv.server_address[1]}/index.html", max_pages=10,
                    checks=["layout", "fonts", "performance", "network"], output_dir=str(site / "out"))
    finally:
        srv.shutdown()
    return res


def on(res, page, prefix=""):
    return [f for f in res.findings if f.page == page and f.rule.startswith(prefix)]


def test_run_ok(result):
    assert result.data["errors"] == [], result.data["errors"]
    assert result.data["viewports"] == ["375x812", "768x1024", "1280x800"]
    assert len(result.data["pages"]) == 5


def test_clean_page_has_no_findings(result):
    assert [f.to_dict() for f in on(result, "/clean.html")] == []
    assert [f.to_dict() for f in on(result, "/index.html")] == []


def test_horizontal_overflow_only_at_375_with_deepest_element(result):
    f = on(result, "/layout.html", "layout/horizontal-overflow")
    assert len(f) == 1, [x.to_dict() for x in f]
    assert f[0].selector == ".wide" and f[0].viewport == "375x812" and f[0].severity == "warning"
    assert "viewports" not in f[0].evidence          # на 768 и 1280 скролла нет
    assert f[0].evidence["scrollWidth"] > f[0].evidence["clientWidth"]
    assert ".slide" not in " ".join(f[0].evidence["overflowingElements"])  # карусель в своём скролле не считается


def test_clipped_text_ignores_ellipsis_and_sr_only(result):
    f = on(result, "/layout.html", "layout/clipped-text")
    assert {x.selector for x in f} == {".box"}, [x.to_dict() for x in f]
    assert f[0].severity == "notice"


def test_small_tap_targets_only_at_375_and_not_inline_links(result):
    f = on(result, "/layout.html", "layout/small-tap-target")
    assert [x.selector for x in f] == ['[aria-label="icon"]'], [x.to_dict() for x in f]  # aria-label раньше класса
    assert f[0].viewport == "375x812" and f[0].evidence == {"width": 16, "height": 16}


def test_fonts(result):
    failed = on(result, "/fonts.html", "fonts/load-failed")
    assert len(failed) == 1 and failed[0].evidence["family"] == "Broken" and failed[0].selector == "h1"
    assert any(u.endswith("/missing.woff2") for u in failed[0].evidence["failedFontUrls"])
    fallback = on(result, "/fonts.html", "fonts/fallback-used")
    assert len(fallback) == 1 and fallback[0].evidence["family"] == "Slow" and fallback[0].severity == "notice"
    # отказ шрифта сообщает fonts, а не network
    assert on(result, "/fonts.html", "network/font-failed") == []


def test_performance(result):
    r = {f.rule: f for f in on(result, "/perf.html", "performance/")}
    assert r["performance/slow-load"].severity == "warning" and r["performance/slow-load"].evidence["loadEventEndMs"] > 4000
    lcp = r["performance/slow-lcp"]
    assert lcp.severity == "warning" and lcp.evidence["lcpMs"] > 4000 and lcp.selector == ".hero", lcp.to_dict()
    cls = r["performance/layout-shift"]
    assert cls.evidence["cls"] > 0.1, cls.to_dict()
    assert r["performance/page-weight"].severity == "warning" and r["performance/page-weight"].evidence["bytes"] > 3 * 2**20
    assert r["performance/too-many-requests"].evidence["requests"] > 100
    assert r["performance/large-js"].url.endswith("/big.js") and r["performance/large-js"].severity == "warning"
    assert r["performance/large-css"].url.endswith("/big.css") and r["performance/large-css"].severity == "notice"
    # на лёгких страницах метрик производительности нет
    assert on(result, "/clean.html", "performance/") == [] and on(result, "/layout.html", "performance/") == []
