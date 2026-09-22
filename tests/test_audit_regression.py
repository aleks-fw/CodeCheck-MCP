"""Фаза 6: сравнение прогонов (Fixed / New / Unchanged) и инструмент compare_reports."""
import asyncio
import json

from fastmcp import Client

from codecheck_mcp.audit.core.finding import Finding
from codecheck_mcp.audit.report import diff
from codecheck_mcp.audit.runner import audit
from codecheck_mcp.server import mcp


def f(rule, page="/", category="seo", **kw):
    return Finding(severity="warning", category=category, rule=rule, page=page, message=rule, details=rule, **kw)


def test_compare_splits_fixed_new_unchanged_and_not_rechecked():
    prev = {"date": "d1", "url": "u", "pages": ["/", "/other"], "viewports": ["375x812", "1280x800"],
            "checks": ["seo", "images", "layout", "interaction", "fonts"]}
    cur = {"date": "d2", "url": "u", "pages": ["/"], "viewports": ["1280x800"],
           "checks": ["seo", "images", "layout", "interaction"]}
    title = f("seo/missing-title", selector="html")
    alt = f("images/missing-alt", category="images", selector="img")
    overflow = f("layout/horizontal-overflow", category="layout", selector=".wide", viewport="375x812")
    dead = f("interaction/no-effect", page="/other", category="interaction", selector="#buy")
    font = f("fonts/load-failed", category="fonts", selector="h1")
    robots = f("seo/missing-robots", page="/robots.txt", url="http://x/robots.txt")
    new = f("seo/missing-h1")
    d = diff.compare(prev, [title, alt, overflow, dead, font, robots], cur, [title, new])
    assert [x.rule for x in d.unchanged] == ["seo/missing-title"]
    assert [x.rule for x in d.new] == ["seo/missing-h1"]
    # alt и robots.txt перепроверены и не найдены — исправлены
    assert sorted(x.rule for x in d.fixed) == ["images/missing-alt", "seo/missing-robots"]
    # остальные этот прогон не проверял: другая ширина, страница вне обхода, категория не выбрана
    assert sorted(x.rule for x in d.not_rechecked) == ["fonts/load-failed", "interaction/no-effect",
                                                        "layout/horizontal-overflow"]
    md = "\n".join(diff.render(d, "u"))
    assert "✅ Fixed: 2 · 🔴 New: 1 · ⚠️ Unchanged: 1" in md and "### Not rechecked" in md


PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">{title}</head><body><h1>Shop</h1>'
        '<img src="a.png" width="10" height="10"></body></html>')


def test_second_run_shows_fixed_error(tmp_path):
    site, out = tmp_path / "site", tmp_path / "out"
    site.mkdir()
    (site / "a.png").write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360f80f0000010101001853a4c10000000049454e44ae426082"))
    (site / "index.html").write_text(PAGE.format(title=""), encoding="utf-8")
    kw = dict(viewports=[1280], checks=["seo", "images"], output_dir=str(out))

    first = audit(str(site), **kw)
    assert first.diff is None and "No previous run to compare with." in first.summary_text()
    assert not (out / "previous.json").exists()
    title_fp = next(x.fingerprint for x in first.findings if x.rule == "seo/missing-title")

    (site / "index.html").write_text(PAGE.format(title="<title>Shop</title>"), encoding="utf-8")  # исправили одно
    second = audit(str(site), **kw)
    assert (out / "previous.json").exists()
    assert [x.fingerprint for x in second.diff.fixed] == [title_fp]
    assert second.diff.new == []
    assert "images/missing-alt" in [x.rule for x in second.diff.unchanged]
    data = json.loads((out / "current.json").read_text(encoding="utf-8"))
    assert data["comparison"]["fixed"] == [title_fp]
    md = (out / "report.md").read_text(encoding="utf-8")
    assert md.index("## Changes since the previous run") < md.index("## Summary")
    assert "✅ Fixed: 1 · 🔴 New: 0" in md and "`seo/missing-title`" in md.split("## Summary")[0]
    assert "✅ Fixed 1 · 🔴 New 0" in second.summary_text()


def call(name, args):
    async def go():
        async with Client(mcp) as c:
            return (await c.call_tool(name, args)).content[0].text
    return asyncio.run(go())


def test_compare_reports_tool(tmp_path):
    prev = {"date": "d1", "url": "u", "pages": ["/"], "viewports": [], "checks": ["seo"],
            "findings": [f("seo/missing-title", selector="html").to_dict()]}
    cur = {"date": "d2", "url": "u", "pages": ["/"], "viewports": [], "checks": ["seo"],
           "findings": [f("seo/missing-h1").to_dict()]}
    (tmp_path / "a.json").write_text(json.dumps(prev), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(cur), encoding="utf-8")
    text = call("compare_reports", {"previous": str(tmp_path / "a.json"), "current": str(tmp_path / "b.json")})
    assert "✅ Fixed: 1 · 🔴 New: 1 · ⚠️ Unchanged: 0" in text, text
    assert call("compare_reports", {"previous": str(tmp_path / "nope.json"),
                                    "current": str(tmp_path / "b.json")}).startswith("Error: file not found")
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    assert call("compare_reports", {"previous": str(tmp_path / "bad.json"),
                                    "current": str(tmp_path / "b.json")}).startswith("Error: not an audit_project")
