"""Фаза 5: клики (мёртвые, рабочие, деструктивные, критичные) и пассивная безопасность."""
import functools
import http.server
import threading

import pytest

from codecheck_mcp.audit.runner import audit

HEAD = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{0}</title></head><body><h1>{0}</h1>'

CLICKS = HEAD.format("Clicks") + """
<button id="dead">Dead button</button>
<button id="toggle" onclick="document.getElementById('out').textContent = 'changed'">Toggle</button>
<button id="fetcher" onclick="fetch('/api/ok')">Load data</button>
<button id="nav" onclick="location.href = 'other.html'">Go</button>
<a href="#" id="dead-link">Dead link</a>
<a href="javascript:void(0)" id="js-link">JS link</a>
<div role="button" id="alerter" tabindex="0" onclick="alert('hi')">Alert</div>
<button id="del">Удалить аккаунт</button>
<button id="off" disabled>Disabled</button>
<button class="checkout">Checkout</button>
<form action="other.html"><input required name="q" aria-label="Query"><button id="send">Send</button></form>
<button id="opener" onclick="window.open('other.html')">Open</button>
<div style="position: relative; height: 60px">
  <button id="covered">Covered</button>
  <div style="position: absolute; inset: 0; background: #eee">Overlay</div>
</div>
<p id="out"></p>
</body></html>"""

CLEAN = HEAD.format("Clean") + """<p id="out"></p>
<button id="ok" onclick="document.getElementById('out').textContent = 'ok'">Works</button>
<script src="app.js"></script></body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.endswith(".html") or self.path == "/":
            for c in ("sessionid=abc123; Path=/", "theme=dark; Path=/", "csrftoken=t0k; Path=/"):
                self.send_header("Set-Cookie", c)
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/ok":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        super().do_GET()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("clicks")
    (d / "index.html").write_text(HEAD.format("Index") + '<a href="clicks.html">clicks</a> '
                                  '<a href="clean.html">clean</a></body></html>', encoding="utf-8")
    (d / "clicks.html").write_text(CLICKS, encoding="utf-8")
    (d / "clean.html").write_text(CLEAN, encoding="utf-8")
    (d / "other.html").write_text(HEAD.format("Other") + "</body></html>", encoding="utf-8")
    (d / "app.js").write_text("var a = 1;\n//# sourceMappingURL=app.js.map\n")
    (d / "app.js.map").write_text('{"version":3,"sources":["app.ts"],"mappings":"AAAA"}')
    return d


@pytest.fixture(scope="module")
def served(site, tmp_path_factory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(site)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        return audit(f"http://127.0.0.1:{srv.server_address[1]}/index.html", max_pages=3, viewports=[1280],
                     checks=["interaction", "security"], critical_selectors=[".checkout", "not a [valid selector"],
                     output_dir=str(tmp_path_factory.mktemp("out")))
    finally:
        srv.shutdown()


def on(res, page, prefix):
    return {f.selector or f.url: f for f in res.findings if f.page == page and f.rule.startswith(prefix)}


def test_run_ok(served):
    assert served.data["errors"] == [], served.data["errors"]
    assert served.data["pages"] == ["/index.html", "/clicks.html", "/clean.html"]


def test_dead_controls_found_and_working_ones_not(served):
    f = on(served, "/clicks.html", "interaction/")
    assert set(f) == {"#dead", "#dead-link", "#js-link", ".checkout", "#covered"}, sorted(f)
    dead = f["#dead"]
    assert dead.rule == "interaction/no-effect" and dead.severity == "warning"
    assert dead.details == ("Clicking #dead on /clicks.html produced no navigation, URL change, network request "
                            "or visible DOM change within 2 seconds.")
    assert f["#dead-link"].rule == "interaction/no-effect"   # href="#" добавляет # к адресу, но это не реакция
    assert f["#covered"].rule == "interaction/not-clickable" and "intercepts pointer events" in f["#covered"].details


def test_critical_selector_is_critical_with_state_note(served):
    c = on(served, "/clicks.html", "interaction/")[".checkout"]
    assert c.severity == "critical" and c.evidence["critical"] is True
    assert "may depend on app state" in c.details
    assert "`interaction/no-effect` on /clicks.html: Clicking .checkout does nothing" in served.summary_text()


def test_clean_page_has_no_interaction_findings(served):
    assert on(served, "/clean.html", "interaction/") == {}


def test_security_headers_cookies_and_source_maps(served):
    rules = sorted(f.rule for f in served.findings if f.category == "security")
    assert rules == ["security/cookie-not-httponly", "security/missing-csp", "security/missing-nosniff",
                     "security/source-map-exposed"], rules
    cookie = next(f for f in served.findings if f.rule == "security/cookie-not-httponly")
    assert cookie.evidence["cookie"] == "sessionid"          # theme и csrftoken не сессионные
    smap = next(f for f in served.findings if f.rule == "security/source-map-exposed")
    assert smap.url.endswith("/app.js.map") and smap.severity == "notice"
    # localhost не требует HTTPS
    assert not any(f.rule == "security/no-https" for f in served.findings)


def test_local_folder_skips_server_headers(site, tmp_path):
    res = audit(str(site / "clean.html"), max_pages=1, viewports=[1280], checks=["security"], output_dir=str(tmp_path))
    assert [f.rule for f in res.findings] == ["security/source-map-exposed"], [f.to_dict() for f in res.findings]
