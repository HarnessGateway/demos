"""The HarnessGateway API, as an application uses it: a key that can only run turns, one session per thing the app
tracks (a chat, a story, a campaign), turns in the background, the agent's work read back through the Containers
API. Everything here is the OpenAI Responses, Files and Containers APIs, unchanged; the standard library is enough.

    hg = HG.from_env(Path(__file__).parent)        # HG_API, HG_KEY, HG_MODEL from the app's .env or the environment
    turn = hg.start("Research Acme", user="ana", previous=last_response_id, metadata={"account": "acme"})
    ...later: hg.response(turn["id"]) until its status is final; hg.folder(hg.session(turn), "accounts/acme")
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FINAL = ("completed", "incomplete", "failed", "cancelled")


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:300]}")
        self.status, self.body = status, body


def dotenv(folder: Path) -> dict[str, str]:
    """KEY=value lines of `.env` in the folder (what scripts/setup.py writes), under the process environment."""
    out: dict[str, str] = {}
    f = folder / ".env"
    if f.is_file():
        for line in f.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                out[k] = v
    return {**out, **{k: v for k, v in os.environ.items() if k.startswith("HG_")}}


class HG:
    def __init__(self, api: str, key: str, model: str):
        self.api, self.key, self.model = api.rstrip("/"), key, model

    @classmethod
    def from_env(cls, folder: Path, default_model: str) -> HG:
        env = dotenv(folder)
        if not env.get("HG_KEY"):
            raise SystemExit(f"no HG_KEY: run scripts/setup.py, or put HG_API and HG_KEY in {folder / '.env'}")
        return cls(env.get("HG_API", "http://127.0.0.1:8000"), env["HG_KEY"], env.get("HG_MODEL", default_model))

    # ── calls ──────────────────────────────────────────────────────────────────────────────────────────────────────
    def call(self, method: str, path: str, body: dict[str, Any] | None = None, raw: bool = False,
             timeout: int = 120) -> Any:
        req = urllib.request.Request(self.api + "/v1" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"authorization": f"Bearer {self.key}", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, e.read().decode(errors="replace")) from None
        return data if raw else json.loads(data)

    # ── turns ──────────────────────────────────────────────────────────────────────────────────────────────────────
    def start(self, prompt: str, *, user: str, previous: str | None = None, metadata: dict[str, str] | None = None,
              instructions: str | None = None, files: dict[str, tuple[str, bytes]] | None = None) -> dict[str, Any]:
        """A background turn: the Response in its queued state. `files` are sent inline with the prompt as
        input_file parts ({filename: (media type, bytes)}); the agent finds them under inputs/ in its work folder."""
        content: Any = prompt
        if files:
            content = [{"role": "user", "content": [{"type": "input_text", "text": prompt}, *(
                {"type": "input_file", "filename": name,
                 "file_data": f"data:{kind};base64," + base64.b64encode(data).decode()}
                for name, (kind, data) in files.items())]}]
        body: dict[str, Any] = {"model": self.model, "input": content, "background": True, "user": user[:256]}
        if previous:
            body["previous_response_id"] = previous
        if metadata:
            body["metadata"] = metadata
        if instructions:
            body["instructions"] = instructions
        return self.call("POST", "/responses", body)

    def response(self, rid: str) -> dict[str, Any]:
        return self.call("GET", f"/responses/{rid}")

    def watch(self, rid: str, on_items: Any) -> None:
        """A thread that follows a running turn's events (GET with stream=true) and calls on_items(items) with every
        output item finished so far, each time one finishes: what the page shows of the agent's work while it works.
        The response's final state is still read with response(); this only shows progress."""
        def follow() -> None:
            items: list[dict[str, Any]] = []
            req = urllib.request.Request(f"{self.api}/v1/responses/{rid}?stream=true",
                                         headers={"authorization": f"Bearer {self.key}", "accept": "text/event-stream"})
            try:
                with urllib.request.urlopen(req, timeout=1800) as r:
                    for raw in r:
                        line = raw.decode(errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            ev = json.loads(line[5:])
                        except json.JSONDecodeError:
                            continue
                        if ev.get("type") == "response.output_item.done":
                            items.append(ev["item"])
                            on_items(list(items))
                        elif ev.get("type") in ("response.completed", "response.failed", "response.incomplete"):
                            return
            except Exception:
                return                                        # progress only: the poller still settles the turn
        threading.Thread(target=follow, daemon=True).start()

    def cancel(self, rid: str) -> dict[str, Any]:
        return self.call("POST", f"/responses/{rid}/cancel")

    @staticmethod
    def text(response: dict[str, Any]) -> str:
        """The assistant's prose in a Response."""
        return "\n\n".join(t for item in response.get("output", []) if item.get("type") == "message"
                           for c in item.get("content", []) if (t := c.get("text", "").strip()))

    @staticmethod
    def steps(response: dict[str, Any]) -> list[dict[str, Any]]:
        """What the agent did, as the page lists it: commands, file changes, tool calls."""
        out = []
        for item in response.get("output", []):
            kind = item.get("type")
            if kind == "shell_call":
                out.append({"kind": "ran", "text": " && ".join((item.get("action") or {}).get("commands", []))})
            elif kind == "apply_patch_call":
                op = item.get("operation") or {}
                verb = {"create_file": "wrote", "update_file": "edited", "delete_file": "deleted"}.get(op.get("type"), "changed")
                out.append({"kind": verb, "text": op.get("path", "")})
            elif kind in ("custom_tool_call", "mcp_call"):
                out.append({"kind": "used", "text": item.get("name") or kind})
        return out

    # ── the agent's work ───────────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def session(response: dict[str, Any]) -> str:
        """The session a response belongs to: what the app keeps to read the agent's work later."""
        return (response.get("metadata") or {}).get("hg_session", "")

    @staticmethod
    def _container(sid: str) -> str:
        """A session's work folder as the Containers API names it."""
        return "cntr_" + sid.removeprefix("sess_")

    def files(self, sid: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        after = None
        while True:
            page = self.call("GET", f"/containers/{self._container(sid)}/files?limit=100"
                             + (f"&after={after}" if after else ""))
            out += page["data"]
            if not page.get("has_more"):
                return out
            after = page["last_id"]

    def folder(self, sid: str, prefix: str) -> list[dict[str, Any]]:
        """The files under a folder of the session's work: {id, path, rel, bytes, at}. A turn's work is saved
        before its response is final, so what a finished turn wrote is always here."""
        prefix = "/work/" + prefix.strip("/") + "/"
        return [{"id": f["id"], "path": f["path"], "rel": f["path"][len(prefix):], "bytes": f["bytes"],
                 "at": f.get("created_at", 0)} for f in self.files(sid) if f["path"].startswith(prefix)]

    def read(self, sid: str, file_id: str) -> bytes:
        return self.call("GET", f"/containers/{self._container(sid)}/files/{file_id}/content", raw=True)

    def read_text(self, sid: str, files: list[dict[str, Any]], rel: str) -> str:
        f = next((f for f in files if f["rel"] == rel), None)
        return self.read(sid, f["id"]).decode(errors="replace") if f else ""
