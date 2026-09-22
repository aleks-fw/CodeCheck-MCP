"""Security (только пассивные проверки): HTTPS, mixed content, заголовки, флаги cookies, доступные source maps."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ..core.finding import Finding

CATEGORY = "security"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "security/no-https": "Serve the site over HTTPS (a free certificate from Let's Encrypt or your host) and "
                         "redirect HTTP to HTTPS.",
    "security/mixed-content": "Load this resource over https:// (or a relative URL); browsers block or warn about "
                              "HTTP resources on HTTPS pages.",
    "security/missing-csp": "Add a Content-Security-Policy header, starting with default-src 'self' and allowing "
                            "only the domains the site really uses.",
    "security/missing-nosniff": "Add the header X-Content-Type-Options: nosniff.",
    "security/missing-hsts": "Add Strict-Transport-Security: max-age=31536000; includeSubDomains once the whole "
                             "site works over HTTPS.",
    "security/cookie-not-secure": "Set the Secure flag on this cookie so it is never sent over plain HTTP.",
    "security/cookie-not-httponly": "Set the HttpOnly flag on this session cookie so page scripts (and XSS) cannot "
                                    "read it.",
    "security/source-map-exposed": "Do not deploy .map files to production (or restrict access to them): they "
                                   "reveal the original source code.",
}

LOOPBACK = ("localhost", "127.0.0.1", "::1", "[::1]")
SESSION_COOKIE = re.compile(r"sess|sid$|^sid|auth|token|jwt|login|remember", re.I)
NOT_SESSION = re.compile(r"csrf|xsrf", re.I)   # токен CSRF читается скриптом намеренно
MAP_COMMENT = re.compile(rb"[#@]\s*sourceMappingURL=(\S+)\s*(?:\*/)?\s*$")


def _get(ctx, url: str) -> tuple[int | None, bytes]:
    key = f"sec-fetch:{url}"
    if key not in ctx.site.cache:
        try:
            r = ctx.browser_context.request.get(url, timeout=10000, max_redirects=3)
            ctx.site.cache[key] = (r.status, r.body()[:4096])
        except Exception:
            ctx.site.cache[key] = (None, b"")
    return ctx.site.cache[key]


def _source_maps(ctx) -> list[Finding]:
    out = []
    origin = urlparse(ctx.url).netloc
    for req, rec in list(ctx.events.requests.items()):
        if req.resource_type not in ("script", "stylesheet") or rec["status"] != 200:
            continue
        if urlparse(req.url).netloc != origin or not ctx.site.first_time(f"map:{req.url}"):
            continue
        map_url = req.url.split("?")[0] + ".map"
        try:
            resp = req.response()
            header = resp.headers.get("sourcemap") or resp.headers.get("x-sourcemap") if resp else None
            tail = resp.body()[-300:] if resp else b""
        except Exception:
            header, tail = None, b""
        m = MAP_COMMENT.search(tail.rstrip())
        if header:
            map_url = urljoin(req.url, header)
        elif m and not m.group(1).startswith(b"data:"):
            map_url = urljoin(req.url, m.group(1).decode("utf-8", "replace"))
        status, body = _get(ctx, map_url)
        if status == 200 and b'"mappings"' in body:
            out.append(Finding(
                severity="notice", category=CATEGORY, rule="security/source-map-exposed", page=ctx.path, url=map_url,
                message=f"Source map is publicly available: {map_url.rsplit('/', 1)[-1]}",
                details=f"{map_url} (source map of {req.url}) answers HTTP 200 with a source map.",
                evidence={"asset": req.url, "status": status}))
    return out


def run(page, ctx) -> list[Finding]:
    u = urlparse(ctx.url)
    https = u.scheme == "https"
    loopback = (u.hostname or "") in LOOPBACK
    out: list[Finding] = []
    p = ctx.path

    def add(rule, sev, message, details, **kw):
        out.append(Finding(severity=sev, category=CATEGORY, rule=rule, page=p, message=message, details=details, **kw))

    if not https and not loopback and ctx.site.first_time("no-https"):
        add("security/no-https", "warning", "Site is served over plain HTTP",
            f"{ctx.url} is loaded over http://, so traffic can be read and changed in transit.", url=ctx.url)
    if https:
        for req in list(ctx.events.requests):
            if req.url.startswith("http://"):
                add("security/mixed-content", "warning", "HTTP resource on an HTTPS page",
                    f"The HTTPS page {p} loads {req.url} ({req.resource_type}) over plain HTTP.", url=req.url,
                    evidence={"resourceType": req.resource_type})

    # заголовки и cookies нашего временного сервера для папки ничего не говорят о проекте
    if not ctx.site.local_folder and ctx.response is not None and ctx.site.first_time("headers"):
        h = {k.lower(): v for k, v in ctx.response.headers.items()}
        ev = {"headers": sorted(h)}
        if "content-security-policy" not in h:
            add("security/missing-csp", "notice", "No Content-Security-Policy header",
                f"The response for {p} has no Content-Security-Policy header.", evidence=ev)
        if h.get("x-content-type-options", "").lower() != "nosniff":
            add("security/missing-nosniff", "notice", "No X-Content-Type-Options: nosniff header",
                f"The response for {p} has no X-Content-Type-Options: nosniff header.", evidence=ev)
        if https and "strict-transport-security" not in h:
            add("security/missing-hsts", "notice", "No Strict-Transport-Security header",
                f"The HTTPS response for {p} has no Strict-Transport-Security header.", evidence=ev)
    if not ctx.site.local_folder:
        for c in ctx.browser_context.cookies(ctx.url):
            name = c["name"]
            if https and not c.get("secure") and ctx.site.first_time(f"cookie-secure:{name}"):
                add("security/cookie-not-secure", "warning", f"Cookie «{name}» has no Secure flag",
                    f"The cookie «{name}» set on {p} over HTTPS has no Secure flag.",
                    evidence={"cookie": name, "domain": c.get("domain")})
            if (SESSION_COOKIE.search(name) and not NOT_SESSION.search(name) and not c.get("httpOnly")
                    and ctx.site.first_time(f"cookie-httponly:{name}")):
                add("security/cookie-not-httponly", "warning", f"Session cookie «{name}» has no HttpOnly flag",
                    f"The cookie «{name}» looks like a session cookie but has no HttpOnly flag, so page "
                    f"scripts can read it.", evidence={"cookie": name, "domain": c.get("domain")})
    return out + _source_maps(ctx)
