import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report as report_mod  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reports_in_tmp(tmp_path, monkeypatch):
    """Тесты пишут отчёты во временную папку, а не в reports/."""
    monkeypatch.setattr(report_mod, "REPORTS_DIR", tmp_path)


def fixture_path(name: str) -> str:
    return str(FIXTURES / name)
