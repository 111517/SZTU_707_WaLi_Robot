#!/usr/bin/env python3
"""
Go2 Dashboard Static Server + API Proxy
Serves dist/ files and proxies /api/ai/* → OpenClaw Gateways.
Replaces: python3 -m http.server <port>

Proxy routes:
  /api/ai/      → Go2  (<go2-ip>:18789)
  /api/ai-tb4/  → Tb4  (<tb4-ip>:18789)

Env vars:
  OPENCLAW_GO2_URL   — Go2 OpenClaw gateway target
  OPENCLAW_TB4_URL   — Tb4 OpenClaw gateway target
  OPENCLAW_GO2_TOKEN — Go2 OpenClaw token, injected by this proxy
  OPENCLAW_TB4_TOKEN — Tb4 OpenClaw token, injected by this proxy
  AI_PROXY_GO2       — legacy Go2 target override
  AI_PROXY_TB4       — legacy Tb4 target override
  AI_PROXY_TARGET — fallback for /api/ai/ (deprecated, use AI_PROXY_GO2)
"""
import http.server
import urllib.request
import urllib.error
import sys
import os

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path):
    """Load simple KEY=VALUE entries without adding a runtime dependency."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv(os.path.join(REPO_ROOT, ".env"))

GO2_TARGET = os.environ.get(
    "OPENCLAW_GO2_URL",
    os.environ.get(
        "AI_PROXY_GO2",
        os.environ.get("AI_PROXY_TARGET", "http://127.0.0.1:18789"),
    ),
)
TB4_TARGET = os.environ.get(
    "OPENCLAW_TB4_URL",
    os.environ.get("AI_PROXY_TB4", "http://127.0.0.1:18789"),
)
GO2_TOKEN = os.environ.get("OPENCLAW_GO2_TOKEN", "")
TB4_TOKEN = os.environ.get("OPENCLAW_TB4_TOKEN", "")

# prefix → (target, label, token)
PROXY_MAP = {
    "/api/ai/":     (GO2_TARGET, "Go2", GO2_TOKEN),
    "/api/ai-tb4/": (TB4_TARGET, "Tb4", TB4_TOKEN),
}

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
DIR = sys.argv[2] if len(sys.argv) > 2 else "."


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _match_proxy(self):
        """Return (target, label) if path matches a proxy prefix, else None."""
        for prefix, (target, label, token) in PROXY_MAP.items():
            if self.path.startswith(prefix):
                return target, label, token, prefix
        return None

    def _proxy_request(self, method):
        """Forward a request to the matching backend target."""
        match = self._match_proxy()
        if not match:
            self.send_error(501, f"Unsupported method ('{method}')")
            return

        target, _label, token, prefix = match
        target_url = target + self.path[len(prefix) - 1:]
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        try:
            req = urllib.request.Request(target_url, data=body, method=method)
            for key, val in self.headers.items():
                if key.lower() in ("host", "content-length", "connection"):
                    continue
                req.add_header(key, val)
            if token and "Authorization" not in self.headers:
                req.add_header("Authorization", f"Bearer {token}")

            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, val in resp.headers.items():
                    if key.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(key, val)
                self.end_headers()

                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def do_POST(self):
        self._proxy_request("POST")

    def do_GET(self):
        match = self._match_proxy()
        if match:
            self._proxy_request("GET")
        else:
            super().do_GET()

    def do_OPTIONS(self):
        """Handle CORS preflight for proxied requests."""
        if self._match_proxy():
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()
        else:
            super().do_OPTIONS()


httpd = http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler)
print(f"Serving {os.path.abspath(DIR)} on http://0.0.0.0:{PORT}")
for prefix, (target, label, _token) in PROXY_MAP.items():
    print(f"  {prefix} → {target}  ({label})")
httpd.serve_forever()
