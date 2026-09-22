"""Демо-магазин из examples/: находки должны совпадать с таблицей в examples/demo-shop/README.md."""
import functools
import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

from codecheck_mcp.audit.runner import audit

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-shop"

EXPECTED = {
    "/errors.html": {"console/error", "console/uncaught-exception", "console/unhandled-rejection"},
    "/media.html": {"accessibility/image-alt", "network/image-failed", "network/script-failed"},
    "/api.html": {"network/api-5xx"},
    "/mobile.html": {"layout/horizontal-overflow"},
    "/buttons.html": {"interaction/no-effect"},
    "/notitle.html": {"seo/missing-title"},
    "/checkout.html": {"network/api-5xx", "console/error", "interaction/action-request-failed"},
    "/cart.html": {"interaction/action-request-failed"},
}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("demo_serve", DEMO / "serve.py")
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(serve.Handler, directory=str(serve.SITE)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        return audit(f"http://127.0.0.1:{srv.server_address[1]}/", critical_selectors=["#checkout", "#place-order"],
                     output_dir=str(tmp_path_factory.mktemp("demo")))
    finally:
        srv.shutdown()


def serious(res, page):
    return {f.rule for f in res.findings if f.page == page and f.severity != "notice"}


def test_demo_findings_match_the_readme(result):
    assert result.data["errors"] == []
    assert serious(result, "/") == set()
    for page, rules in EXPECTED.items():
        assert serious(result, page) == rules, (page, serious(result, page))


def test_demo_details(result):
    dead = [f for f in result.findings if f.rule == "interaction/no-effect"]
    assert [(f.selector, f.severity) for f in dead] == [("#checkout", "critical")]  # «Add to cart» работает
    overflow = next(f for f in result.findings if f.rule == "layout/horizontal-overflow")
    assert overflow.viewport == "375x812" and "viewports" not in (overflow.evidence or {})
    for f in result.findings:
        if f.severity != "notice":
            assert f.screenshot and (result.out_dir / f.screenshot).exists(), f.to_dict()


def test_demo_top_group_is_the_order_api(result):
    g = result.groups[0]
    assert g.severity == "CRITICAL" and g.impact == 10 and g.confirmed
    assert g.root.rule == "network/api-5xx" and g.root.url.endswith("/api/order")
    assert g.pages == ["/cart.html", "/checkout.html"]
    assert sorted(x.rule for x, _, _ in g.related) == ["console/error", "interaction/action-request-failed",
                                                       "interaction/action-request-failed"]
