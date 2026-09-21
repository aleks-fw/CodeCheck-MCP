import asyncio

from fastmcp import Client

from server import mcp

from conftest import fixture_path

EXPECTED = {"full_qa", "test_interactions", "test_layout", "test_fonts", "test_images", "quick_security"}


def call(name, args):
    async def go():
        async with Client(mcp) as c:
            tools = {t.name for t in await c.list_tools()}
            res = await c.call_tool(name, args) if name else None
            return tools, res
    return asyncio.run(go())


def test_all_tools_registered_and_fonts_tool_works():
    tools, res = call("test_fonts", {"target": fixture_path("fonts_bad.html"), "max_pages": 1})
    assert EXPECTED <= tools, tools
    text = res.content[0].text
    assert "Находок" in text and "report.md" in text, text
    assert "разных шрифтов" in text or "иерархия" in text.lower(), text


def test_missing_path_returns_error_text_not_crash():
    _, res = call("test_layout", {"target": "C:/no/such/folder/xyz"})
    assert "Ошибка" in res.content[0].text
