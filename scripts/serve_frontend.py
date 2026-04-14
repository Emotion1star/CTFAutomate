from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "server" / "frontend" / "site"
HOST = os.environ.get("CTF_FRONTEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("CTF_FRONTEND_PORT", "8080"))


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), FrontendHandler)
    print(f"Frontend server running at http://{HOST}:{PORT}")
    server.serve_forever()
