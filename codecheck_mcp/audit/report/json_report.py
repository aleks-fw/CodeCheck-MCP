"""current.json: все findings и метаданные прогона."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.finding import SEVERITIES, Finding


def counts(findings: list[Finding]) -> dict[str, int]:
    return {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}


def build(meta: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    """meta: tool, version, project, url, date, pages, viewports, checks, errors."""
    return {**meta, "summary": counts(findings), "findings": [f.to_dict() for f in findings]}


def write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path: Path) -> tuple[dict[str, Any], list[Finding]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, [Finding.from_dict(d) for d in data.get("findings", [])]
