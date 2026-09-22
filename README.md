<p align="center">
  <img src="assets/banner.svg" alt="CodeCheck MCP" width="100%">
</p>

<h1 align="center">CodeCheck MCP</h1>

<p align="center">
  <a href="#installation">Install</a> ·
  <a href="#the-fix-loop-build--audit--fix--re-audit">Fix loop</a> ·
  <a href="#tools">Tools</a> ·
  <a href="llms-install.md">For AI agents</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="SECURITY.md">Security</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-server-8a2be2" alt="MCP server">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-English-0d9488" alt="English"></a>
  <a href="README.ru.md"><img src="https://img.shields.io/badge/lang-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-d64545" alt="Русский"></a>
</p>

An MCP server that **audits a finished web project in a real browser** and writes a report another AI can fix code
from. It opens the site with Playwright, crawls its pages, clicks the buttons, watches the console and the network,
measures layout at several screen widths, runs axe-core for accessibility, checks SEO, images, fonts, performance
and basic security, and gives every problem a stable ID, a CSS selector, evidence and a screenshot.

Run it again after the fix and it tells you what was fixed, what is new and what is still there.

Tested on Windows and Python 3.14. Other operating systems and Python versions have not been tested.

| | |
|---|---|
| **A real browser** | Chromium via Playwright: real clicks, real layout, real network. Nothing is guessed from the source code. |
| **Made for a fix loop** | `current.json` with one record per problem: rule, page, selector or URL, evidence and a fingerprint that stays the same between runs. |
| **Evidence, not opinions** | Every finding says what was measured. Critical findings and warnings come with a screenshot, the element outlined in red. |
| **Regression view** | Each run is compared with the previous one: ✅ Fixed, 🔴 New, ⚠️ Unchanged. |
| **Safe by design** | Read-only for your project, isolated browser context, navigation to other domains blocked, only passive security checks. |

## Installation

You need Python 3.10+ and an internet connection (Chromium is about 150 MB).

```bash
# 1. Create an environment and install straight from GitHub
python -m venv codecheck-env
codecheck-env/Scripts/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git      # Windows
# codecheck-env/bin/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git        # macOS / Linux

# 2. Download the browser for Playwright (once)
codecheck-env/Scripts/python -m playwright install chromium
```

### Connect to Claude Code

```bash
claude mcp add --scope user codecheck -- "<path>/codecheck-env/Scripts/codecheck-mcp"
```

### Connect to other clients (Claude Desktop, Cursor, ...)

```json
{
  "mcpServers": {
    "codecheck": {
      "command": "<path>/codecheck-env/Scripts/codecheck-mcp",
      "env": { "CODECHECK_REPORTS_DIR": "<where reports go>" }
    }
  }
}
```

`<path>` is the absolute path to the folder where you created the environment. `CODECHECK_REPORTS_DIR` is optional
(default `~/codecheck-reports`). Restart the client and `codecheck` appears in its MCP list.

### If you are an AI agent

Install by following [llms-install.md](llms-install.md).

## The fix loop: Build → Audit → Fix → Re-audit

1. **Build** the site (or start it locally).
2. **Audit.** Ask the agent: *"Run audit_project on http://localhost:5173 with criticalSelectors ["#checkout"]"*.
   You get counts by severity, the list of critical findings and the paths to `report.md` and `current.json`.
3. **Fix.** *"Read current.json and fix the critical findings and warnings. Use the selector, url and evidence of
   each finding to locate the code."* Each finding names the rule, the page, the element or resource and what was
   observed, so the agent does not have to reproduce the bug first.
4. **Re-audit.** Run `audit_project` again with the same `url`. The answer starts with
   `Since the previous run: ✅ Fixed 3 · 🔴 New 0 · ⚠️ Unchanged 12`; repeat until nothing critical is left.

A finding only counts as fixed if the new run checked the same category, page and viewport; otherwise it is listed
as "not rechecked", so a narrower run never reports false fixes.

## Tools

| Tool | Parameters | What it does |
|---|---|---|
| `audit_project` | `url`, `maxPages=10`, `viewports=[375, 768, 1280]`, `checks=all`, `criticalSelectors=[]`, `outputDir` | Full audit for the fix loop, see below |
| `compare_reports` | `previous`, `current` (paths to JSON reports) | Fixed / New / Unchanged between any two `audit_project` reports |
| `full_qa` | `target`, `max_pages=10` | Quick QA with the checks below, report in Russian |
| `test_interactions` | `target`, `max_pages` | Dead buttons, disabled controls that react, covered buttons, forms, double submit, broken anchors |
| `test_layout` | `target`, `max_pages`, `widths=[320, 375, 768, 1024, 1440]` | Overlapping and clipped text, horizontal scroll, contrast (also on images), tap targets under 44 px |
| `test_fonts` | `target`, `max_pages` | Font families, outlier fonts, failed web fonts, size sprawl, heading hierarchy |
| `test_images` | `target`, `max_pages` | Broken, stretched, blurry, heavy images, missing `alt` |
| `quick_security` | `target`, `max_pages=3` | Secrets in files and git history, `.env` in git, headers, cookies, mixed content |

