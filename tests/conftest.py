from pathlib import Path

import pytest

import codecheck_mcp.report as report_mod

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reports_in_tmp(tmp_path, monkeypatch):
    """Тесты пишут отчёты во временную папку, а не в reports/."""
    monkeypatch.setattr(report_mod, "REPORTS_DIR", tmp_path)


def fixture_path(name: str) -> str:
    return str(FIXTURES / name)
