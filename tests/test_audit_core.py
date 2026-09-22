"""Фаза 1: модель Finding, fingerprint, report.md, селекторы и каркас audit_project."""
import json
from types import SimpleNamespace

import pytest
from conftest import fixture_path
from playwright.sync_api import sync_playwright

from codecheck_mcp.audit.core.finding import Finding
from codecheck_mcp.audit.core.fingerprint import fingerprint
from codecheck_mcp.audit.core.selector import SELECTOR_JS
from codecheck_mcp.audit.report import json_report, markdown
from codecheck_mcp.audit.runner import audit


def make(**kw):
    base = dict(severity="warning", category="seo", rule="seo/missing-title", page="/", message="No title",
                details="The page has no <title> element.")
    return Finding(**{**base, **kw})


# ---------- Finding ----------

def test_finding_serialization_roundtrip():
    f = make(selector="head", evidence={"count": 0}, viewport="375x812")
    f.id = "CC-001"
    d = json.loads(json.dumps(f.to_dict()))
    assert list(d) == ["id", "fingerprint", "severity", "category", "rule", "page", "message", "details",
                       "selector", "viewport", "evidence"]  # пустые необязательные поля не пишутся
    assert Finding.from_dict(d) == f


def test_finding_rejects_unknown_severity_and_category():
    with pytest.raises(ValueError):
        make(severity="high")
    with pytest.raises(ValueError):
        make(category="internal")


# ---------- fingerprint ----------

def test_fingerprint_is_stable_and_ignores_order_time_and_id():
    a = make(selector="#buy", viewport="375x812", message="first wording")
    b = make(selector="#buy", viewport="1280x800", message="second wording", evidence={"t": 1})
    b.id = "CC-099"
    assert a.fingerprint == b.fingerprint == fingerprint("seo/missing-title", "/", "#buy")
    assert len(a.fingerprint) == 16


def test_fingerprint_depends_on_rule_page_and_target():
    base = make(selector="#buy").fingerprint
    assert make(selector="#sell").fingerprint != base
    assert make(selector="#buy", page="/cart").fingerprint != base
    assert make(selector="#buy", rule="seo/missing-h1").fingerprint != base
    # без селектора берётся url
    assert make(url="https://x.test/a.js").fingerprint == fingerprint("seo/missing-title", "/", "https://x.test/a.js")


def test_fingerprint_ignores_random_localhost_port():
    a = make(url="http://127.0.0.1:61598/api/fail").fingerprint
    assert a == make(url="http://127.0.0.1:50011/api/fail").fingerprint == make(url="http://localhost/api/fail").fingerprint
    assert a != make(url="https://shop.example/api/fail").fingerprint


# ---------- report.md ----------

def test_markdown_report_on_fake_data():
    findings = [
        make(severity="critical", category="console", rule="console/uncaught-exception", page="/checkout",
             message="Uncaught TypeError", details="x is undefined", evidence={"stack": "app.js:3"}),
        make(severity="warning", category="seo", rule="seo/missing-title", selector="head"),
        make(severity="warning", category="network", rule="network/api-4xx", url="https://x.test/api", page="/"),
        make(severity="notice", category="seo", rule="seo/missing-canonical", message="No canonical"),
    ]
    for n, f in enumerate(findings, 1):
        f.id = f"CC-{n:03d}"
    findings[0].screenshot = "screenshots/CC-001.png"
    meta = {"tool": "codecheck-mcp", "version": "0.1.0", "project": "shop", "url": "https://x.test",
            "date": "2026-09-22T10:00:00+00:00", "pages": ["/", "/checkout"], "viewports": ["375x812"],
            "checks": [], "errors": [{"check": "seo", "page": "/", "viewport": "375x812", "error": "boom"}]}
    data = json_report.build(meta, findings)
    assert data["summary"] == {"critical": 1, "warning": 2, "notice": 1}
    md = markdown.render(data, findings, {"seo/missing-title": "Add a unique <title>."})

    for line in ("- **Project:** shop", "- **URL:** https://x.test", "- **Date:** 2026-09-22T10:00:00+00:00",
                 "- **Pages tested:** 2", "| 🔴 Critical | 1 |", "| 🟠 Warnings | 2 |", "| 🟡 Notices | 1 |"):
        assert line in md, line
    # разделы по порядку, внутри — группы по категориям
    i_crit, i_warn, i_note = md.index("## 🔴 Critical (1)"), md.index("## 🟠 Warnings (2)"), md.index("## 🟡 Notices (1)")
    assert i_crit < i_warn < i_note < md.index("## Pages tested") < md.index("## Recommendations")
    warn = md[i_warn:i_note]
    assert warn.index("### seo") < warn.index("### network")  # порядок категорий из CATEGORIES
    assert "![CC-001](screenshots/CC-001.png)" in md
    assert "`console/uncaught-exception`" in md and "app.js:3" in md
    assert "## Run errors" in md and "boom" in md
    # по одной рекомендации на каждое встреченное правило, без выдумывания
    rec = md[md.index("## Recommendations"):].splitlines()
    rec_lines = [x for x in rec if x.startswith("- `")]
    assert len(rec_lines) == 4
    assert "- `seo/missing-title`: Add a unique <title>." in rec
    assert f"- `seo/missing-canonical`: {markdown.NO_RECOMMENDATION}" in rec


