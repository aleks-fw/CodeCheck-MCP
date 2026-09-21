# Installing CodeCheck MCP (instructions for an AI agent)

Repository: https://github.com/aleks-fw/CodeCheck-MCP
What it is: an MCP server (Python, stdio) that QA-tests a finished web project in a real browser.
Tools: `full_qa`, `test_interactions`, `test_layout`, `test_fonts`, `test_images`, `quick_security`.

Follow these steps in order. Do not skip the confirmations: they involve a large download and a change to the
user's MCP configuration.

1. **Check requirements.** Python 3.10 or newer (`python --version`). Tested only on Windows + Python 3.14.
2. **Ask the user where to install** (a folder for the virtual environment). Respect any rule the user gave about
   drives or directories. The install needs roughly 500 MB (Python packages plus Chromium).
3. **Create a virtual environment and install from GitHub:**
   ```
   python -m venv <ENV_DIR>
   <ENV_DIR>/Scripts/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git      # Windows
   <ENV_DIR>/bin/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git          # macOS / Linux
   ```
4. **Download the browser (once, about 150 MB).** Tell the user before you do it:
   ```
   <ENV_DIR>/Scripts/python -m playwright install chromium
   ```
   If the user wants the browser in a specific folder, set `PLAYWRIGHT_BROWSERS_PATH` for this command AND add the
   same variable to the MCP server's `env` in step 5.
5. **Register the server** with the user's MCP client, after the user confirms the config change.
   The command is the absolute path to `<ENV_DIR>/Scripts/codecheck-mcp` (`.exe` on Windows), no arguments.
   - Claude Code: `claude mcp add --scope user codecheck -- "<ABSOLUTE_PATH>/codecheck-mcp"`
   - Other clients (JSON): `{"mcpServers": {"codecheck": {"command": "<ABSOLUTE_PATH>/codecheck-mcp"}}}`
   - Optional env vars: `CODECHECK_REPORTS_DIR` (where `report.md` files go, default `~/codecheck-reports`),
     `PLAYWRIGHT_BROWSERS_PATH`.
6. **Verify.** Restart or reload the MCP client, confirm the server `codecheck` is connected and lists the six
   tools. A first call such as `test_fonts` with a local project folder is a good smoke test.
   If a tool answers "Chromium ... не установлен", step 4 was not done for the same browser path.

Usage rules: only test projects the user owns or has permission to test. The server is read-only for the checked
project, blocks navigation to external domains, and masks secrets in reports.
