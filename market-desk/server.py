"""Market Desk: a newsroom desk app on the `journalist-pi` harness package. The app owns the desk's workflow (the
schedule, assignments, review, approval); the agent owns the method (gather, weigh, write with sources); the platform
runs it. Each job is one background turn with `metadata.desk` and `metadata.task`; a revision is a follow-up on the
same response (`previous_response_id`), so the agent revises in the same workspace; the desk's research thread is one
session per desk. The editor's name goes with every request as `user`.

    python3 server.py [--port 8910]        # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import web  # noqa: E402
from hg import HG, ApiError  # noqa: E402

DEFAULT_MODEL = "journalist-pi/deepseek/deepseek-v4-pro"
CONFIG = json.loads((HERE / "config.json").read_text())
TZ = ZoneInfo(CONFIG.get("timezone", "America/New_York"))
TASKS = ["briefing", "data-release", "market-wrap", "explainer", "news-short", "research"]


def now() -> float:
    return time.time()


def today() -> str:
    return dt.datetime.now(TZ).date().isoformat()


def log(job: dict[str, Any], event: str, note: str = "") -> None:
    job["history"].append({"at": now(), "event": event, "note": note})
    job["updated"] = now()


class Desk:
    """The desk's jobs and the agent behind them."""

    def __init__(self, hg: HG, store: web.Store):
        self.hg, self.store = hg, store

    @property
    def jobs(self) -> list[dict[str, Any]]:
        return self.store.data["jobs"]

    def create(self, desk: str, task: str, title: str, prompt: str, kind: str, slot: str | None = None) -> dict[str, Any]:
        job = {"id": "job_" + uuid.uuid4().hex[:12], "desk": desk, "task": task, "title": title, "prompt": prompt, "kind": kind,
               "slot": slot, "day": today(), "status": "queued", "created": now(), "updated": now(), "response_id": None,
               "session_id": None, "folder": None, "files": [], "answer": "", "history": [], "published": None, "error": None}
        log(job, "assigned", prompt)
        with self.store.lock:
            self.jobs.insert(0, job)
            self.store.save()
        previous = self.store.data["threads"].get(desk) if kind == "ask" else None   # the research thread follows itself
        try:
            r = self._start(job, prompt, previous)
        except ApiError:
            if not previous:
                with self.store.lock:
                    job["status"], job["error"] = "failed", "the platform refused the request"
                    self.store.save()
                return job
            r = self._start(job, prompt, None)                                       # a thread that ended: a new one
        with self.store.lock:
            job.update(response_id=r["id"], session_id=r["metadata"]["session_id"], status="drafting", started=now())
            if kind == "ask":
                self.store.data["threads"][desk] = r["id"]
            log(job, "drafting")
            self.store.save()
        return job

    def _start(self, job: dict[str, Any], prompt: str, previous: str | None) -> dict[str, Any]:
        return self.hg.start(prompt, user=self.store.data["editor"], previous=previous,
                             metadata={"desk": job["desk"], "task": job["task"]})

    def send_back(self, job: dict[str, Any], note: str) -> None:
        prompt = (f"Editor's note on your {job['task']} draft in {job['folder']}:\n\n{note}\n\nRevise the draft in place: "
                  "update draft.md, sources.json and verify.md in the same folder, keep every number cited, and say in "
                  "verify.md what changed.")
        r = self._start(job, prompt, job["response_id"])
        with self.store.lock:
            job.update(response_id=r["id"], status="drafting", started=now())
            log(job, "sent back", note)
            self.store.save()

    def approve(self, job: dict[str, Any], checked: int, total: int) -> None:
        text = self.hg.read_text(job["session_id"], job["files"], "draft.md") or job["answer"]
        with self.store.lock:
            job["status"], job["published"] = "approved", {"at": now(), "markdown": text, "verified": f"{checked}/{total}"}
            log(job, "approved", f"{checked} of {total} claims checked")
            self.store.save()

    def ended(self, job: dict[str, Any], r: dict[str, Any]) -> None:
        if r["status"] != "completed":
            job["status"], job["error"] = "failed", (r.get("error") or {}).get("message") or r["status"]
            log(job, "failed", job["error"])
            return
        job["answer"] = self.hg.text(r)
        self.hg.settle(job["session_id"])
        self._collect(job)
        job["status"] = "answered" if job["kind"] == "ask" else "review"
        job["seconds"] = int(now() - job.get("started", job["created"]))
        log(job, "ready for review" if job["kind"] != "ask" else "answered")

    def _collect(self, job: dict[str, Any]) -> None:
        """The job's output folder, /workspace/desk/<date>/<desk>-<slug>/: the newest draft.md written since it started."""
        since = job.get("started", job["created"]) - 5
        mine = [f for f in self.hg.folder(job["session_id"], "/workspace/desk") if f["rel"].count("/") >= 2]
        drafts = [f for f in mine if f["rel"].endswith("/draft.md") and f["rel"].split("/")[1].startswith(job["desk"])]
        fresh = sorted((f for f in drafts if f["at"] >= since), key=lambda f: f["at"]) or sorted(drafts, key=lambda f: f["at"])
        if not fresh:
            return
        folder = "/workspace/desk/" + "/".join(fresh[-1]["rel"].split("/")[:2])
        job["folder"] = folder
        job["files"] = self.hg.folder(job["session_id"], folder)

    # ── the schedule ───────────────────────────────────────────────────────────────────────────────────────────────
    def slots(self) -> list[dict[str, Any]]:
        d = dt.datetime.now(TZ)
        out = []
        for s in CONFIG["schedule"]:
            on_today = not s.get("days") or d.strftime("%a").lower()[:3] in s["days"]
            job = next((j for j in self.jobs if j.get("slot") == s["id"] and j["day"] == today()), None)
            out.append({**s, "today": on_today, "job_id": job["id"] if job else None})
        return out

    def tick(self) -> None:
        while True:
            if self.store.data.get("auto"):
                hm = dt.datetime.now(TZ).strftime("%H:%M")
                for s in self.slots():
                    if s["today"] and not s["job_id"] and s["time"] <= hm:
                        self.create(s["desk"], s["task"], s["title"], s["prompt"], "scheduled", s["id"])
            time.sleep(30)


