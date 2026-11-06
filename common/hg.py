"""The HarnessGateway API, as an application uses it: a run-only key named after the app, one session per thing the
app tracks (an account, an engagement, a desk thread), turns in the background, the workspace read back through the
Containers API. Standard library only.

    hg = HG.from_env(Path(__file__).parent)        # HG_API, HG_KEY, HG_MODEL from the app's .env or the environment
    turn = hg.start("Research Acme", user="ana", previous=last_response_id, metadata={"account": "acme"})
    ...later: hg.response(turn["id"]) until its status is final; hg.folder(session_id, "/workspace/accounts/acme")
"""
from __future__ import annotations

import json
import os
import time
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
              instructions: str | None = None) -> dict[str, Any]:
        """A background turn: the Response in its queued state, with id and metadata.session_id."""
        body: dict[str, Any] = {"model": self.model, "input": prompt, "background": True, "user": user[:256]}
        if previous:
            body["previous_response_id"] = previous
        if metadata:
            body["metadata"] = metadata
        if instructions:
            body["instructions"] = instructions
        return self.call("POST", "/responses", body)

    def response(self, rid: str) -> dict[str, Any]:
        return self.call("GET", f"/responses/{rid}")

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
            elif kind in ("function_call", "mcp_call", "web_search_call"):
                out.append({"kind": "used", "text": item.get("name") or kind})
        return out

    # ── the workspace ──────────────────────────────────────────────────────────────────────────────────────────────
    def container(self, sid: str) -> dict[str, Any]:
        return self.call("GET", f"/containers/{sid}")

    def settle(self, sid: str, timeout_s: float = 120) -> None:
        """Until the session's state is saved: a turn ends before its process exits and its workspace is saved."""
        deadline = time.time() + timeout_s
        while time.time() < deadline and self.container(sid)["metadata"].get("state") != "idle":
            time.sleep(2)

    def files(self, sid: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        after = None
        while True:
            page = self.call("GET", f"/containers/{sid}/files?limit=100" + (f"&after={after}" if after else ""))
            out += page["data"]
            if not page.get("has_more"):
                return out
            after = page["last_id"]

    def folder(self, sid: str, prefix: str) -> list[dict[str, Any]]:
        """The files under a workspace folder: {id, path, rel, bytes, at}."""
        prefix = prefix.rstrip("/") + "/"
        return [{"id": f["id"], "path": f["path"], "rel": f["path"][len(prefix):], "bytes": f["bytes"],
                 "at": f.get("created_at", 0)} for f in self.files(sid) if f["path"].startswith(prefix)]

    def read(self, sid: str, file_id: str) -> bytes:
        return self.call("GET", f"/containers/{sid}/files/{file_id}/content", raw=True)

    def read_text(self, sid: str, files: list[dict[str, Any]], rel: str) -> str:
        f = next((f for f in files if f["rel"] == rel), None)
        return self.read(sid, f["id"]).decode(errors="replace") if f else ""
