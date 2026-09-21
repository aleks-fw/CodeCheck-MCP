"""Модель находок и сборка отчёта."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("critical", "high", "medium", "low")
# куда пишутся отчёты: CODECHECK_REPORTS_DIR или ~/codecheck-reports
REPORTS_DIR = Path(os.environ.get("CODECHECK_REPORTS_DIR") or Path.home() / "codecheck-reports")


@dataclass
class Finding:
    check: str            # interactions / layout / fonts / images / security
    severity: str         # critical / high / medium / low
    message: str
    page: str = ""
    selector: str = ""
    viewport: str = ""
    screenshot: str = ""  # путь относительно папки отчёта
    rect: dict | None = None  # {x, y, width, height} для рамки на скриншоте


@dataclass
class Report:
    target: str
    findings: list[Finding] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    out_dir: Path | None = None
    _once: set = field(default_factory=set)

    def first_time(self, key: str) -> bool:
        """True только при первом вызове с этим ключом (для проверок, которые идут раз на проект)."""
        if key in self._once:
            return False
        self._once.add(key)
        return True

    def add(self, check: str, severity: str, message: str, **kw) -> Finding:
        assert severity in SEVERITIES, severity
        f = Finding(check=check, severity=severity, message=message, **kw)
        # одна и та же проблема на одной странице/ширине не дублируется
        key = (f.check, f.message, f.page, f.selector, f.viewport)
        if not any((x.check, x.message, x.page, x.selector, x.viewport) == key for x in self.findings):
            self.findings.append(f)
        return f

    def ensure_dir(self) -> Path:
        if self.out_dir is None:
            self.out_dir = REPORTS_DIR / time.strftime("%Y%m%d-%H%M%S")
            (self.out_dir / "shots").mkdir(parents=True, exist_ok=True)
        return self.out_dir

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for f in self.findings if f.severity == s) for s in SEVERITIES}

    def summary(self) -> str:
        c = self.counts()
        head = (f"Проверено страниц: {len(self.pages)}. Находок: {len(self.findings)} "
                f"(critical {c['critical']}, high {c['high']}, medium {c['medium']}, low {c['low']}).")
        top = sorted(self.findings, key=lambda f: SEVERITIES.index(f.severity))[:10]
        lines = [head] + [f"- [{f.severity}] {f.check}: {f.message} ({f.page}{' ' + f.viewport if f.viewport else ''})"
                          for f in top]
        return "\n".join(lines)

    def write(self) -> Path:
        d = self.ensure_dir()
        out = [f"# QA-отчёт: {self.target}", "", self.summary().split("\n")[0], "",
               "Страницы: " + ", ".join(self.pages), ""]
        for sev in SEVERITIES:
            items = [f for f in self.findings if f.severity == sev]
            if not items:
                continue
            out += [f"## {sev} ({len(items)})", ""]
            for f in items:
                out.append(f"- **{f.check}**: {f.message}")
                meta = [x for x in (f.page, f.viewport, f.selector and f"`{f.selector}`") if x]
                if meta:
                    out.append("  - " + " · ".join(meta))
                if f.screenshot:
                    out.append(f"  - ![]({f.screenshot})")
            out.append("")
        if not self.findings:
            out.append("Проблем не найдено.")
        path = d / "report.md"
        path.write_text("\n".join(out), encoding="utf-8")
        return path
