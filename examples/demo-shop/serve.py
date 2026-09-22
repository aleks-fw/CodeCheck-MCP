"""Demo server for CodeCheck: serves ./site and a broken API endpoint.

    python serve.py            # http://127.0.0.1:8000/
    python serve.py 8080       # another port

GET /api/orders always answers HTTP 500, like a backend with a bug.
"""
import functools
import http.server
import sys
from pathlib import Path

SITE = Path(__file__).parent / "site"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/orders"):
            body = b'{"error": "database connection failed"}'
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(SITE)))
    print(f"Demo shop: http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