class Handler(web.App):
    here = HERE
    desk: Desk
    ROUTES = {"GET /app/state": "state", "POST /app/run": "run", "POST /app/start-day": "start_day", "POST /app/auto": "auto",
              "POST /app/editor": "editor", "POST /app/send-back": "send_back", "POST /app/approve": "approve"}

    def job(self, b: dict[str, Any]) -> dict[str, Any]:
        return next(j for j in self.desk.jobs if j["id"] == b["job"])

    def state(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            return {"desks": CONFIG["desks"], "slots": self.desk.slots(), "jobs": self.desk.jobs, "auto": self.store.data["auto"],
                    "editor": self.store.data["editor"], "model": self.hg.model, "today": today(),
                    "now": dt.datetime.now(TZ).strftime("%H:%M")}

    def run(self, b: dict[str, Any]) -> dict[str, Any]:
        if b.get("slot"):
            s = next(s for s in CONFIG["schedule"] if s["id"] == b["slot"])
            return self.desk.create(s["desk"], s["task"], s["title"], s["prompt"], "scheduled", s["id"])
        task = b.get("task", "research")
        if task not in TASKS:
            raise ValueError(f"task is one of {', '.join(TASKS)}")
        return self.desk.create(b["desk"], task, b.get("title") or "Assignment", b["prompt"], b.get("kind", "adhoc"))

    def start_day(self, b: dict[str, Any]) -> list[dict[str, Any]]:
        return [self.desk.create(s["desk"], s["task"], s["title"], s["prompt"], "scheduled", s["id"])
                for s in self.desk.slots() if s["today"] and not s["job_id"] and (not b.get("desk") or s["desk"] == b["desk"])]

    def auto(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            self.store.data["auto"] = bool(b.get("on"))
            self.store.save()
        return {"auto": self.store.data["auto"]}

    def editor(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            self.store.data["editor"] = str(b.get("editor") or "editor")[:60]
            self.store.save()
        return {"editor": self.store.data["editor"]}

    def send_back(self, b: dict[str, Any]) -> dict[str, Any]:
        job = self.job(b)
        self.desk.send_back(job, str(b["note"]))
        return job

    def approve(self, b: dict[str, Any]) -> dict[str, Any]:
        job = self.job(b)
        self.desk.approve(job, int(b.get("checked", 0)), int(b.get("total", 0)))
        return job


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8910)
    a = ap.parse_args()
    Handler.hg = HG.from_env(HERE, DEFAULT_MODEL)
    Handler.store = web.Store(HERE / "data.json", {"jobs": [], "auto": False, "threads": {}, "editor": "editor"})
    Handler.desk = desk = Desk(Handler.hg, Handler.store)
    web.follow(Handler.hg, Handler.store, lambda: [j for j in desk.jobs if j["status"] == "drafting"], desk.ended)
    threading.Thread(target=desk.tick, daemon=True).start()
    web.serve(Handler, a.port)


if __name__ == "__main__":
    main()
