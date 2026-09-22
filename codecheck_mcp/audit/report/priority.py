"""Prioritized Issues: находки группируются по общей причине и сортируются по серьёзности и влиянию.

Связи строятся только по фактам из находок:
- одна и та же проблема на разных страницах: тот же URL ресурса, тот же селектор или тот же текст (подтверждено);
- причина -> последствие: тот же URL запроса или URL упомянут в тексте ошибки (подтверждено); та же страница
  и типичная связь, например упавший скрипт и ReferenceError (предположение, помечается как Likely).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..core.finding import Finding

LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
ICON = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}
NO_RECOMMENDATION = "No recommendation is defined for this rule yet."

# категория группы: по правилу, иначе по категории находки
_RULE_CATEGORY = [
    ("network/slow-request", "performance"),
    ("network/image-failed", "visual"), ("images/broken", "visual"),
    ("network/stylesheet-failed", "visual"), ("network/font-failed", "visual"),
    ("images/missing-alt", "accessibility"),
    ("images/heavy", "performance"), ("images/oversized", "performance"),
]
_CATEGORY = {"interaction": "functionality", "console": "functionality", "network": "functionality",
             "layout": "responsive", "performance": "performance", "accessibility": "accessibility",
             "security": "security", "fonts": "visual", "images": "visual", "seo": "other"}

# для этих правил одна и та же проблема на разных страницах узнаётся по URL ресурса
_URL_RULES = ("network/", "interaction/action-request-failed", "images/heavy", "images/broken", "images/oversized",
              "performance/large-js", "performance/large-css", "security/source-map-exposed",
              "security/mixed-content")
_FETCHY = re.compile(r"fetch|xhr|http|status|request|network|api\b|\b[45]\d\d\b", re.I)
_MISSING_CODE = re.compile(r"is not defined|is not a function|cannot read propert|undefined is not", re.I)


def category_of(f: Finding) -> str:
    for rule, cat in _RULE_CATEGORY:
        if f.rule == rule:
            return cat
    return _CATEGORY.get(f.category, "other")


def _path(url: str | None) -> str:
    u = urlparse(url or "")
    return (u.path or "/") + (f"?{u.query}" if u.query else "")


def _cluster_key(f: Finding) -> tuple[str, str]:
    if f.url and f.rule.startswith(_URL_RULES):
        return f.rule, _path(f.url)
    return f.rule, f.selector or f.message


@dataclass
class _Cluster:
    key: tuple[str, str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def root(self) -> Finding:
        order = ("critical", "warning", "notice")
        return min(self.findings, key=lambda f: (order.index(f.severity), f.id))

    @property
    def pages(self) -> set[str]:
        return {f.page for f in self.findings}

    @property
    def rule(self) -> str:
        return self.key[0]


@dataclass
class _Link:
    cause: _Cluster
    effect: _Cluster
    confirmed: bool
    reason: str


@dataclass
class Group:
    root: Finding
    findings: list[Finding]
    related: list[tuple[Finding, bool, str]]   # (находка, связь подтверждена, основание)
    severity: str = ""
    category: str = ""
    impact: int = 0
    impact_basis: dict[str, int] = field(default_factory=dict)
    id: str = ""

    @property
    def pages(self) -> list[str]:
        return sorted({f.page for f in self.findings})

    @property
    def confirmed(self) -> bool:
        return all(ok for _, ok, _ in self.related)

    @property
    def title(self) -> str:
        r = self.root
        path = _path(r.url) if r.url else ""
        return f"{r.message} ({path})" if path and path not in r.message else r.message

    def root_cause(self) -> str:
        spread = f" Seen on {len(self.pages)} pages." if len(self.pages) > 1 else ""
        return " ".join(f"{self.root.details}{spread}".split())  # одной строкой: axe пишет многострочно

    def evidence(self) -> dict[str, list[Any]]:
        def uniq(xs, n):
            return list(dict.fromkeys(x for x in xs if x))[:n]
        fs = self.findings
        requests = []
        for f in fs:
            ev = f.evidence or {}
            listed = ev.get("requests")  # у performance/too-many-requests это число, а не список
            for r in listed if isinstance(listed, list) else ([ev] if "status" in ev and "method" in ev else []):
                requests.append(f"{r.get('method', 'GET')} {r.get('url', f.url)} → "
                                f"{r.get('status', r.get('error', '?'))}")
        return {
            "screenshots": uniq([f.screenshot for f in fs], 5),
            "urls": uniq([f.url for f in fs], 5),
            "selectors": uniq([f.selector for f in fs], 5),
            "requests": uniq(requests, 5),
            "console": uniq([(f.evidence or {}).get("text") for f in fs if f.category == "console"], 3),
        }

    def to_dict(self, recommendation: str) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "severity": self.severity, "category": self.category,
            "impact": self.impact, "impactBasis": self.impact_basis, "affectedPages": self.pages,
            "rootCause": {"text": self.root_cause(), "confirmed": self.confirmed, "finding": self.root.id,
                          "rule": self.root.rule},
            "relatedIssues": [{"finding": f.id, "rule": f.rule, "page": f.page, "message": f.message,
                               "confirmed": ok, "link": why} for f, ok, why in self.related],
            "recommendation": recommendation, "evidence": self.evidence(),
            "findings": [f.id for f in self.findings],
        }


def _links(clusters: list[_Cluster]) -> list[_Link]:
    """Все связи «причина -> последствие» между кластерами, с основанием."""
    out = []
    by_rule: dict[str, list[_Cluster]] = {}
    for c in clusters:
        by_rule.setdefault(c.rule, []).append(c)

    def of(*rules):
        return [c for r in rules for c in by_rule.get(r, [])]

    def text(f: Finding) -> str:
        ev = f.evidence or {}
        return f"{ev.get('text', '')}\n{ev.get('stack', '')}\n{f.message}"

    apis = of("network/api-5xx", "network/api-4xx")
    for api in apis + of("interaction/action-request-failed"):
        path = api.key[1]
        for c in of("interaction/action-request-failed"):
            if c is not api and c.key[1] == path and api.rule != c.rule:
                out.append(_Link(api, c, True, f"the click sends the same failing request {path}"))
        for c in of("console/error", "console/unhandled-rejection", "console/uncaught-exception"):
            same_page = [f for f in c.findings if f.page in api.pages]
            if any(path in text(f) for f in same_page):
                out.append(_Link(api, c, True, f"the error text mentions {path}"))
            elif any(_FETCHY.search(text(f)) for f in same_page):
                out.append(_Link(api, c, False, f"same page as the failing request {path}, and the error is "
                                                "about a request; the text does not name the URL"))
    for js in of("network/script-failed"):
        for c in of("console/uncaught-exception", "console/error"):
            if any(f.page in js.pages and _MISSING_CODE.search(text(f)) for f in c.findings):
                out.append(_Link(js, c, False, f"same page as the missing script {js.key[1]}, and the error is "
                                               "about code that is not defined"))
        for c in of("interaction/no-effect", "interaction/critical-not-checked"):
            if c.pages & js.pages:
                out.append(_Link(js, c, False, f"same page as the missing script {js.key[1]}, which may hold "
                                               "the click handler"))
    for css in of("network/stylesheet-failed"):
        for c in clusters:
            if c.rule.startswith("layout/") and c.pages & css.pages:
                out.append(_Link(css, c, False, f"same page as the missing stylesheet {css.key[1]}"))
    for exc in of("console/uncaught-exception"):
        for c in of("interaction/no-effect"):
            if c.pages & exc.pages:
                out.append(_Link(exc, c, False, "same page as an uncaught exception, which may have stopped the "
                                                "script that attaches the click handler"))
    for weight in of("performance/page-weight"):
        largest = {_path(x.get("url")) for f in weight.findings for x in (f.evidence or {}).get("largest", [])}
        for c in of("images/heavy", "performance/large-js", "performance/large-css"):
            if c.key[1] in largest and c.pages & weight.pages:
                out.append(_Link(weight, c, True, "the file is among the largest downloads of this page"))
    for slow in of("network/slow-request"):
        for c in of("performance/slow-load"):
            if c.pages & slow.pages:
                out.append(_Link(slow, c, False, f"same page as the slow request {slow.key[1]}"))
    return out


_SEV = {"critical": 0, "warning": 1, "notice": 2}


def _level(g: Group) -> str:
    worst = min(_SEV[f.severity] for f in g.findings)
    if worst == 0:
        return "CRITICAL"
    if worst == 1:
        return "HIGH" if g.category in ("functionality", "security") else "MEDIUM"
    return "LOW"


def _impact(g: Group, total_pages: int) -> tuple[int, dict[str, int]]:
    """Влияние на пользователя 1-10: прозрачная сумма, каждая часть видна в impactBasis."""
    worst = min(_SEV[f.severity] for f in g.findings)
    basis = {"severity": (8, 5, 2)[worst]}
    if worst < 2 and g.category in ("functionality", "security"):
        basis["breaks a function or exposes data"] = 1
    n = len(g.pages)
    if n >= 3 and total_pages and n * 2 >= total_pages:
        basis["on most pages"] = 2
    elif n >= 2:
        basis["on several pages"] = 1
    if any((f.evidence or {}).get("critical") for f in g.findings):
        basis["key action (criticalSelectors)"] = 1
    if len(g.related) >= 2:
        basis["causes other issues"] = 1
    return max(1, min(10, sum(basis.values()))), basis


def build(findings: list[Finding], total_pages: int) -> list[Group]:
    clusters: dict[tuple[str, str], _Cluster] = {}
    for f in findings:
        clusters.setdefault(_cluster_key(f), _Cluster(_cluster_key(f))).findings.append(f)
    cl = list(clusters.values())

    # у каждого последствия одна причина: подтверждённая связь важнее, затем более серьёзная причина
    best: dict[int, _Link] = {}
    for link in sorted(_links(cl), key=lambda x: (not x.confirmed, _SEV[x.cause.root.severity], x.cause.root.id)):
        best.setdefault(id(link.effect), link)

    def top(c: _Cluster, seen: set[int]) -> tuple[_Cluster, list[_Link]]:
        """Первопричина цепочки и связи по пути (циклы обрываются)."""
        link = best.get(id(c))
        if link is None or id(link.cause) in seen:
            return c, []
        root, path = top(link.cause, seen | {id(c)})
        return root, path + [link]

    groups: dict[int, Group] = {}
    for c in cl:
        root, path = top(c, {id(c)})
        g = groups.get(id(root))
        if g is None:
            g = groups[id(root)] = Group(root=root.root, findings=[], related=[])
        g.findings += c.findings
        if c is not root:
            ok = all(x.confirmed for x in path)
            why = "; then ".join(x.reason for x in reversed(path))
            g.related += [(f, ok, why) for f in c.findings]

    out = list(groups.values())
    for g in out:
        g.findings.sort(key=lambda f: f.id)
        g.related.sort(key=lambda x: x[0].id)
        g.category = category_of(g.root)
        g.severity = _level(g)
        g.impact, g.impact_basis = _impact(g, total_pages)
    out.sort(key=lambda g: (LEVELS.index(g.severity), -g.impact, -len(g.pages), g.root.id))
    for n, g in enumerate(out, 1):
        g.id = f"G-{n:02d}"
    return out


def render(groups: list[Group], recommendations: dict[str, str]) -> list[str]:
    """Раздел Prioritized Issues для report.md."""
    out = ["## Prioritized Issues", "",
           "Findings grouped by a shared cause and sorted by severity and user impact. **Root cause** is backed by "
           "the evidence of the findings; **Likely root cause** means at least one link below is inferred from the "
           "page and the kind of error, not proven.", ""]
    if not groups:
        return out + ["No issues found.", ""]
    for g in groups:
        label = "Root cause" if g.confirmed else "Likely root cause"
        basis = ", ".join(f"{k} {'+' if i else ''}{v}" for i, (k, v) in enumerate(g.impact_basis.items()))
        out += [f"### {ICON[g.severity]} {g.severity} — {g.title}", "",
                f"- **Impact:** {g.impact}/10 ({basis})",
                f"- **Category:** {g.category}",
                "- **Affected pages:** " + ", ".join(f"`{p}`" for p in g.pages),
                f"- **{label}:** {g.root_cause()} ({g.root.id})"]
        if g.related:
            out.append("- **Related issues:**")
            for f, ok, why in g.related:
                out.append(f"  - {f.id} `{f.rule}` on `{f.page}`: {f.message} "
                           f"({'confirmed' if ok else 'likely'}: {why})")
        linked = {x[0].id for x in g.related} | {g.root.id}
        others = [f for f in g.findings if f.id not in linked]
        if others:
            out.append("- **Same problem also on:** " + ", ".join(f"`{f.page}` ({f.id})" for f in others))
        out.append(f"- **Recommendation:** {recommendations.get(g.root.rule, NO_RECOMMENDATION)}")
        ev = {k: v for k, v in g.evidence().items() if v}
        if ev:
            out.append("- **Evidence:** " + " · ".join(
                f"{k}: " + ", ".join(f"`{x}`" if k != "screenshots" else f"[{x}]({x})" for x in v)
                for k, v in ev.items()))
        out.append("")
    return out


def summary(groups: list[Group], limit: int = 5) -> list[str]:
    """Первые группы для ответа MCP."""
    if not groups:
        return []
    lines = [f"Top issues ({min(limit, len(groups))} of {len(groups)} groups):"]
    for g in groups[:limit]:
        rel = f" · {len(g.related)} related" if g.related else ""
        lines.append(f"- {g.id} {ICON[g.severity]} {g.severity} · impact {g.impact}/10 · {g.title} · "
                     f"pages: {', '.join(g.pages[:4])}{'…' if len(g.pages) > 4 else ''}{rel}")
    return lines


def to_json(groups: list[Group], recommendations: dict[str, str]) -> list[dict[str, Any]]:
    return [g.to_dict(recommendations.get(g.root.rule, NO_RECOMMENDATION)) for g in groups]
