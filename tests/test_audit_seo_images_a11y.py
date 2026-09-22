"""Фаза 3: SEO, изображения, доступность (axe и свои проверки), дедупликация пересечений."""
import os

import pytest
from PIL import Image

from codecheck_mcp.audit.runner import audit

CHECKS = ["seo", "images", "accessibility", "network"]

BAD = """<!doctype html><html><head><meta charset="utf-8">
<style>.nofocus:focus, .nofocus:focus-visible { outline: none; }</style></head><body>
<h1>Main</h1><h1>Second main</h1>
<h2>Section</h2><h4>Skipped level</h4>
<img src="ok.png" width="100" height="50">
<img src="missing.png" width="100" height="50" alt="Broken">
<img src="heavy.png" width="400" height="400" alt="Noise">
<img src="big.png" width="200" height="160" alt="Big">
<div class="clickable" onclick="this.textContent = 'clicked'">Click me</div>
<button class="nofocus">No focus ring</button>
<a href="#top" id="control-link">Link with default focus ring</a>
</body></html>"""

CLEAN = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Clean page for the audit</title>
<meta name="description" content="A page without problems.">
<link rel="canonical" href="https://example.test/clean.html">
<link rel="icon" href="favicon.png">
<meta property="og:title" content="Clean"><meta property="og:description" content="No problems">
<meta property="og:image" content="https://example.test/og.png">
</head><body><main>
<h1>Clean</h1><h2>Part</h2><h3>Sub part</h3>
<img src="ok.png" width="100" height="50" alt="Orange block">
<img src="ok.png" width="100" height="50" alt="">
<p><a href="#part">Jump to part</a></p>
<button type="button" onclick="this.textContent = 'done'">Real button</button>
</main></body></html>"""


def png(path, size, noise=False):
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) if noise else Image.new("RGB", size, (220, 120, 40))
    img.save(path)


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    root = tmp_path_factory.mktemp("sites")
    bad, good = root / "bad", root / "good"
    for d in (bad, good):
        d.mkdir()
        png(d / "ok.png", (100, 50))
    png(bad / "heavy.png", (400, 400), noise=True)   # ~470 КБ
    png(bad / "big.png", (1000, 800))                 # в 5 раз больше показанного
    png(good / "favicon.png", (32, 32))
    (bad / "index.html").write_text(BAD, encoding="utf-8")
    (good / "index.html").write_text(CLEAN, encoding="utf-8")
    (good / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://example.test/sitemap.xml\n")
    (good / "sitemap.xml").write_text('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      "<url><loc>https://example.test/</loc></url></urlset>")
    out = root / "out"
    return (audit(str(bad), viewports=[1280], checks=CHECKS, output_dir=str(out / "bad")),
            audit(str(good), viewports=[1280], checks=CHECKS, output_dir=str(out / "good")))


def by_rule(res):
    out = {}
    for f in res.findings:
        out.setdefault(f.rule, []).append(f)
    return out


def test_runs_without_errors(sites):
    for res in sites:
        assert res.data["errors"] == [], res.data["errors"]


def test_clean_page_has_no_findings(sites):
    _, good = sites
    assert [f.to_dict() for f in good.findings] == []


def test_seo_rules(sites):
    r = by_rule(sites[0])
    for rule in ("seo/missing-description", "seo/multiple-h1", "seo/heading-skip", "seo/missing-canonical",
                 "seo/missing-favicon", "seo/missing-open-graph", "seo/missing-robots", "seo/missing-sitemap"):
        assert rule in r, (rule, sorted(r))
    assert r["seo/multiple-h1"][0].severity == "notice" and r["seo/multiple-h1"][0].evidence["count"] == 2
    assert r["seo/heading-skip"][0].evidence == {"previous": "h2", "previousLevel": 2, "level": 4}
    assert r["seo/missing-robots"][0].page == "/robots.txt"
    assert r["seo/missing-open-graph"][0].evidence["missing"] == ["og:title", "og:description", "og:image"]


def test_axe_and_seo_overlaps_are_deduplicated(sites):
    r = by_rule(sites[0])
    # title и lang находят и SEO, и axe: остаётся одна запись на каждую проблему
    assert len(r.get("seo/missing-title", []) + r.get("accessibility/document-title", [])) == 1, sorted(r)
    assert len(r.get("seo/missing-lang", []) + r.get("accessibility/html-has-lang", [])) == 1, sorted(r)
    # alt: axe (critical) и images (warning) по одному селектору — одна запись, более серьёзная
    alt = r.get("images/missing-alt", []) + r.get("accessibility/image-alt", [])
    assert len(alt) == 1 and alt[0].selector.startswith("img"), [f.to_dict() for f in alt]
    assert alt[0].severity == "critical"


def test_broken_image_reported_once_with_selector(sites):
    r = by_rule(sites[0])
    broken = r.get("network/image-failed", []) + r.get("images/broken", [])
    assert len(broken) == 1, [f.to_dict() for f in broken]
    assert broken[0].url.endswith("/missing.png") and broken[0].selector, broken[0].to_dict()


def test_image_size_rules(sites):
    r = by_rule(sites[0])
    heavy = r["images/heavy"]
    assert len(heavy) == 1 and heavy[0].url.endswith("/heavy.png") and heavy[0].severity == "notice"
    assert heavy[0].evidence["bytes"] > 200 * 1024
    over = r["images/oversized"]
    assert len(over) == 1 and over[0].url.endswith("/big.png")
    assert over[0].evidence["natural"] == [1000, 800] and over[0].evidence["displayed"] == [200, 160]


def test_keyboard_rules(sites):
    r = by_rule(sites[0])
    onclick = r["accessibility/onclick-not-focusable"]
    assert [f.selector for f in onclick] == [".clickable"] and onclick[0].severity == "warning"
    focus = r["accessibility/focus-not-visible"]
    # у кнопки без outline фокуса не видно, у ссылки с обычным фокусом — видно
    assert [f.selector for f in focus] == [".nofocus"], [f.to_dict() for f in focus]


def test_axe_findings_have_evidence_and_recommendation(sites):
    bad = sites[0]
    axe = [f for f in bad.findings if f.rule.startswith("accessibility/") and "axeRule" in (f.evidence or {})]
    assert axe, "axe не нашёл ничего на заведомо плохой странице"
    for f in axe:
        assert f.evidence["helpUrl"].startswith("https://dequeuniversity.com/")
    md = (bad.out_dir / "report.md").read_text(encoding="utf-8")
    assert "No recommendation is defined" not in md
