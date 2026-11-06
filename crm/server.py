"""A small CRM with a sales agent in it: accounts, contacts, deals and notes here; research, outreach drafts, call plans
and next steps from the agent, the `sales-codex` harness package on HarnessGateway. The agent never sends anything:
a person approves a draft here, and the CRM records it (this demo's outbox stands in for the mail server).

One session per account, so the agent's workspace (/workspace/accounts/<slug>/) and memory carry from task to task;
the rep's name goes with every request as `user`, so the platform's sessions and usage show who asked.

    python3 server.py [--port 8900]        # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import web  # noqa: E402
from hg import HG  # noqa: E402

DEFAULT_MODEL = "sales-codex/deepseek-openai/deepseek-v4-pro"
TASKS = {
    "brief": "Research {name} ({website}) on the public web and write the account brief to brief.md: what the company "
             "does, size and footprint, recent news, the pains an operations team there likely has, where our products fit, "
             "and three talking points. Answer with a short summary of what you found.",
    "outreach": "Draft an outreach email to {contact} at {name} about: {topic}. Save it as outreach/{date}-{slug_topic}.md "
                "with a `Subject:` line first, under 150 words, specific to their business and to what the brief says. "
                "Answer with the draft.",
    "call-prep": "Prepare the plan for the next call with {name}: agenda, five discovery questions, the objections we are "
                 "likely to hear and how to answer them. Save call-prep.md and summarize it.",
    "next-steps": "Read the account record and the notes and propose the next steps for each open deal, with owners and "
                  "dates. Save next-steps.md and summarize it.",
    "ask": "{prompt}",
}
SEED = [
    {"name": "Acme Logistics", "website": "https://www.acme-logistics.example", "industry": "Freight and 3PL",
     "size": "1,200 employees",
     "contacts": [{"name": "Dana Whitfield", "title": "VP Operations", "email": "dana@acme-logistics.example"},
                  {"name": "Luis Ortega", "title": "Director of Warehousing", "email": "luis@acme-logistics.example"}],
     "deals": [{"name": "Warehouse visibility pilot", "stage": "Discovery", "value": 48000, "close": "2026-12-15"}],
     "notes": [{"by": "Ana", "text": "Met Dana at the supply-chain summit; frustrated with dock scheduling spreadsheets."}]},
    {"name": "Northwind Clinics", "website": "https://www.northwindclinics.example", "industry": "Outpatient healthcare",
     "size": "34 clinics",
     "contacts": [{"name": "Priya Natarajan", "title": "COO", "email": "priya@northwindclinics.example"}],
     "deals": [{"name": "Scheduling platform", "stage": "Proposal", "value": 120000, "close": "2027-01-31"}],
     "notes": [{"by": "Ana", "text": "Proposal sent 10/28; Priya asked for a reference in healthcare."}]},
    {"name": "Harbor Fintech", "website": "https://www.harborfintech.example", "industry": "Payments",
     "size": "Series B, 180 employees",
     "contacts": [{"name": "Marcus Lee", "title": "Head of Operations", "email": "marcus@harborfintech.example"}],
     "deals": [], "notes": []},
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


def account(doc: dict[str, Any]) -> dict[str, Any]:
    """A new account record from what a person typed; the agent's state and the outbox start empty."""
    s = slug(doc["name"])
    return {"id": s, "slug": s, "name": doc["name"], "website": doc.get("website", ""), "industry": doc.get("industry", ""),
            "size": doc.get("size", ""), "contacts": doc.get("contacts", []), "deals": doc.get("deals", []),
            "notes": [{"at": time.time(), **n} for n in doc.get("notes", [])], "outbox": [],
            "agent": {"session_id": None, "last_response": None, "tasks": []}}


