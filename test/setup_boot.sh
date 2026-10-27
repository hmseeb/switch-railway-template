#!/usr/bin/env bash
# Contract test for setup_boot.py inside the pinned setup image, against a stub
# Mattermost: the closed-signup refusal on user creation becomes 409, any other
# 403 is left alone.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=${SWITCH_VERSION:-$(python3 -c 'import json;print(json.load(open("template.json"))["services"]["setup"]["source"]["image"].split(":")[-1])')}
docker run --rm -v "$PWD/setup_boot.py:/shim/setup_boot.py:ro" "ghcr.io/sandbox-quantum/setup:$VERSION" python -c '
import http.server, json, sys, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = {"id": "api.user.create_user.no_open_server"} if self.path == "/api/v4/users" else {"id": "api.context.permissions"}
        data = json.dumps(body).encode()
        self.send_response(403); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *a): pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=s.serve_forever, daemon=True).start()
sys.path.insert(0, "/shim"); import setup_boot, httpx
c = httpx.Client(base_url=f"http://127.0.0.1:{s.server_port}")
a = c.post("/api/v4/users", json={}).status_code
b = c.post("/api/v4/teams", json={}).status_code
assert (a, b) == (409, 403), (a, b)
print("PASS")
'
