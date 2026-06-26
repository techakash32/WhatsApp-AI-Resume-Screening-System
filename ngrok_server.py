"""
ngrok tunnel + local file server.
Serves generated PDFs via a public ngrok HTTPS URL.

Install:
    pip install pyngrok --break-system-packages
    ngrok config add-authtoken YOUR_TOKEN   # one-time setup

Usage:
    server = NgrokServer(port=8765)
    server.start()
    url = server.get_public_url("/absolute/path/to/report.pdf")
    # → "https://xxxx.ngrok-free.app/report.pdf"
    server.stop()   # call when done / on app shutdown
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote


# ─────────────────────────────────────────────────────────────────────────────

class NgrokServer:
    def __init__(self, serve_dir: str = "output/reports", port: int = 8765):
        self.serve_dir  = os.path.abspath(serve_dir)
        self.port       = port
        self._httpd     = None
        self._thread    = None
        self._tunnel    = None
        self._public_url: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Start local HTTP server + ngrok tunnel. Call once at app startup."""
        Path(self.serve_dir).mkdir(parents=True, exist_ok=True)
        self._start_http()
        self._start_ngrok()

    def stop(self):
        """Tear down tunnel and HTTP server."""
        try:
            if self._tunnel:
                from pyngrok import ngrok
                ngrok.disconnect(self._tunnel.public_url)
        except Exception:
            pass
        if self._httpd:
            self._httpd.shutdown()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_public_url(self, pdf_abs_path: str) -> str:
        """Return the public ngrok URL for a PDF that lives in serve_dir."""
        if not self._public_url:
            raise RuntimeError("NgrokServer not started. Call start() first.")
        filename = Path(pdf_abs_path).name
        return f"{self._public_url}/{filename}"

    @property
    def public_base_url(self) -> str | None:
        return self._public_url

    # ── Internals ─────────────────────────────────────────────────────────────

    def _start_http(self):
        serve_dir = self.serve_dir

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = unquote(self.path.lstrip("/"))
                full = os.path.join(serve_dir, path)
                if os.path.isfile(full) and full.endswith(".pdf"):
                    with open(full, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'inline; filename="{path}"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass  # silence request logs

        self._httpd = HTTPServer(("0.0.0.0", self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def _start_ngrok(self):
        try:
            from pyngrok import ngrok, conf
            # If NGROK_AUTHTOKEN env var is set, pyngrok picks it up automatically
            token = os.environ.get("NGROK_AUTHTOKEN")
            if token:
                conf.get_default().auth_token = token
            self._tunnel = ngrok.connect(self.port, "http")
            self._public_url = self._tunnel.public_url.replace("http://", "https://")
            print(f"  [ngrok] tunnel: {self._public_url}")
        except Exception as e:
            print(f"  [ngrok] ERROR: {e}")
            self._public_url = f"http://localhost:{self.port}"