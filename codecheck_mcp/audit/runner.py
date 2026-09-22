"""audit_project: обход страниц, запуск проверок, дедупликация, скриншоты, current.json и report.md."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from .. import __version__
from .. import report as legacy_report
from ..browser import goto, launch_chromium, open_target
from . import thresholds as T
from .checks import REGISTRY, interaction, recommendations
from .core.crawler import page_key, same_origin_links
from .core.finding import CATEGORIES, SEVERITIES, Finding
from .core.screenshot import capture
from .core.session import PageContext, Site, open_page, page_path
from .report import diff as diff_report
from .report import json_report, markdown

SHOT_SEVERITIES = ("critical", "warning")
# это правило выдаёт сам обход страниц, а не проверка из реестра
CRAWL_RECOMMENDATIONS = {
    "network/page-unavailable": "Fix the link to this page or restore the page: users following it get an error.",
}


def project_name(target: str) -> str:
    if target.startswith(("http://", "https://")):
        u = urlparse(target)
        return u.netloc + (u.path.rstrip("/") if u.path not in ("", "/") else "")
    p = Path(target).expanduser().resolve()
    return p.name if p.is_dir() else f"{p.parent.name}/{p.name}"


def default_output_dir(target: str) -> Path:
    slug = re.sub(r"[^\w.-]+", "-", project_name(target)).strip("-.") or "project"
    return Path(legacy_report.REPORTS_DIR) / slug


@dataclass
class AuditResult:
    out_dir: Path
    data: dict[str, Any]
    findings: list[Finding]
    diff: diff_report.Diff | None = None

    def summary_text(self) -> str:
        c = self.data["summary"]
        lines = [
            f"CodeCheck audit of {self.data['url']}: {len(self.data['pages'])} page(s), "
            f"viewports {', '.join(self.data['viewports'])}.",
            f"Critical: {c['critical']} · Warnings: {c['warning']} · Notices: {c['notice']}",
        ]
        crit = [f for f in self.findings if f.severity == "critical"]
        if crit:
            lines += ["", "Critical:"] + [f"- {f.id} `{f.rule}` on {f.page}: {f.message}" for f in crit]
        lines += [""] + diff_report.summary(self.diff)
        if self.data["errors"]:
            lines += ["", f"Run errors: {len(self.data['errors'])} check run(s) failed, see report.md."]
        lines += ["", f"Report: {self.out_dir / 'report.md'}",
                  f"JSON: {self.out_dir / 'current.json'}",
                  f"Screenshots: {self.out_dir / 'screenshots'}"]
        return "\n".join(lines)


def _select(checks: list[str] | None, registry: list[ModuleType]) -> list[ModuleType]:
    if not checks:
        return list(registry)
    unknown = sorted(set(checks) - set(CATEGORIES))
    if unknown:
        raise ValueError(f"Unknown check categories: {', '.join(unknown)}. Allowed: {', '.join(CATEGORIES)}")
    return [m for m in registry if m.CATEGORY in checks]


class _Collector:
    """Складывает находки без дублей и держит PNG для critical и warning до выдачи ID."""

    def __init__(self) -> None:
        self.found: dict[str, Finding] = {}
        self.shots: dict[str, bytes] = {}

    def add(self, f: Finding, page) -> None:
        key = f.dedupe_key
        old = self.found.get(key)
        if old is not None:
            # то же самое на другом viewport: одна запись, где видно все viewports
            if f.viewport and old.viewport and f.viewport != old.viewport:
                seen = set((old.evidence or {}).get("viewports", [old.viewport])) | {f.viewport}
                old.evidence = {**(old.evidence or {}), "viewports": sorted(seen)}
            if SEVERITIES.index(f.severity) >= SEVERITIES.index(old.severity):
                if not old.selector and f.selector:  # другая проверка знает элемент: отпечаток старый, селектор новый
                    old.selector = f.selector
                return
            self.shots.pop(key, None)  # более серьёзная версия той же проблемы заменяет старую
        self.found[key] = f
        if f.severity in SHOT_SEVERITIES:
            png = capture(page, f.selector)
            if png:
                self.shots[key] = png


def audit(target: str, max_pages: int = T.DEFAULT_MAX_PAGES, viewports: list[int] | None = None,
          checks: list[str] | None = None, critical_selectors: list[str] | None = None,
          output_dir: str | None = None, registry: list[ModuleType] | None = None) -> AuditResult:
    modules = _select(checks, REGISTRY if registry is None else registry)
    widths = sorted(set(viewports or T.DEFAULT_VIEWPORTS), reverse=True)  # самый широкий первым: он основной
    sizes = [(w, T.VIEWPORT_HEIGHTS.get(w, T.DEFAULT_HEIGHT)) for w in widths]

    out = Path(output_dir).expanduser() if output_dir else default_output_dir(target)
    shots_dir = out / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    for old in shots_dir.glob("CC-*.png"):  # скриншоты прошлого прогона больше не соответствуют ID
        old.unlink()
    if (out / "current.json").exists():  # прошлый прогон становится базой для сравнения
        (out / "current.json").replace(out / "previous.json")

    col = _Collector()
    errors: list[dict[str, str]] = []
    pages: list[str] = []
    with open_target(target) as start_url, sync_playwright() as pw:
        browser = launch_chromium(pw)
        try:
            site = Site(start_url, list(critical_selectors or []), [m.CATEGORY for m in modules],
                        local_folder=not target.startswith(("http://", "https://")))
            queue, seen = [start_url], set()
            while queue and len(pages) < max_pages:
                url = queue.pop(0)
                if page_key(url) in seen:
                    continue
                seen.add(page_key(url))
                links = _audit_page(browser, site, url, sizes, modules, col, errors)
                if links is None:
                    continue
                pages.append(page_path(url))
                queue += [u for u in links if page_key(u) not in seen]
            if interaction in modules:
                for f in interaction.unchecked_critical(site):  # находка на весь сайт: без скриншота
                    col.found.setdefault(f.dedupe_key, f)
        finally:
            browser.close()

    order = {s: i for i, s in enumerate(SEVERITIES)}
    cat_order = {c: i for i, c in enumerate(CATEGORIES)}
    findings = sorted(col.found.values(), key=lambda f: (order[f.severity], cat_order[f.category], f.page, f.rule,
                                                          f.target))
    key_of = {id(f): k for k, f in col.found.items()}
    for n, f in enumerate(findings, 1):
        f.id = f"CC-{n:03d}"
        png = col.shots.get(key_of[id(f)])
        if png:
            (shots_dir / f"{f.id}.png").write_bytes(png)
            f.screenshot = f"screenshots/{f.id}.png"

    meta = {"tool": "codecheck-mcp", "version": __version__, "project": project_name(target), "url": target,
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pages": pages,
            "viewports": [f"{w}x{h}" for w, h in sorted(sizes)], "checks": [m.CATEGORY for m in modules],
            "errors": errors}
    data = json_report.build(meta, findings)
    diff = None
    if (out / "previous.json").exists():
        try:
            prev, prev_findings = json_report.load(out / "previous.json")
            diff = diff_report.compare(prev, prev_findings, data, findings)
            data["comparison"] = diff.to_dict()
        except (ValueError, KeyError, TypeError) as e:  # испорченный previous.json не должен ронять прогон
            errors.append({"check": "compare", "page": "-", "viewport": "-", "error": f"previous.json: {e}"})
    json_report.write(out / "current.json", data)
    recs = {**CRAWL_RECOMMENDATIONS, **recommendations(modules)}
    changes = diff_report.render(diff, target)
    (out / "report.md").write_text(markdown.render(data, findings, recs, changes), encoding="utf-8")
    return AuditResult(out, data, findings, diff)


def _audit_page(browser, site: Site, url: str, sizes, modules, col: _Collector, errors) -> list[str] | None:
    """Прогоняет проверки на странице во всех viewport. None, если страница не открылась."""
    links: list[str] = []
    for i, (w, h) in enumerate(sizes):
        primary = i == 0
        bctx, page, events = open_page(browser, site, url, w, h)
        ctx = PageContext(site, url, w, h, primary, bctx, events=events)
        try:
            try:
                ctx.response = goto(page, url)
            except Exception as e:
                col.add(_unreachable(site, url, f"navigation failed: {str(e)[:200]}", None), page)
                return None
            if primary:
                status = ctx.response.status if ctx.response else None
                if status is not None and status >= 400:
                    col.add(_unreachable(site, url, f"the server answered HTTP {status}", status), page)
                    return None
                links = same_origin_links(page, url)
            for m in modules:
                if not (m.PER_VIEWPORT or primary):
                    continue
                try:
                    for f in m.run(page, ctx):
                        col.add(f, page)
                except Exception as e:  # падение одной проверки не роняет прогон, но попадает в отчёт
                    for f in getattr(e, "findings", []):  # то, что проверка успела найти до сбоя
                        col.add(f, page)
                    errors.append({"check": m.CATEGORY, "page": ctx.path, "viewport": ctx.viewport,
                                   "error": f"{type(e).__name__}: {str(e)[:200]}"})
        finally:
            bctx.close()
    return links


def _unreachable(site: Site, url: str, why: str, status: int | None) -> Finding:
    start = page_key(url) == page_key(site.start_url)
    return Finding(
        severity="critical" if start else "warning", category="network", rule="network/page-unavailable",
        page=page_path(url), url=url, message="Page could not be opened",
        details=f"Opening {page_path(url)} failed: {why}." + ("" if start else " The page is linked from the site."),
        evidence={"status": status} if status is not None else None)
