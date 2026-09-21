import base64
import functools
import http.server
import json
import os
import subprocess
import threading

from PIL import Image

from codecheck_mcp.browser import run
from codecheck_mcp.checks.images import check_images
from codecheck_mcp.checks.security import check_security, find_secrets, mask

PAGE = "<!doctype html><html lang=ru><head><meta charset=utf-8><title>t</title></head><body>{}</body></html>"


def img_msgs(rep):
    return [f.message for f in rep.findings if f.check == "images"]


def sec_msgs(rep):
    return [f.message for f in rep.findings if f.check == "security"]


def make_png(path, size, noise=False):
    img = Image.new("RGB", size, (200, 120, 60))
    if noise:
        img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    img.save(path)


# ---------- изображения ----------

def test_clean_images_have_no_findings(tmp_path):
    make_png(tmp_path / "ok.png", (800, 400))
    (tmp_path / "index.html").write_text(PAGE.format('<img src="ok.png" width="400" height="200" alt="Блюдо">'),
                                         encoding="utf-8")
    rep = run(str(tmp_path), [check_images], max_pages=1)
    assert img_msgs(rep) == [], img_msgs(rep)


def test_image_bugs_are_found(tmp_path):
    make_png(tmp_path / "small.png", (40, 40))
    make_png(tmp_path / "wide.png", (200, 100))
    make_png(tmp_path / "heavy.png", (500, 500), noise=True)
    body = (
        '<img src="missing.png" width="100" height="100" alt="нет файла">'
        '<img src="small.png" width="400" height="40" alt="мелкая и растянутая">'
        '<img src="wide.png" width="200" height="200" alt="сплюснутая">'
        '<img src="heavy.png" width="100" height="100" alt="тяжёлая">'
        '<img src="wide.png" width="200" height="100">'
    )
    (tmp_path / "index.html").write_text(PAGE.format(body), encoding="utf-8")
    m = img_msgs(run(str(tmp_path), [check_images], max_pages=1))
    assert any("не загрузилась" in x and "missing.png" in x for x in m), m
    assert any("растянута или сплющена" in x and "small.png" in x for x in m), m
    assert any("растянута или сплющена" in x and "wide.png" in x for x in m), m
    assert any("мыльная" in x and "small.png" in x for x in m), m
    assert any("Тяжёлая" in x and "heavy.png" in x for x in m), m
    assert any("нет атрибута alt" in x for x in m), m


# ---------- секреты ----------

TG_TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456_-"[:35]
SERVICE_JWT = ".".join([
    base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("="),
    base64.urlsafe_b64encode(json.dumps({"role": "service_role", "iss": "supabase"}).encode()).decode().rstrip("="),
    "c2lnbmF0dXJlLXNpZ25hdHVyZS1zaWduYXR1cmU",
])


def test_find_secrets_detects_and_ignores_placeholders():
    text = f'TOKEN = "{TG_TOKEN}"\nKEY = "{SERVICE_JWT}"\npassword = "your_password_here"\nx = os.environ["TOKEN"]'
    names = [n for n, _, _ in find_secrets(text)]
    assert any("Telegram" in n for n in names), names
    assert any("service_role" in n for n in names), names
    values = [v for _, _, v in find_secrets(text)]
    assert all("your_password" not in v for v in values), values  # заглушка не считается секретом
    assert all("environ" not in v for v in values), values         # чтение из окружения тоже


def test_mask_hides_value():
    m = mask(TG_TOKEN)
    assert TG_TOKEN not in m and m.startswith("1234")


def test_project_secrets_and_git_history(tmp_path):
    def git(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True,
                       capture_output=True)
    git("init")
    (tmp_path / "old.py").write_text(f'BOT = "{TG_TOKEN}"\n', encoding="utf-8")
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "init")
    (tmp_path / "old.py").write_text("BOT = None\n", encoding="utf-8")  # секрет убрали, но он в истории
    (tmp_path / "index.html").write_text(PAGE.format(f"<script>var k='{SERVICE_JWT}'</script><p>hi</p>"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "fix")
    rep = run(str(tmp_path), [check_security], max_pages=1)
    m = sec_msgs(rep)
    assert any("service_role" in x and "index.html" in x for x in m), m
    assert any("Секретный файл под контролем git: .env" in x for x in m), m
    assert any("остался в истории git" in x and "Telegram" in x for x in m), m
    assert any("нет .gitignore" in x for x in m), m
    # значение секрета целиком в отчёте быть не должно
    assert not any(TG_TOKEN in x or SERVICE_JWT in x for x in m), m


def test_clean_project_has_no_secret_findings(tmp_path):
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / "index.html").write_text(PAGE.format("<p>hi</p>"), encoding="utf-8")
    (tmp_path / "app.py").write_text('import os\nTOKEN = os.environ["BOT_TOKEN"]\n', encoding="utf-8")
    assert sec_msgs(run(str(tmp_path), [check_security], max_pages=1)) == []


# ---------- заголовки ----------

def serve(directory, headers):
    class H(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            for k, v in headers.items():
                self.send_header(k, v)
            super().end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_headers_missing_and_present(tmp_path):
    (tmp_path / "index.html").write_text(PAGE.format("<p>hi</p>"), encoding="utf-8")
    bare = serve(tmp_path, {})
    good = serve(tmp_path, {"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
                            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
    try:
        m = sec_msgs(run(f"http://127.0.0.1:{bare.server_address[1]}/index.html", [check_security],
                         max_pages=1, headers_on_local=True))
        assert any("Content-Security-Policy" in x for x in m), m
        assert any("X-Content-Type-Options" in x for x in m), m
        assert any("Referrer-Policy" in x for x in m), m
        m = sec_msgs(run(f"http://127.0.0.1:{good.server_address[1]}/index.html", [check_security],
                         max_pages=1, headers_on_local=True))
        # у «хорошего» сервера остаётся только HTTP (localhost) и, возможно, cookies; заголовки в порядке
        assert not any("Content-Security-Policy" in x or "X-Content-Type" in x or "Referrer" in x for x in m), m
    finally:
        bare.shutdown()
        good.shutdown()
