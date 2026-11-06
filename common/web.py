"""The small web server every demo app is: one page, its JSON routes, the shared static files, and a read-only relay
of workspace files to the page (so the browser never holds the key). Standard library only.

    class Handler(web.App):
        ROUTES = {"GET /app/state": ..., "POST /app/run": ...}      # name -> method(self, body) -> JSON
    web.serve(Handler, port)
"""
from __future__ import annotations

import http.server
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hg import HG, ApiError

COMMON = Path(__file__).resolve().parent
KINDS = {".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".svg": "image/svg+xml"}


class Store:
    """The app's state as one JSON file, written atomically under a lock."""

    def __init__(self, path: Path, empty: dict[str, Any]):
        self.path, self.lock = path, threading.RLock()
        self.data = json.loads(path.read_text()) if path.exists() else empty

    def save(self) -> None:
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1))
            tmp.replace(self.path)


Job = dict[str, Any]


def follow(hg: HG, store: Store, running: Callable[[], list[Job]], ended: Callable[[Job, Job], None], every: float = 4) -> None:
    """A thread: each job `running()` returns is polled; when its response is final, `ended(job, response)` runs."""
    def loop() -> None:
        while True:
            for job in running():
                try:
                    r = hg.response(job["response_id"])
                except Exception:
                    continue
                if r["status"] in ("queued", "in_progress"):
                    continue
                with store.lock:
                    ended(job, r)
                    store.save()
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


class App(http.server.BaseHTTPRequestHandler):
    hg: HG
    store: Store
    here: Path                                  # the app's folder: index.html lives there
    ROUTES: dict[str, str] = {}                 # "GET /app/state" -> method name

    def log_message(self, *a: object) -> None:
        pass

    def send(self, status: int, data: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, doc: Any, status: int = 200) -> None:
        self.send(status, json.dumps(doc).encode(), "application/json")

    def body(self) -> dict[str, Any]:
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def route(self, method: str) -> None:
        path = self.path.split("?")[0]
        name = self.ROUTES.get(f"{method} {path}")
        try:
            if name:
                self.json(getattr(self, name)(self.body() if method == "POST" else {}))
            elif method == "GET" and path.startswith("/ws/"):                      # /ws/<session>/<file id>
                _, _, sid, fid = path.split("/", 3)
                self.send(200, self.hg.read(sid, fid), "application/octet-stream")
            elif method == "GET" and path.startswith("/common/"):
                f = COMMON / Path(path).name
                if f.is_file():
                    self.send(200, f.read_bytes(), KINDS.get(f.suffix, "application/octet-stream"))
                else:
                    self.json({"error": "not found"}, 404)
            elif method == "GET" and path == "/":
                self.send(200, (self.here / "index.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self.json({"error": "not found"}, 404)
        except ApiError as e:
            self.json({"error": e.body[:500]}, 502)
        except (KeyError, ValueError) as e:
            self.json({"error": str(e)}, 400)

    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")


def serve(handler: type[App], port: int, host: str = "127.0.0.1") -> None:
    print(f"http://{host}:{port}  (API {handler.hg.api}, model {handler.hg.model})", flush=True)
    http.server.ThreadingHTTPServer((host, port), handler).serve_forever()
