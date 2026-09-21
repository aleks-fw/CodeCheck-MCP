"""Лёгкая проверка безопасности: секреты в файлах и истории git, заголовки, cookies, mixed content."""
from __future__ import annotations

import base64
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from browser import new_page
from report import Report

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "browsers", "reports", ".tmp", ".pipcache",
             "dist", "build", ".next"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".otf", ".eot",
            ".pdf", ".zip", ".gz", ".mp4", ".mp3", ".webm", ".exe", ".dll", ".pyc", ".lock", ".map"}
MAX_FILE_BYTES = 1_000_000
PLACEHOLDER = re.compile(r"(your[_-]?|xxx|example|changeme|placeholder|<.*>|\[.*\]|\*{3,}|dummy|test|sample|todo)", re.I)

# (название, regex, severity)
RULES = [
    ("Токен Telegram-бота", re.compile(r"(?<![\w])\d{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"), "critical"),
    ("Приватный ключ", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"), "critical"),
    ("Ключ доступа AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "critical"),
    ("Токен GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "critical"),
    ("Строка подключения к БД с паролем", re.compile(r"postgres(?:ql)?://[^:\s/]+:([^@\s]{4,})@"), "high"),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "medium"),
    ("Секрет в присваивании", re.compile(
        r"(?i)\b(?:api[_-]?hash|api[_-]?key|secret|passwd|password|token|access[_-]?key)\w*\s*[=:]\s*[\"']([^\"'\s]{12,})[\"']"),
     "high"),
]


def mask(value: str) -> str:
    return value[:4] + "…" + value[-2:] if len(value) > 8 else "…"


def _entropy(s: str) -> float:
    c = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in c.values())


def _jwt_role(token: str) -> str:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role", "")
    except Exception:
        return ""


def find_secrets(text: str):
    """Возвращает [(название, severity, значение)] для найденных в тексте секретов."""
    found = []
    for name, rx, sev in RULES:
        for m in rx.finditer(text):
            value = m.group(1) if rx.groups else m.group(0)
            if PLACEHOLDER.search(value) or "os.environ" in m.group(0) or "getenv" in m.group(0):
                continue
            if name == "Секрет в присваивании" and _entropy(value) < 3.0:
                continue
            if name == "JWT":
                role = _jwt_role(m.group(0))
                if role == "service_role":
                    name, sev = "JWT Supabase с ролью service_role (даёт полный доступ к базе)", "critical"
                else:
                    name = f"JWT (роль «{role or '?'}»; anon-ключ публичный, но проверь, что он не приватный)"
            found.append((name, sev, value))
    return found


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file() and p.suffix.lower() not in SKIP_EXT:
            try:
                if p.stat().st_size <= MAX_FILE_BYTES:
                    yield p
            except OSError:
                continue


def _git(root: Path, *args, limit=5_000_000) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60)
        return r.stdout[:limit].decode("utf-8", "replace") if r.returncode == 0 else None
    except Exception:
        return None


def scan_secrets(root: Path, report: Report) -> None:
    seen: set[str] = set()
    for p in _iter_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(root))
        in_file: set[str] = set()
        for name, sev, value in find_secrets(text):
            if value in in_file:  # одно значение, пойманное двумя правилами, показываем один раз
                continue
            in_file.add(value)
            seen.add(value)
            line = text[: text.find(value)].count("\n") + 1
            report.add("security", sev, f"{name} в файле {rel}:{line}: {mask(value)}", selector=rel)

    is_git = (root / ".git").exists()
    if not (root / ".gitignore").exists():
        report.add("security", "low", "В проекте нет .gitignore: легко закоммитить .env, ключи и мусор", selector=".gitignore")
    if is_git:
        tracked = (_git(root, "ls-files") or "").splitlines()
        for f in tracked:
            name = Path(f).name.lower()
            if name == ".env" or (name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))) \
                    or name.endswith((".pem", ".key")) or name in ("id_rsa", "id_ed25519"):
                report.add("security", "high", f"Секретный файл под контролем git: {f}", selector=f)
        # секреты, которые удалили из файлов, но они остались в истории
        log = _git(root, "log", "--all", "-p", "-U0", "--no-color", "--max-count=300")
        commit = ""
        for line in (log or "").splitlines():
            if line.startswith("commit "):
                commit = line.split()[1][:8]
            elif line.startswith("+") and not line.startswith("+++"):
                for name, sev, value in find_secrets(line[1:]):
                    if value not in seen:
                        seen.add(value)
                        report.add("security", sev,
                                   f"{name} удалён из файлов, но остался в истории git (коммит {commit}): "
                                   f"{mask(value)}. Считай его скомпрометированным и перевыпусти", selector=commit)


def check_headers(browser, url: str, report: Report) -> None:
    u = urlparse(url)
    ctx, page = new_page(browser, report, url)
    try:
        http_requests = []
        page.on("request", lambda r: http_requests.append(r.url) if r.url.startswith("http://") else None)
        resp = page.goto(url, wait_until="load")
        page.wait_for_timeout(300)
        if not resp:
            return
        h = {k.lower(): v for k, v in resp.headers.items()}
        https = u.scheme == "https"
        if not https:
            report.add("security", "high", "Сайт открывается по HTTP без шифрования", page=url)
        csp = h.get("content-security-policy", "")
        if not csp:
            report.add("security", "medium", "Нет заголовка Content-Security-Policy (защита от XSS)", page=url)
        if https and "strict-transport-security" not in h:
            report.add("security", "medium", "Нет заголовка Strict-Transport-Security (HSTS)", page=url)
        if "x-frame-options" not in h and "frame-ancestors" not in csp:
            report.add("security", "low", "Нет защиты от встраивания в iframe (X-Frame-Options / frame-ancestors)", page=url)
        if h.get("x-content-type-options", "").lower() != "nosniff":
            report.add("security", "low", "Нет заголовка X-Content-Type-Options: nosniff", page=url)
        if "referrer-policy" not in h:
            report.add("security", "low", "Нет заголовка Referrer-Policy", page=url)
        if https:
            for r in sorted(set(http_requests))[:5]:
                report.add("security", "high", f"Mixed content: HTTPS-страница грузит ресурс по HTTP: {r[:120]}", page=url)
        for c in ctx.cookies():
            problems = []
            if https and not c.get("secure"):
                problems.append("без флага Secure")
            if not c.get("httpOnly"):
                problems.append("без HttpOnly")
            if c.get("sameSite", "None") == "None" and not c.get("secure"):
                problems.append("SameSite=None без Secure")
            if problems:
                report.add("security", "low", f"Cookie «{c['name']}» {', '.join(problems)}", page=url)
    finally:
        ctx.close()


def check_security(browser, url, report, source_dir=None, headers_on_local=False, **_):
    """Секреты проверяются один раз на проект; заголовки только у реальных сайтов (у localhost их нет смысла ждать)."""
    if source_dir and report.first_time("secrets"):
        scan_secrets(Path(source_dir), report)
    local = urlparse(url).hostname in ("127.0.0.1", "localhost")
    if headers_on_local or not local:
        check_headers(browser, url, report)
