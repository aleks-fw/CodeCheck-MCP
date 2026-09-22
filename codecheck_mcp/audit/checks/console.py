"""Console: console.error, необработанные исключения и отклонённые промисы."""
from __future__ import annotations

import re
from typing import Any

from ..core.finding import Finding

CATEGORY = "console"
PER_VIEWPORT = False

RECOMMENDATIONS = {
    "console/uncaught-exception": "Fix the code at the source location in evidence: an uncaught exception stops the "
                                  "rest of that script, so features after it silently do not work.",
    "console/unhandled-rejection": "Add error handling (catch / try-await) to the promise chain named in evidence "
                                   "and show the user a fallback state when the operation fails.",
    "console/error": "Find the console.error call or failing operation at the source location in evidence and fix "
                     "the underlying problem instead of hiding the message.",
}

# сообщение Chromium о неудачной загрузке ресурса: это покрывает проверка network
_RESOURCE_ERROR = "Failed to load resource"
_FRAME = re.compile(r"(https?://[^\s)]+?):(\d+):(\d+)")


def _source_from_stack(stack: str) -> str | None:
    m = _FRAME.search(stack or "")
    return f"{m.group(1)}:{m.group(2)}:{m.group(3)}" if m else None


def _source_from_location(loc: dict[str, Any] | None) -> str | None:
    if not loc or not loc.get("url"):
        return None
    return f"{loc['url']}:{loc.get('lineNumber', 0) + 1}:{loc.get('columnNumber', 0) + 1}"


def run(page, ctx) -> list[Finding]:
    try:
        rejections = page.evaluate("() => window.__ccRejections || []")
    except Exception:
        rejections = []
    rejected = {r["message"] for r in rejections}

    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def add(rule: str, text: str, evidence: dict[str, Any]) -> None:
        g = groups.setdefault((rule, text), {"evidence": evidence, "count": 0})
        g["count"] += 1

    for e in ctx.events.pageerrors:
        if e["message"] in rejected:  # Chromium присылает отклонённый промис ещё и как pageerror
            continue
        text = f"{e['name']}: {e['message']}" if e["name"] else e["message"]
        add("console/uncaught-exception", text, {"stack": e["stack"][:2000], "source": _source_from_stack(e["stack"])})
    for r in rejections:
        add("console/unhandled-rejection", r["message"],
            {"stack": r["stack"][:2000], "source": _source_from_stack(r["stack"])})
    for c in ctx.events.console:
        if c["text"].startswith(_RESOURCE_ERROR):
            continue
        add("console/error", c["text"], {"source": _source_from_location(c["location"])})

    severity = {"console/uncaught-exception": "critical", "console/unhandled-rejection": "warning",
                "console/error": "warning"}
    title = {"console/uncaught-exception": "Uncaught exception", "console/unhandled-rejection":
             "Unhandled promise rejection", "console/error": "console.error"}
    out = []
    for (rule, text), g in groups.items():
        short = text.splitlines()[0][:150] if text else "(empty message)"
        ev = {k: v for k, v in g["evidence"].items() if v}
        ev.update(text=text[:2000], count=g["count"])
        where = f" at {ev['source']}" if ev.get("source") else ""
        out.append(Finding(
            severity=severity[rule], category=CATEGORY, rule=rule, page=ctx.path,
            message=f"{title[rule]}: {short}",
            details=f"{title[rule]} on {ctx.path} while loading the page{where}: {text[:500]} "
                    f"(seen {g['count']} time(s)).",
            evidence=ev))
    return out