`url` / `target` is a URL or a path to a project folder or file; for a folder a temporary local server is started.

### audit_project

| Parameter | Default | Meaning |
|---|---|---|
| `url` | required | Site URL or project folder / file |
| `maxPages` | `10` | Pages to crawl, same origin only |
| `viewports` | `[375, 768, 1280]` | Screen widths in px (heights 812, 1024, 800) |
| `checks` | all | Any of `interaction`, `layout`, `images`, `fonts`, `console`, `accessibility`, `seo`, `performance`, `security`, `network` |
| `criticalSelectors` | `[]` | Selectors of key actions (e.g. `#checkout`); if one does nothing on click, the finding is critical |
| `outputDir` | `<CODECHECK_REPORTS_DIR>/<project>` | Where `current.json`, `previous.json`, `report.md` and `screenshots/` go |

Example call:

```json
{
  "url": "http://127.0.0.1:8765/",
  "criticalSelectors": ["#checkout"],
  "viewports": [375, 768, 1280]
}
```

Answer (real run on [examples/demo-shop](examples/demo-shop), second run after adding a missing `<title>`):

```text
CodeCheck audit of http://127.0.0.1:8765/: 7 page(s), viewports 375x812, 768x1024, 1280x800.
Critical: 5 · Warnings: 4 · Notices: 25

Critical:
- CC-001 `interaction/no-effect` on /buttons.html: Clicking #checkout does nothing
- CC-002 `console/uncaught-exception` on /errors.html: Uncaught exception: ReferenceError: cartItems is not defined
- CC-003 `accessibility/image-alt` on /media.html: Images must have alternative text
- CC-004 `network/api-5xx` on /api.html: API request returned HTTP 500
- CC-005 `network/script-failed` on /media.html: JavaScript file did not load

Since the previous run: ✅ Fixed 1 · 🔴 New 0 · ⚠️ Unchanged 34
Fixed:
  CC-009 `seo/missing-title` on `/notitle.html`: Page has no title

Report: .../report.md
JSON: .../current.json
Screenshots: .../screenshots
```

A fragment of the same `report.md`:

```markdown
## Changes since the previous run

✅ Fixed: 1 · 🔴 New: 0 · ⚠️ Unchanged: 34

### ✅ Fixed

- CC-009 `seo/missing-title` on `/notitle.html`: Page has no title

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical | 5 |
| 🟠 Warnings | 4 |
| 🟡 Notices | 25 |

## 🔴 Critical (5)

### interaction

#### CC-001 · `interaction/no-effect`

**Clicking #checkout does nothing**

Clicking #checkout on /buttons.html produced no navigation, URL change, network request or visible DOM change
within 2 seconds. This control may depend on app state (cart, login): the page was reloaded before the click,
so the state may have been reset.

- **Page:** `/buttons.html`
- **Selector:** `#checkout`
- **Fingerprint:** `0efe5a1a7da1d417`

