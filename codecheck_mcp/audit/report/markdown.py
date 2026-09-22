"""report.md: сводка, находки по серьёзности и категориям, страницы, рекомендации по встреченным правилам."""
from __future__ import annotations

import json
from typing import Any

from ..core.finding import CATEGORIES, SEVERITIES, Finding

SECTION = {"critical": "🔴 Critical", "warning": "🟠 Warnings", "notice": "🟡 Notices"}
NO_RECOMMENDATION = "No recommendation is defined for this rule yet."


def _finding(f: Finding) -> list[str]:
    out = [f"#### {f.id} · `{f.rule}`", "", f"**{f.message}**", "", f.details, ""]
    meta = [f"- **Page:** `{f.page}`"]
    if f.viewport:
        meta.append(f"- **Viewport:** {f.viewport}")
    if f.selector:
        meta.append(f"- **Selector:** `{f.selector}`")
    if f.url:
        meta.append(f"- **URL:** {f.url}")
    if f.evidence:
        meta.append(f"- **Evidence:** `{json.dumps(f.evidence, ensure_ascii=False)}`")
    meta.append(f"- **Fingerprint:** `{f.fingerprint}`")
    out += meta
    if f.screenshot:
        out += ["", f"![{f.id}]({f.screenshot})"]
    return out + [""]


def render(data: dict[str, Any], findings: list[Finding], recommendations: dict[str, str],
           changes: list[str] | None = None, prioritized: list[str] | None = None) -> str:
    """changes: сравнение с прошлым прогоном, сразу после заголовка; prioritized: Prioritized Issues после него."""
    c = data["summary"]
    out = [
        "# CodeCheck audit report", "",
        f"- **Project:** {data['project']}",
        f"- **URL:** {data['url']}",
        f"- **Date:** {data['date']}",
        f"- **Pages tested:** {len(data['pages'])}",
        f"- **Viewports:** {', '.join(data['viewports'])}",
        f"- **Tool:** codecheck-mcp {data['version']}", "",
        *(changes or []),
        *(prioritized or []),
        "## Summary", "",
        "| Severity | Count |", "|---|---|",
        *[f"| {SECTION[s]} | {c[s]} |" for s in SEVERITIES], "",
    ]
    for sev in SEVERITIES:
        items = [f for f in findings if f.severity == sev]
        out += [f"## {SECTION[sev]} ({len(items)})", ""]
        if not items:
            out += ["None.", ""]
            continue
        for cat in CATEGORIES:
            group = [f for f in items if f.category == cat]
            if group:
                out += [f"### {cat}", ""]
                for f in group:
                    out += _finding(f)
    out += ["## Pages tested", "", *[f"- `{p}`" for p in data["pages"]], ""]
    if data.get("errors"):
        out += ["## Run errors", "", "These checks did not finish; their results are missing from this report.", "",
                *[f"- `{e['check']}` on `{e['page']}` ({e['viewport']}): {e['error']}" for e in data["errors"]], ""]
    rules = sorted({f.rule for f in findings})
    out += ["## Recommendations", ""]
    out += [f"- `{r}`: {recommendations.get(r, NO_RECOMMENDATION)}" for r in rules] or ["Nothing to fix."]
    return "\n".join(out) + "\n"
