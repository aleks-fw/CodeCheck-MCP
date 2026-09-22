"""Фаза 2: проверки console и network на страницах с намеренными ошибками."""
import functools
import http.server
import json
import threading
import time

import pytest
from conftest import FIXTURES

from codecheck_mcp.audit.runner import audit

SITE = FIXTURES / "audit_net"
API = {"/api/ok": (200, 0), "/api/fail": (500, 0), "/api/missing": (404, 0), "/api/unauthorized": (401, 0),
       "/api/slow": (200, 1.3), "/api/very-slow": (200, 3.3)}


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in API:
            status, delay = API[self.path]
            time.sleep(delay)
            body = json.dumps({"ok": status == 200}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site_report(tmp_path_factory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(SITE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = tmp_path_factory.mktemp("netaudit")
        res = audit(f"http://127.0.0.1:{srv.server_address[1]}/index.html", max_pages=20, viewports=[1280],
                    checks=["console", "network"], output_dir=str(out))
    finally:
        srv.shutdown()
    return res


def on(res, page):
    return [f for f in res.findings if f.page == page]


def test_all_pages_crawled(site_report):
    assert len(site_report.data["pages"]) == 10, site_report.data["pages"]
    assert site_report.data["errors"] == []


def test_clean_page_and_index_have_no_findings(site_report):
    assert on(site_report, "/clean.html") == [], [f.to_dict() for f in on(site_report, "/clean.html")]
    assert on(site_report, "/") == [] and on(site_report, "/index.html") == []


def test_console_error_deduplicated_with_count(site_report):
    f = on(site_report, "/console.html")
    assert [x.rule for x in f] == ["console/error"], [x.to_dict() for x in f]
    assert f[0].severity == "warning" and f[0].evidence["count"] == 3
    assert f[0].evidence["text"] == "Cart total is NaN" and "/console.html:" in f[0].evidence["source"]


def test_uncaught_exception_is_critical_with_stack(site_report):
    f = on(site_report, "/throw.html")
    assert [x.rule for x in f] == ["console/uncaught-exception"], [x.to_dict() for x in f]
    assert f[0].severity == "critical" and "undefinedFunctionCall" in f[0].message
    assert "at init" in f[0].evidence["stack"] and "/throw.html:" in f[0].evidence["source"]


def test_unhandled_rejection_is_warning_not_duplicated_as_exception(site_report):
    f = on(site_report, "/reject.html")
    assert [x.rule for x in f] == ["console/unhandled-rejection"], [x.to_dict() for x in f]
    assert f[0].severity == "warning" and f[0].evidence["text"] == "profile request failed"


def test_api_errors(site_report):
    f500 = on(site_report, "/api500.html")
    assert [(x.rule, x.severity) for x in f500] == [("network/api-5xx", "critical")], [x.to_dict() for x in f500]
    assert f500[0].url.endswith("/api/fail")
    assert {"method": "GET", "status": 500, "resourceType": "fetch"}.items() <= f500[0].evidence.items()
    assert f500[0].evidence["durationMs"] >= 0
    assert [(x.rule, x.severity) for x in on(site_report, "/api404.html")] == [("network/api-4xx", "warning")]
    # 401 на странице логина — не ошибка
    assert on(site_report, "/login.html") == []


def test_broken_assets(site_report):
    got = {(x.rule, x.severity, x.url.rsplit("/", 1)[-1]) for x in on(site_report, "/broken.html")}
    assert got == {("network/stylesheet-failed", "critical", "missing.css"),
                   ("network/script-failed", "critical", "missing.js"),
                   ("network/image-failed", "warning", "missing.png")}, got


def test_slow_requests(site_report):
    got = {x.url.rsplit("/", 1)[-1]: x for x in on(site_report, "/slow.html")}
    assert set(got) == {"slow", "very-slow"}, [x.to_dict() for x in on(site_report, "/slow.html")]
    assert got["slow"].rule == "network/slow-request" and got["slow"].severity == "notice"
    assert got["slow"].evidence["durationMs"] >= 1300
    assert got["very-slow"].severity == "warning" and got["very-slow"].evidence["durationMs"] >= 3300


def test_screenshots_for_critical_and_warning_only(site_report):
    for f in site_report.findings:
        assert bool(f.screenshot) == (f.severity != "notice"), f.to_dict()
