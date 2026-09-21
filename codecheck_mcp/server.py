"""MCP-сервер «QA-тестировщик»: открывает готовый проект в браузере и ищет баги."""
from __future__ import annotations

import asyncio

from fastmcp import FastMCP

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
    return f"{rep.summary()}\n\nПолный отчёт: {rep.out_dir / 'report.md'}"


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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