![CC-001](screenshots/CC-001.png)
```

The report ends with the list of tested pages and one recommendation per rule that was found.

### Finding format (`current.json`)

```ts
interface Finding {
  id: string;           // CC-001, CC-002... numbered within the run
  fingerprint: string;  // stable hash of rule + page + (selector or url) for comparing runs
  severity: "critical" | "warning" | "notice";
  category: "interaction" | "layout" | "images" | "fonts" | "console"
          | "accessibility" | "seo" | "performance" | "security" | "network";
  rule: string;         // e.g. "seo/missing-title"
  page: string;         // e.g. "/checkout"
  message: string;      // short description
  details: string;      // what exactly was observed
  selector?: string;    // shortest unique CSS selector
  url?: string;         // for resources and requests
  viewport?: string;    // e.g. "375x812"
  screenshot?: string;  // relative path, critical and warning only
  evidence?: Record<string, unknown>;  // status, size, duration, stack...
}
```

`current.json` also holds the run metadata (`tool`, `version`, `project`, `url`, `date`, `pages`, `viewports`,
`checks`, `errors`, `summary`) and, from the second run on, a `comparison` block with the fingerprints of fixed,
new and unchanged findings.

### What audit_project checks

| Category | Rules (severity) |
|---|---|
| console | uncaught exception (critical), unhandled promise rejection (warning), `console.error` (warning); stack and source file:line, repeats counted |
| network | API 5xx (critical), API 4xx (warning, except 401/403 on a login page), JS/CSS failed (critical), image/font failed (warning), request failed (warning), request over 1 s / 3 s (notice / warning) |
| seo | missing or empty title, missing meta description, missing `lang`, no `<h1>` (warning); several `<h1>`, skipped heading levels, no canonical, no favicon, no Open Graph, no robots.txt / sitemap.xml (notice) |
| images | image did not load, missing `alt` (warning); file over 200 KB / 1 MB (notice / warning); natural size over 2× the displayed size (notice) |
| accessibility | [axe-core](https://github.com/dequelabs/axe-core) WCAG 2.x A/AA rules (critical / serious / moderate+minor → critical / warning / notice); `onclick` elements unreachable by keyboard, no visible focus on Tab (warning) |
| layout | horizontal scroll with the deepest element past the edge (warning), text clipped by `overflow: hidden` (notice), tap targets under 24×24 px at 375 px (notice); every viewport |
| fonts | `@font-face` font failed to load (warning), text shown in a fallback because the declared font never loaded (notice) |
| performance | load over 3 s, LCP over 2.5 / 4 s, CLS over 0.1 / 0.25, page over 3 MB, over 100 requests, JS file over 500 KB, CSS file over 150 KB; thresholds in [thresholds.py](codecheck_mcp/audit/thresholds.py) |
| interaction | clicks up to 20 buttons, `href="#"` / `javascript:` links and `role="button"` per page on a fresh load and watches 2 s for navigation, URL change, requests, DOM changes, dialogs, new tabs; skips logout / delete; critical for `criticalSelectors`. A critical selector that was never clicked is reported too: critical if it matched no element on any page, warning if it was hidden, invalid, destructive or past the click limit |
| security | plain HTTP (not localhost), mixed content (warning); no CSP, no `nosniff`, no HSTS (notice); cookies without `Secure` or session cookies without `HttpOnly` (warning); public source maps (notice) |

If axe and another check find the same thing (for example a missing `alt` or `lang`), it is reported once.

## Try it on the demo shop

[examples/demo-shop](examples/demo-shop) is a small site with one deliberate bug per page (script errors, a broken
image and script, an API that answers 500, horizontal scroll on phones, a dead checkout button, a page without a
title) and a clean home page.

```bash
python examples/demo-shop/serve.py 8765
# then ask your agent: run audit_project on http://127.0.0.1:8765/ with criticalSelectors ["#checkout"]
```

## Architecture

```text
codecheck_mcp/
  server.py                 MCP tools
  browser.py                Playwright launch, local server for folders, external-domain blocking
  checks/                   checks of the quick tools (full_qa, test_*)
  audit/
    runner.py               audit_project: crawl, run checks per viewport, merge duplicates, write reports
    thresholds.py           every threshold in one place
    core/                   finding, fingerprint, selector, screenshot, crawler, session (events per page)
    checks/                 one module per category; each has run(page, ctx) -> list[Finding]
    report/                 json_report, markdown, diff
  vendor/axe.min.js         axe-core 4.13.0, unmodified (MPL-2.0)
```

Every page is loaded once per viewport; console and network events are recorded before the page starts loading,
then each check reads the same page. Checks are registered in `audit/checks/__init__.py`.

## Safety of the server itself

- Read-only: the project under test is never modified.
- Pages open in an isolated browser context, without your cookies or sessions.
- Navigation to other domains is blocked; `audit_project` does not fill in or submit forms with data and skips
  buttons that look like logout or delete.
- Security checks are passive: they read headers, cookies and public files, and never attack the site.
- Secrets found by `quick_security` are masked in reports.
- Test only your own projects, or sites you have the owner's permission to test.

## Known limitations

- A full `audit_project` takes about 30 s for a small site; pages with many dead buttons take longer (up to 2 s per
  click). Lower `maxPages` or narrow `checks` for large sites.
- Console, network, SEO, images, fonts, accessibility, performance and security run at the widest viewport only;
  layout runs at every viewport.
- Server headers and cookies are not checked for a local folder (they come from the temporary server, not from
  your project).
- Only the `onclick` attribute is seen, not listeners added with `addEventListener`.
- Sizes are transferred bytes: a local folder is served without compression, so real hosting may be lighter.
- The comparison is with the previous run in the same output folder only.

## Roadmap

- Optional session setup (cookies or a login script) to audit pages behind a login.
- Check console and network at every viewport.
- A `max duration` limit for very large sites.
- Test on macOS and Linux.

## Development

```bash
pip install -e ".[dev]"
python -m playwright install chromium
pytest tests -q
ruff check codecheck_mcp tests
mypy codecheck_mcp
```

The tests use pages with deliberate bugs, clean pages that must produce no findings, and regressions found on real
sites. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE). `codecheck_mcp/vendor/axe.min.js` is [axe-core](https://github.com/dequelabs/axe-core)
by Deque Systems, MPL-2.0, see [codecheck_mcp/vendor](codecheck_mcp/vendor).
