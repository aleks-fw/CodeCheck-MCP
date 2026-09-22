"""MCP-сервер «QA-тестировщик»: открывает готовый проект в браузере и ищет баги."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import FastMCP

from .audit.report import diff as diff_report
from .audit.report import json_report
from .audit.runner import audit
from .browser import run
from .checks.fonts import check_fonts
from .checks.images import check_images
from .checks.interactions import check_interactions
from .checks.layout import check_layout
from .checks.security import check_security

mcp = FastMCP(
    "codecheck",
    instructions=(
        "Автоматический QA готового веб-проекта. target: URL (https://...) или путь к папке/файлу проекта. "
        "Каждый инструмент возвращает сводку и путь к report.md со скриншотами проблем (красные рамки). "
        "Инструменты только читают проект; клики выполняются в изолированном браузере, внешние переходы блокируются."
    ),
)


async def _run(target: str, checks: list, max_pages: int, **opts) -> str:
    # синхронный Playwright гоняем в потоке, чтобы не блокировать цикл событий MCP
    try:
        rep = await asyncio.to_thread(run, target, checks, None, max_pages, **opts)
    except FileNotFoundError as e:
        return f"Ошибка: {e}"
    except Exception as e:
        return f"Ошибка запуска проверки: {type(e).__name__}: {str(e)[:300]}"
    return f"{rep.summary()}\n\nПолный отчёт: {rep.ensure_dir() / 'report.md'}"


@mcp.tool
async def full_qa(target: str, max_pages: int = 10) -> str:
    """Полный QA: кнопки, вёрстка (5 ширин экрана), шрифты, изображения и лёгкая проверка безопасности."""
    return await _run(target, [check_interactions, check_layout, check_fonts, check_images, check_security], max_pages)


@mcp.tool
async def test_interactions(target: str, max_pages: int = 10) -> str:
    """Кнопки и ссылки: мёртвые кнопки, отключённые, что всё равно реагируют, перекрытые, формы, битые якоря."""
    return await _run(target, [check_interactions], max_pages)


@mcp.tool
async def test_layout(target: str, max_pages: int = 10, widths: list[int] | None = None) -> str:
    """Вёрстка: наложение текста, обрезанный текст, горизонтальный скролл, контраст, мелкие зоны нажатия.
    widths: ширины экрана в px (по умолчанию 320, 375, 768, 1024, 1440)."""
    vps = [(w, 800) for w in widths] if widths else None
    return await _run(target, [check_layout], max_pages, viewports=vps)


@mcp.tool
async def test_fonts(target: str, max_pages: int = 10) -> str:
    """Шрифты: единообразие семейств и размеров, незагрузившиеся веб-шрифты, иерархия заголовков."""
    return await _run(target, [check_fonts], max_pages)


@mcp.tool
async def test_images(target: str, max_pages: int = 10) -> str:
    """Изображения (только измеримое): битые, искажённые, мыльные, тяжёлые, без alt."""
    return await _run(target, [check_images], max_pages)


@mcp.tool
async def quick_security(target: str, max_pages: int = 3) -> str:
    """Лёгкая безопасность: секреты в файлах и истории git, .env в git, заголовки, cookies, mixed content."""
    return await _run(target, [check_security], max_pages)


@mcp.tool
async def audit_project(url: str, maxPages: int = 10, viewports: list[int] | None = None,
                        checks: list[str] | None = None, criticalSelectors: list[str] | None = None,
                        outputDir: str | None = None) -> str:
    """Audit a web project for an automated fix loop (Build → Audit → Fix → Re-audit).
    url: site URL or path to the project folder/file. maxPages: same-origin pages to crawl.
    viewports: widths in px (default 375, 768, 1280). checks: categories (default all).
    criticalSelectors: selectors of key actions; a dead one is critical. outputDir: where current.json,
    report.md and screenshots/ go (default: a folder per project in CODECHECK_REPORTS_DIR).
    Returns counts by severity, the critical findings and paths to the files."""
    try:
        res = await asyncio.to_thread(audit, url, maxPages, viewports, checks, criticalSelectors, outputDir)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Audit failed: {type(e).__name__}: {str(e)[:300]}"
    return res.summary_text()


@mcp.tool
async def compare_reports(previous: str, current: str) -> str:
    """Compare two audit_project JSON reports (paths to current.json / previous.json files) by fingerprint.
    Returns Fixed, New, Unchanged and findings the newer run did not recheck."""
    try:
        prev, prev_findings = json_report.load(Path(previous).expanduser())
        cur, cur_findings = json_report.load(Path(current).expanduser())
    except FileNotFoundError as e:
        return f"Error: file not found: {e.filename}"
    except (ValueError, KeyError, TypeError) as e:
        return f"Error: not an audit_project report: {type(e).__name__}: {str(e)[:200]}"
    d = diff_report.compare(prev, prev_findings, cur, cur_findings)
    return "\n".join(diff_report.render(d, cur.get("url", ""))).strip()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
