"""Группировка и приоритизация находок (Prioritized Issues)."""
from codecheck_mcp.audit.core.finding import Finding
from codecheck_mcp.audit.report import priority

N = iter(range(1, 1000))


def f(rule, page, severity="warning", category=None, **kw):
    x = Finding(severity=severity, category=category or rule.split("/")[0], rule=rule, page=page,
                message=kw.pop("message", rule), details=kw.pop("details", f"{rule} on {page}."), **kw)
    x.id = f"CC-{next(N):03d}"
    return x


def by_root(groups):
    return {g.root.rule: g for g in groups}


def test_task_example_checkout_api():
    """POST /api/order отвечает 500: кнопки на двух страницах и ошибка в консоли — одна группа CRITICAL."""
    order = "http://shop.test/api/order"
    click1 = f("interaction/action-request-failed", "/checkout", "critical", url=order, selector="#place-order",
               message="Clicking #place-order sends POST /api/order, which answers HTTP 500",
               details="Clicking #place-order on /checkout sent POST http://shop.test/api/order, which answered "
                       "HTTP 500.", evidence={"requests": [{"method": "POST", "url": order, "status": 500}],
                                              "critical": True})
    click2 = f("interaction/action-request-failed", "/cart", "critical", url=order, selector="#place-order",
               evidence={"requests": [{"method": "POST", "url": order, "status": 500}], "critical": True})
    rejection = f("console/unhandled-rejection", "/checkout", message="Unhandled promise rejection: order failed",
                  evidence={"text": "Order request failed: HTTP 500"})
    other_page_error = f("console/error", "/about", evidence={"text": "Analytics blocked"})
    canonical = [f("seo/missing-canonical", p, "notice", message="No canonical link") for p in ("/", "/cart", "/about")]

    groups = priority.build([click1, click2, rejection, other_page_error, *canonical], total_pages=4)
    g = groups[0]
    assert g.severity == "CRITICAL" and g.category == "functionality"
    assert g.root is click1 and g.pages == ["/cart", "/checkout"]
    assert "POST http://shop.test/api/order, which answered HTTP 500" in g.root_cause()
    assert [(x.id, ok) for x, ok, _ in g.related] == [(rejection.id, False)]  # связь выведена, не доказана
    assert not g.confirmed                                                     # значит, Likely root cause
    assert g.impact == 10 and g.impact_basis["key action (criticalSelectors)"] == 1
    assert g.evidence()["requests"] == ["POST http://shop.test/api/order → 500"]
    # ошибка консоли на другой странице — отдельная группа, canonical на трёх страницах — одна группа
    roots = by_root(groups)
    assert roots["console/error"].related == [] and roots["console/error"].pages == ["/about"]
    seo = roots["seo/missing-canonical"]
    assert seo.severity == "LOW" and seo.pages == ["/", "/about", "/cart"] and seo.related == []

    md = "\n".join(priority.render(groups, {"interaction/action-request-failed": "Fix the endpoint."}))
    assert "## Prioritized Issues" in md
    assert "### 🔴 CRITICAL — Clicking #place-order sends POST /api/order, which answers HTTP 500" in md
    assert "- **Impact:** 10/10" in md and "- **Affected pages:** `/cart`, `/checkout`" in md
    assert "- **Likely root cause:**" in md and "(likely: same page as the failing request /api/order" in md
    assert "- **Recommendation:** Fix the endpoint." in md
    assert "Same problem also on:** `/cart`" in md


def test_confirmed_link_when_error_names_the_url():
    api = f("network/api-5xx", "/", "critical", url="http://x.test/api/orders", message="API request returned HTTP 500")
    err = f("console/error", "/", evidence={"text": "GET /api/orders failed with 500"})
    click = f("interaction/action-request-failed", "/", "critical", url="http://x.test/api/orders", selector="#reload")
    (g,) = priority.build([api, err, click], total_pages=1)
    assert g.root is api and g.confirmed
    assert {x.rule: ok for x, ok, _ in g.related} == {"console/error": True, "interaction/action-request-failed": True}
    assert "- **Root cause:**" in "\n".join(priority.render([g], {}))
    assert g.title == "API request returned HTTP 500 (/api/orders)"


