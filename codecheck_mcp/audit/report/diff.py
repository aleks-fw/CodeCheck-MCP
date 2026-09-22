"""Сравнение двух прогонов по fingerprint: Fixed, New, Unchanged."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.finding import Finding


@dataclass
class Diff:
    previous_date: str
    previous_url: str
    fixed: list[Finding] = field(default_factory=list)       # были раньше, в этом прогоне не найдены
    new: list[Finding] = field(default_factory=list)         # есть только в этом прогоне
    unchanged: list[Finding] = field(default_factory=list)   # есть в обоих (из текущего прогона)
    not_rechecked: list[Finding] = field(default_factory=list)  # были раньше, но этот прогон их не проверял

    def to_dict(self) -> dict[str, Any]:
        return {"previousDate": self.previous_date, "previousUrl": self.previous_url,
                "fixed": [f.fingerprint for f in self.fixed], "new": [f.fingerprint for f in self.new],
                "unchanged": [f.fingerprint for f in self.unchanged],
                "notRechecked": [f.fingerprint for f in self.not_rechecked]}


def _viewports(f: Finding) -> set[str]:
    return set((f.evidence or {}).get("viewports") or ([f.viewport] if f.viewport else []))


def _rechecked(f: Finding, prev: dict[str, Any], cur: dict[str, Any]) -> bool:
    """Проверял ли текущий прогон то место, где была находка: ту же категорию, страницу и ширину экрана."""
    if f.category not in cur.get("checks", []):
        return False
    crawled_before = f.page in prev.get("pages", [])   # /robots.txt и т. п. не обходятся, их проверяют всегда
    if crawled_before and f.page not in cur.get("pages", []):
        return False
    vps = _viewports(f)
    return not vps or bool(vps & set(cur.get("viewports", [])))


def compare(prev: dict[str, Any], prev_findings: list[Finding],
            cur: dict[str, Any], cur_findings: list[Finding]) -> Diff:
    before = {f.fingerprint: f for f in prev_findings}
    now = {f.fingerprint: f for f in cur_findings}
    d = Diff(prev.get("date", "?"), prev.get("url", "?"))
    d.new = [f for fp, f in now.items() if fp not in before]
    d.unchanged = [f for fp, f in now.items() if fp in before]
    for fp, f in before.items():
        if fp not in now:
            (d.fixed if _rechecked(f, prev, cur) else d.not_rechecked).append(f)
    return d


def _line(f: Finding) -> str:
    return f"- {f.id} `{f.rule}` on `{f.page}`: {f.message}"


def render(d: Diff | None, current_url: str = "") -> list[str]:
    """Раздел для начала report.md."""
    out = ["## Changes since the previous run", ""]
    if d is None:
        return out + ["No previous run to compare with (this is the first run for this output folder).", ""]
    out.append(f"Compared with the run of {d.previous_date}.")
    if current_url and d.previous_url != current_url:
        out.append(f"Note: the previous run audited {d.previous_url}, this one audits {current_url}.")
    out += ["", f"✅ Fixed: {len(d.fixed)} · 🔴 New: {len(d.new)} · ⚠️ Unchanged: {len(d.unchanged)}", ""]
    if d.fixed:
        out += ["### ✅ Fixed", "", "IDs are from the previous run.", "", *map(_line, d.fixed), ""]
    if d.new:
        out += ["### 🔴 New", "", *map(_line, d.new), ""]
    if d.unchanged:
        out += ["### ⚠️ Unchanged", "", *map(_line, d.unchanged), ""]
    if d.not_rechecked:
        out += ["### Not rechecked", "",
                "Found in the previous run, but this run did not check that category, page or viewport, "
                "so it is unknown whether they are fixed.", "", *map(_line, d.not_rechecked), ""]
    return out


def summary(d: Diff | None, limit: int = 10) -> list[str]:
    """Короткий блок для ответа MCP."""
    if d is None:
        return ["No previous run to compare with."]
    lines = [f"Since the previous run: ✅ Fixed {len(d.fixed)} · 🔴 New {len(d.new)} · "
             f"⚠️ Unchanged {len(d.unchanged)}" + (f" · not rechecked {len(d.not_rechecked)}" if d.not_rechecked else "")]
    for title, items in (("Fixed", d.fixed), ("New", d.new)):
        if items:
            lines += [f"{title}:"] + [f"  {_line(f)[2:]}" for f in items[:limit]]
            if len(items) > limit:
                lines.append(f"  … and {len(items) - limit} more")
    return lines
