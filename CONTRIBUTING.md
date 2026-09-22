# Contributing / Участие в проекте

Issues and pull requests are welcome, in English or Russian.
Замечания и pull request'ы приветствуются, на русском или английском.

## Setup

```bash
git clone https://github.com/aleks-fw/CodeCheck-MCP.git
cd CodeCheck-MCP
python -m venv .venv
.venv/Scripts/pip install -e ".[test]"        # Windows; on macOS/Linux use .venv/bin/pip
.venv/Scripts/python -m playwright install chromium
.venv/Scripts/python -m pytest tests -q
```

## Adding or changing an audit_project check

Checks of `audit_project` live in `codecheck_mcp/audit/checks/`, one module per category. A module defines
`CATEGORY`, `PER_VIEWPORT`, `RECOMMENDATIONS` (one line per rule it can emit) and `run(page, ctx) -> list[Finding]`,
and is registered in `REGISTRY` in `codecheck_mcp/audit/checks/__init__.py`. The page is already loaded; console and
network events recorded since before the load are in `ctx.events`. Thresholds go to
`codecheck_mcp/audit/thresholds.py`. If another check can find the same problem, add the rule to `ALIASES` in
`codecheck_mcp/audit/core/fingerprint.py` so it is reported once. If a new rule can cause or explain other findings, add the link
to `_links` in `codecheck_mcp/audit/report/priority.py`, marked confirmed only when the findings themselves prove it. Run `ruff check codecheck_mcp tests` and
`mypy codecheck_mcp` along with the tests.

## Adding or changing a check of the quick tools

Checks live in `codecheck_mcp/checks/`. A check is a function
`check_x(browser, url, report, **_)` that opens the page with `new_page` / `goto` from `codecheck_mcp/browser.py`
and records problems with `report.add(check, severity, message, page=..., selector=..., screenshot=...)`.
Register a new check in `codecheck_mcp/server.py`.

1. **Write the fixtures first.** Add an HTML page with the deliberate bug and, next to it, a clean page that must
   produce no findings (`tests/fixtures/`).
2. **Write the test**, run it, and watch it fail for the right reason.
3. **Implement the check**, then run the whole suite.

## False positives

A check that cries wolf is worse than no check. If you find a false positive on a real site, add a small fixture
that reproduces it (see `tests/fixtures/edge_ok.html`) and a test asserting there are no findings, then fix the
rule. Prefer measurable rules over guesses, and say in the message what was measured.

## Rules of thumb

- The project under test is read-only: never write to it, and never send data to external domains.
- Secrets must be masked in every message that reaches a report.
- Keep the README (both languages) in sync with what the tools actually do.
- Tested platform so far: Windows, Python 3.14. Reports from other platforms are very welcome.