def test_missing_script_explains_errors_and_dead_buttons_as_likely():
    js = f("network/script-failed", "/", "critical", url="http://x.test/js/app.js")
    ref = f("console/uncaught-exception", "/", "critical", evidence={"text": "ReferenceError: initCart is not defined"})
    dead = f("interaction/no-effect", "/", "warning", selector="#buy")
    elsewhere = f("interaction/no-effect", "/other", "warning", selector="#x")
    groups = priority.build([js, ref, dead, elsewhere], total_pages=2)
    g = by_root(groups)["network/script-failed"]
    assert sorted(x.rule for x, _, _ in g.related) == ["console/uncaught-exception", "interaction/no-effect"]
    assert not g.confirmed and g.impact_basis["causes other issues"] == 1
    assert by_root(groups)["interaction/no-effect"].pages == ["/other"]  # мёртвая кнопка на другой странице отдельно


def test_heavy_file_in_page_weight_is_confirmed():
    weight = f("performance/page-weight", "/", evidence={"largest": [{"url": "http://x.test/hero.png", "bytes": 3e6}]})
    heavy = f("images/heavy", "/", "notice", url="http://x.test/hero.png")
    (g,) = priority.build([weight, heavy], total_pages=1)
    assert g.root is weight and g.confirmed and g.category == "performance" and g.severity == "MEDIUM"


def test_order_and_levels():
    crit = f("console/uncaught-exception", "/", "critical")
    sec = f("security/cookie-not-httponly", "/", "warning", message="cookie")
    look = f("layout/horizontal-overflow", "/", "warning", selector=".wide")
    wide = [f("layout/clipped-text", p, "warning", selector=".title") for p in ("/", "/a", "/b")]
    note = f("seo/missing-canonical", "/", "notice")
    groups = priority.build([note, look, sec, crit, *wide], total_pages=3)
    assert [(g.severity, g.root.rule) for g in groups] == [
        ("CRITICAL", "console/uncaught-exception"), ("HIGH", "security/cookie-not-httponly"),
        ("MEDIUM", "layout/clipped-text"), ("MEDIUM", "layout/horizontal-overflow"), ("LOW", "seo/missing-canonical")]
    assert [g.id for g in groups] == ["G-01", "G-02", "G-03", "G-04", "G-05"]
    clipped = groups[2]
    assert clipped.impact == 7 and clipped.impact_basis == {"severity": 5, "on most pages": 2}  # 3 из 3 страниц


def test_json_shape():
    g = priority.build([f("network/api-4xx", "/", url="http://x.test/api/a")], total_pages=1)
    (d,) = priority.to_json(g, {"network/api-4xx": "Fix it."})
    assert list(d) == ["id", "title", "severity", "category", "impact", "impactBasis", "affectedPages", "rootCause",
                       "relatedIssues", "recommendation", "evidence", "findings"]
    assert d["rootCause"]["confirmed"] is True and d["recommendation"] == "Fix it." and d["severity"] == "HIGH"


def test_multiline_details_stay_on_one_line():
    axe = f("accessibility/image-alt", "/", "critical", selector="img", details="Ensure images have alt\n  Fix:\n  add alt")
    md = "\n".join(priority.render(priority.build([axe], total_pages=1), {}))
    assert "- **Root cause:** Ensure images have alt Fix: add alt (" in md


def test_evidence_requests_can_be_a_count():
    many = f("performance/too-many-requests", "/", "notice", evidence={"requests": 101})
    (g,) = priority.build([many], total_pages=1)
    assert g.evidence()["requests"] == []
