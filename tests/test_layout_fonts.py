from browser import run
from checks.fonts import check_fonts
from checks.layout import check_layout

from conftest import fixture_path


def msgs(rep, check):
    return [f.message for f in rep.findings if f.check == check]


def test_clean_page_has_no_layout_or_font_findings():
    rep = run(fixture_path("clean.html"), [check_layout, check_fonts], max_pages=1)
    assert rep.pages, "страница не открылась"
    bad = [f for f in rep.findings if f.check in ("layout", "fonts")]
    assert bad == [], [f.message for f in bad]


def test_edge_cases_are_not_false_positives():
    """Регрессия с реального сайта: касание строк, 44px, декоративные символы, шрифт для заголовков, фон-градиент."""
    rep = run(fixture_path("edge_ok.html"), [check_layout, check_fonts], max_pages=1, viewports=[(375, 800)])
    bad = [f.message for f in rep.findings if f.check in ("layout", "fonts")]
    assert bad == [], bad


def test_layout_bugs_are_found():
    rep = run(fixture_path("layout_bad.html"), [check_layout], max_pages=1, viewports=[(375, 800)])
    m = msgs(rep, "layout")
    assert any("накладывается" in x for x in m), m
    assert any("Горизонтальный скролл" in x for x in m), m
    assert any("обрезан" in x for x in m), m
    assert any("контраст" in x for x in m), m
    # у находок должны быть скриншоты
    assert any(f.screenshot for f in rep.findings if f.check == "layout")


def test_font_bugs_are_found():
    rep = run(fixture_path("fonts_bad.html"), [check_fonts], max_pages=1)
    m = msgs(rep, "fonts")
    assert any("разных шрифтов" in x for x in m), m
    assert any("иерархия" in x.lower() for x in m), m
    assert any("NoSuchFontXYZ".lower() in x.lower() for x in m), m
