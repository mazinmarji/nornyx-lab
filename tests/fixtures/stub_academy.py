"""A stand-in academy service, just complete enough to drive the B5 harness.

Used by `tests/test_verifier_behaviour.py` to reach step 9 without Docker or the
real image, so the harness's product-failure / verifier-failure classification
can be executed rather than inferred from source.

It is a real file rather than a string embedded in a test, for the same reason
`nornyx_lab.verification.check_counters` is a real module: a program that only
exists inside another program's quoting is a program nothing truly checks.

    python stub_academy.py <demo-run fixture> [port]

`GET /__shutdown` stops it, which is how the test tears it down. Killing it by
pid is not portable — under MSYS `$!` is not a Windows process id, and the
silent failure left a listener that poisoned the next test.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FIXTURE: dict = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # noqa: D102 - quiet test output
        return

    def _send(self, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.endswith("/__shutdown"):
            self._send(b'{"stopping":true}')
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        elif self.path.endswith("/health"):
            self._send(b'{"status":"ok","api_version":"v1"}')
        elif self.path.endswith("/progress"):
            self._send(b'{"modules":[{"module_id":"F0","executions":1}]}')
        else:
            self._send(b'<!doctype html><div id="root"></div>', "text/html")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._send(json.dumps(FIXTURE).encode())


def main() -> int:
    global FIXTURE
    FIXTURE = json.loads(open(sys.argv[1], encoding="utf-8").read())
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    server = HTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