class Handler(web.App):
    here = HERE
    ROUTES = {"GET /app/state": "state", "POST /app/account": "new_account", "POST /app/run": "run",
              "POST /app/approve": "approve", "POST /app/note": "note", "POST /app/rep": "rep"}

    def acct(self, b: dict[str, Any]) -> dict[str, Any]:
        return next(a for a in self.store.data["accounts"] if a["id"] == b["account"])

    def state(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            return {"accounts": self.store.data["accounts"], "rep": self.store.data["rep"], "model": self.hg.model,
                    "tasks": TASKS}

    def rep(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            self.store.data["rep"] = str(b.get("rep") or "Ana")[:60]
            self.store.save()
        return {"rep": self.store.data["rep"]}

    def new_account(self, b: dict[str, Any]) -> dict[str, Any]:
        a = account(b)
        with self.store.lock:
            self.store.data["accounts"].insert(0, a)
            self.store.save()
        return a

    def note(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            a = self.acct(b)
            a["notes"].append({"at": time.time(), "by": self.store.data["rep"], "text": str(b["text"])[:4000]})
            self.store.save()
        return a

    def run(self, b: dict[str, Any]) -> dict[str, Any]:
        """One task for the account's agent: a new turn on the account's session, in the background."""
        with self.store.lock:
            a = self.acct(b)
            kind = b.get("kind", "ask")
            topic = str(b.get("topic") or "an introduction")
            ask = TASKS[kind].format(name=a["name"], website=a["website"], contact=b.get("contact", "the main contact"),
                                     topic=topic, slug_topic=slug(topic), date=dt.date.today().isoformat(),
                                     prompt=str(b.get("prompt", "")).strip())
            record = {k: v for k, v in a.items() if k not in ("agent", "outbox", "id", "slug")}
            prompt = (f"{ask}\n\nWork in /workspace/accounts/{a['slug']}/. Never send anything: the CRM does that once "
                      f"a person approves.\n\nAccount record (JSON):\n{json.dumps(record, indent=1)}")
            task = {"id": "task_" + uuid.uuid4().hex[:10], "kind": kind, "ask": ask if kind != "ask" else prompt.split("\n\n")[0],
                    "status": "working", "at": time.time(), "response_id": None, "reply": "", "steps": [], "files": [],
                    "error": None, "approved": None}
            r = self.hg.start(prompt, user=self.store.data["rep"], previous=a["agent"]["last_response"],
                              metadata={"account": a["slug"], "task": kind})
            task["response_id"] = r["id"]
            a["agent"]["session_id"], a["agent"]["last_response"] = r["metadata"]["session_id"], r["id"]
            a["agent"]["tasks"].append(task)
            self.store.save()
        return task

    def approve(self, b: dict[str, Any]) -> dict[str, Any]:
        """A person approves what the agent drafted: an outreach draft goes to the outbox (sent, in this demo), anything
        else becomes a note. Only now does anything leave the agent's workspace."""
        with self.store.lock:
            a = self.acct(b)
            task = next(t for t in a["agent"]["tasks"] if t["id"] == b["task"])
            f = next((f for f in task["files"] if f["rel"] == b.get("file")), None)
            text = self.hg.read(a["agent"]["session_id"], f["id"]).decode(errors="replace") if f else task["reply"]
            if task["kind"] == "outreach":
                subject = next((ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.lower().startswith("subject:")),
                               "(no subject)")
                a["outbox"].append({"at": time.time(), "to": b.get("to", ""), "subject": subject, "body": text,
                                    "by": self.store.data["rep"]})
                a["notes"].append({"at": time.time(), "by": self.store.data["rep"], "text": f"Sent: {subject}"})
            else:
                a["notes"].append({"at": time.time(), "by": f"agent, approved by {self.store.data['rep']}", "text": text[:8000]})
            task["approved"] = time.time()
            self.store.save()
        return a


def ended(task: dict[str, Any], r: dict[str, Any], hg: HG, accounts: list[dict[str, Any]]) -> None:
    a = next(x for x in accounts if any(t is task for t in x["agent"]["tasks"]))
    task["status"] = "done" if r["status"] == "completed" else "failed"
    task["reply"], task["steps"] = hg.text(r), hg.steps(r)
    task["error"] = (r.get("error") or {}).get("message") if r["status"] != "completed" else None
    task["seconds"] = int(time.time() - task["at"])
    sid = a["agent"]["session_id"]
    hg.settle(sid)
    task["files"] = hg.folder(sid, f"/workspace/accounts/{a['slug']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8900)
    args = ap.parse_args()
    Handler.hg = HG.from_env(HERE, DEFAULT_MODEL)
    Handler.store = web.Store(HERE / "data.json", {"accounts": [account(a) for a in SEED], "rep": "Ana"})
    accounts = Handler.store.data["accounts"]
    web.follow(Handler.hg, Handler.store, lambda: [t for a in accounts for t in a["agent"]["tasks"] if t["status"] == "working"],
               lambda task, r: ended(task, r, Handler.hg, accounts))
    web.serve(Handler, args.port)


if __name__ == "__main__":
    main()
