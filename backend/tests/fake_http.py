"""A local fake HTTP server for the real Feeds adapter's tests (B03): no test calls the network.

A test sets a handler per path; each request is recorded (method, path, query, JSON body, headers, the fake time
the test's clock shows). A handler returns `(status, body)` or `(status, body, delay_seconds)`.
"""
import json
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Seen:
    method: str
    path: str
    query: dict[str, str]
    body: dict | None
    headers: dict[str, str]
    at: float | None = None  # the fake clock when the request arrived, if the server has one


Handler = Callable[[Seen], tuple]


@dataclass
class FakeHttp:
    routes: dict[str, Handler] = field(default_factory=dict)
    seen: list[Seen] = field(default_factory=list)
    clock: Callable[[], float] | None = None
    url: str = ""

    def on(self, path: str, handler: Handler) -> None:
        self.routes[path] = handler

    def hits(self, path: str) -> list[Seen]:
        return [s for s in self.seen if s.path == path]


def start(fake: FakeHttp) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _serve(self, method: str):
            parts = urllib.parse.urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            seen = Seen(method, parts.path, dict(urllib.parse.parse_qsl(parts.query)),
                        json.loads(raw) if raw else None, {k.lower(): v for k, v in self.headers.items()},
                        fake.clock() if fake.clock else None)
            fake.seen.append(seen)
            handler = fake.routes.get(parts.path)
            status, body, *delay = handler(seen) if handler else (404, {"error": "no route"})
            if delay:
                time.sleep(delay[0])  # allowed: a slow server, to test the client's timeout
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):  # the client gave up (a timeout test)
                pass

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return server