def test_markdown_empty_sections_say_none():
    data = json_report.build({"project": "p", "url": "u", "date": "d", "pages": ["/"], "viewports": ["375x812"],
                              "version": "0", "errors": []}, [])
    md = markdown.render(data, [], {})
    assert md.count("None.") == 3 and "Nothing to fix." in md


# ---------- селекторы ----------

SELECTOR_PAGE = """<!doctype html><html><body>
<button id="buy">Buy</button>
<button data-testid="pay">Pay</button>
<input name="email"><button aria-label="Close">x</button>
<div class="card"><p class="price">1</p></div><div class="card"><p class="price">2</p></div>
<ul><li>a</li><li><span>b</span></li></ul>
</body></html>"""


def test_selectors_are_short_unique_and_follow_preference():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        page.set_content(SELECTOR_PAGE)
        page.evaluate(SELECTOR_JS)
        sel = page.evaluate("""() => ['#buy', '[data-testid=pay]', 'input', '[aria-label=Close]',
            '.card:nth-of-type(2) .price', 'li:nth-of-type(2) span']
            .map(q => __ccSelector(document.querySelector(q)))""")
        unique = page.evaluate("(ss) => ss.map(s => document.querySelectorAll(s).length)", sel)
        b.close()
    assert sel[:4] == ["#buy", '[data-testid="pay"]', '[name="email"]', '[aria-label="Close"]'], sel
    assert unique == [1] * len(sel), (sel, unique)
    assert sel[4] == "div.card:nth-of-type(2) > p.price", sel
    assert sel[5] == "span", sel  # единственный span на странице: самый короткий уникальный селектор


# ---------- каркас audit_project ----------

def _fake_check(per_viewport=True, fail=False):
    def run(page, ctx):
        if fail:
            raise RuntimeError("check exploded")
        return [
            Finding(severity="warning", category="layout", rule="layout/fake", page=ctx.path, selector="h1",
                    viewport=ctx.viewport, message="Fake warning", details="Test finding."),
            Finding(severity="notice", category="layout", rule="layout/fake-notice", page=ctx.path,
                    message="Fake notice", details="Test notice."),
        ]
    return SimpleNamespace(CATEGORY="layout", PER_VIEWPORT=per_viewport, RECOMMENDATIONS={"layout/fake": "Fix it."},
                           run=run)


def test_audit_skeleton_writes_json_markdown_and_screenshots(tmp_path):
    out = tmp_path / "out"
    res = audit(fixture_path("clean.html"), viewports=[375, 1280], output_dir=str(out),
                registry=[_fake_check(), SimpleNamespace(**{**vars(_fake_check(fail=True)), "CATEGORY": "seo"})])
    data = json.loads((out / "current.json").read_text(encoding="utf-8"))
    assert data["pages"] == ["/clean.html"]
    assert data["viewports"] == ["375x812", "1280x800"]
    assert data["summary"] == {"critical": 0, "warning": 1, "notice": 1}
    ids = [f["id"] for f in data["findings"]]
    assert ids == ["CC-001", "CC-002"]
    warn = data["findings"][0]
    # одна запись на два viewport, скриншот только у warning
    assert warn["evidence"]["viewports"] == ["1280x800", "375x812"]
    assert warn["screenshot"] == "screenshots/CC-001.png" and (out / "screenshots" / "CC-001.png").exists()
    assert "screenshot" not in data["findings"][1]
    assert not (out / "screenshots" / "CC-002.png").exists()
    # упавшая проверка не роняет прогон и видна в отчёте
    assert data["errors"] and data["errors"][0]["check"] == "seo" and "check exploded" in data["errors"][0]["error"]
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "- `layout/fake`: Fix it." in md and "## Run errors" in md
    text = res.summary_text()
    assert "Critical: 0 · Warnings: 1 · Notices: 1" in text and str(out / "report.md") in text, text
    assert "Run errors: 2" in text, text  # упавшая проверка запускалась на двух viewport


def test_audit_reports_missing_start_page(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "a.html").write_text("<a href='missing.html'>x</a>", encoding="utf-8")
    res = audit(str(tmp_path / "site" / "a.html"), viewports=[1280], output_dir=str(tmp_path / "out"), registry=[])
    f = [x for x in res.findings if x.rule == "network/page-unavailable"]
    assert len(f) == 1 and f[0].page == "/missing.html" and f[0].severity == "warning"
    assert f[0].evidence == {"status": 404}
    assert res.data["pages"] == ["/a.html"]


def test_audit_rejects_unknown_category(tmp_path):
    with pytest.raises(ValueError, match="Unknown check categories: bogus"):
        audit(fixture_path("clean.html"), checks=["bogus"], output_dir=str(tmp_path))
