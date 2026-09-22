import asyncio

from conftest import fixture_path
from fastmcp import Client

from codecheck_mcp.server import mcp

EXPECTED = {"full_qa", "test_interactions", "test_layout", "test_fonts", "test_images", "quick_security", "audit_project"}


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


def test_audit_project_tool_rejects_unknown_category():
    _, res = call("audit_project", {"url": fixture_path("clean.html"), "checks": ["bogus"]})
    assert res.content[0].text.startswith("Error: Unknown check categories: bogus"), res.content[0].text


def test_audit_project_tool_runs_and_returns_paths(tmp_path):
    _, res = call("audit_project", {"url": fixture_path("clean.html"), "viewports": [1280], "outputDir": str(tmp_path)})
    text = res.content[0].text
    assert "Critical: 0" in text and str(tmp_path / "current.json") in text, text
    assert (tmp_path / "report.md").exists() and (tmp_path / "current.json").exists()
