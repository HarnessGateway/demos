#!/usr/bin/env python3
"""Market Desk: a commodities newsroom with a journalist agent in it. Editors assign stories (from the release calendar
or by hand) to the biofuels or crude-oil desk; the agent gathers the desk's primary sources, writes a cited draft with
charts and a list of the claims a person must verify; the editor checks each claim, sends the draft back with a note,
approves it or spikes it. Nothing is published from here.

The agent is the `journalist-pi` harness package on HarnessGateway. Each story is one session: its first turn writes the
draft, and a revision continues the same session (previous_response_id), so the agent revises its own files. The agent
ends each answer with one fenced `desk-report` block of JSON naming the folder it wrote; the desk reads draft.md,
sources.json, verify.md and the charts from that folder through the platform's Containers API.

    python3 server.py [--port 8910]    # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)

Data lives in desk.db (SQLite) beside this file. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from hg import FINAL, HG, ApiError, dotenv  # noqa: E402

DB_PATH = HERE / "desk.db"
DEFAULT_MODEL = "journalist-pi/deepseek-anthropic/deepseek-v4-pro"
ET = ZoneInfo("America/New_York")
DESKS = {"biofuels": "Biofuels", "crude-oil": "Crude oil"}
KINDS = ["briefing", "data-release", "market-wrap", "explainer", "news-short", "research"]
STATUSES = ["drafting", "review", "revising", "approved", "spiked", "failed"]
REPORT_RE = re.compile(r"```desk-report[ \t]*\n(.*?)```", re.S)
KINDS_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
                ".md": "text/markdown; charset=utf-8", ".json": "application/json", ".csv": "text/csv; charset=utf-8"}

# The desks' standing schedule. Days are Python weekdays (Monday is 0); times are Eastern.
CALENDAR = [
    {"desk": "biofuels", "kind": "briefing", "days": [0, 1, 2, 3, 4], "time": "06:00", "title": "Morning briefing",
     "brief": "Write the morning briefing for the biofuels desk: what moved in US biofuels markets and policy since the "
              "last business day (RINs, LCFS credits, ethanol, renewable diesel, SAF, feedstocks), and what to watch today."},
    {"desk": "crude-oil", "kind": "briefing", "days": [0, 1, 2, 3, 4], "time": "06:15", "title": "Morning briefing",
     "brief": "Write the morning briefing for the crude oil desk: what moved in US crude supply data and policy since the "
              "last business day, and what to watch today."},
    {"desk": "crude-oil", "kind": "data-release", "days": [2], "time": "10:30", "title": "EIA Weekly Petroleum Status Report",
     "brief": "Write the data-release story on this week's EIA Weekly Petroleum Status Report: commercial crude stocks, "
              "Cushing, domestic production, refinery utilization and net imports, each week over week and against the "
              "five-year average, with a chart of commercial crude stocks."},
    {"desk": "biofuels", "kind": "data-release", "days": [2], "time": "10:30", "title": "EIA weekly ethanol",
     "brief": "Write the data-release story on this week's EIA fuel ethanol production and stocks (from the Weekly "
              "Petroleum Status Report): week over week and year over year, with a chart of production."},
    {"desk": "biofuels", "kind": "market-wrap", "days": [4], "time": "16:00", "title": "Weekly biofuels wrap",
     "brief": "Write the weekly biofuels market wrap: the week's data releases, policy actions in the Federal Register "
              "and from EPA and CARB, and what is scheduled next week."},
    {"desk": "crude-oil", "kind": "market-wrap", "days": [4], "time": "16:15", "title": "Weekly crude wrap",
     "brief": "Write the weekly crude oil wrap: what the week's EIA data showed and what is scheduled next week."},
]
MONTHLY = [
    {"desk": "biofuels", "kind": "data-release", "title": "EPA RIN generation data (EMTS)",
     "brief": "Write the data-release story on EPA's latest monthly RIN generation data: D4, D5 and D6 RINs generated, "
              "against the prior month and the same month last year, with a chart."},
    {"desk": "crude-oil", "kind": "data-release", "title": "EIA Short-Term Energy Outlook",
     "brief": "Write the data-release story on EIA's latest Short-Term Energy Outlook: its US crude production and price "
              "forecasts and what changed from last month's outlook."},
    {"desk": "biofuels", "kind": "explainer", "title": "Policy explainer",
     "brief": "Write an explainer on the most significant US federal or California biofuels policy action of the past "
              "two weeks (RFS, LCFS, 45Z or SAF): what changed, who it affects, and what happens next."},
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, desk TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, brief TEXT NOT NULL,
    status TEXT DEFAULT 'drafting', session_id TEXT DEFAULT '', folder TEXT DEFAULT '', headline TEXT DEFAULT '',
    summary TEXT DEFAULT '', draft TEXT DEFAULT '', sources TEXT DEFAULT '[]', claims TEXT DEFAULT '[]',
    files TEXT DEFAULT '[]', editor_note TEXT DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, note TEXT DEFAULT '', response_id TEXT NOT NULL, status TEXT DEFAULT 'queued',
    answer TEXT DEFAULT '', error TEXT DEFAULT '', steps TEXT DEFAULT '[]', usage TEXT DEFAULT '{}',
    created_at REAL NOT NULL, ended_at REAL);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    who TEXT NOT NULL, what TEXT NOT NULL, at REAL NOT NULL);
"""

ENV: dict[str, str] = {}
hg: HG


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_et() -> dt.datetime:
    return dt.datetime.now(ET)


def log(conn: sqlite3.Connection, story_id: int, who: str, what: str) -> None:
    conn.execute("INSERT INTO log (story_id, who, what, at) VALUES (?, ?, ?, ?)", (story_id, who, what, time.time()))


def story(conn: sqlite3.Connection, sid: int, full: bool = False) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM stories WHERE id = ?", (sid,)).fetchone()
    if not row:
        raise LookupError
    s = dict(row)
    for k in ("sources", "claims", "files"):
        s[k] = json.loads(s[k])
    s["verified"] = sum(1 for c in s["claims"] if c.get("checked"))
    if full:
        s["runs"] = [dict(r) | {"steps": json.loads(r["steps"]), "usage": json.loads(r["usage"])}
                     for r in conn.execute("SELECT * FROM runs WHERE story_id = ? ORDER BY id", (sid,))]
        s["log"] = [dict(r) for r in conn.execute("SELECT * FROM log WHERE story_id = ? ORDER BY id", (sid,))]
    else:
        del s["draft"]
    return s


# ── the agent ────────────────────────────────────────────────────────────────────────────────────────────────────
def prompt_for(desk: str, kind: str, brief: str) -> str:
    t = now_et()
    return (f"Desk: {desk}. Task: {kind}. It is {t:%A %Y-%m-%d, %H:%M} Eastern.\n\n"
            f"Assignment from the editor: {brief}")


def start_run(conn: sqlite3.Connection, story_id: int, kind: str, text: str, note: str, previous: str | None,
              desk: str, task: str) -> None:
    turn = hg.start(text, user=ENV.get("DESK_EDITOR", "editor"), previous=previous,
                    metadata={"app": "market-desk", "desk": desk, "task": task, "story": str(story_id)})
    conn.execute("INSERT INTO runs (story_id, kind, note, response_id, status, created_at) VALUES (?,?,?,?,?,?)",
                 (story_id, kind, note, turn["id"], turn["status"], time.time()))
    conn.execute("UPDATE stories SET session_id = ?, updated_at = ? WHERE id = ?",
                 (turn["metadata"].get("session_id", ""), time.time(), story_id))


def assign(desk: str, kind: str, title: str, brief: str) -> dict[str, Any]:
    if desk not in DESKS or kind not in KINDS or not title.strip() or not brief.strip():
        raise RuntimeError("desk, kind, title and brief are required")
    with db() as conn:
        t = time.time()
        cur = conn.execute("INSERT INTO stories (desk, kind, title, brief, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                           (desk, kind, title.strip(), brief.strip(), t, t))
        sid = int(cur.lastrowid or 0)
        log(conn, sid, "editor", "assigned")
        start_run(conn, sid, "draft", prompt_for(desk, kind, brief), "", None, desk, kind)
        return story(conn, sid)


def revise(story_id: int, note: str) -> dict[str, Any]:
    if not note.strip():
        raise RuntimeError("say what to change")
    with db() as conn:
        s = story(conn, story_id)
        prev = conn.execute("SELECT response_id FROM runs WHERE story_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                            (story_id,)).fetchone()
        if not prev:
            raise RuntimeError("there is no finished draft to revise yet")
        text = (f"The editor sent the draft back with this note: {note.strip()}\n\nRevise the draft in the same folder "
                "(draft.md, sources.json, verify.md, charts) and answer with what you changed and the desk-report block.")
        start_run(conn, story_id, "revision", text, note.strip(), prev["response_id"], s["desk"], s["kind"])
        conn.execute("UPDATE stories SET status = 'revising', editor_note = ? WHERE id = ?", (note.strip(), story_id))
        log(conn, story_id, "editor", f"sent back: {note.strip()}")
        return story(conn, story_id)


def final_message(r: dict[str, Any]) -> str:
    for item in reversed(r.get("output") or []):
        if item.get("type") == "message":
            text = "\n\n".join(c.get("text", "") for c in item.get("content") or [] if c.get("type") == "output_text").strip()
            if text:
                return text
    return ""


def parse_claims(md: str) -> list[dict[str, Any]]:
    """verify.md's table (Claim | Source | Status | Note) as rows."""
    rows = []
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not line.strip().startswith("|") or set(cells[0]) <= set("-: ") or cells[0].lower() == "claim":
            continue
        rows.append({"claim": cells[0], "source": cells[1], "status": cells[2] if len(cells) > 2 else "",
                     "note": cells[3] if len(cells) > 3 else "", "checked": False})
    return rows


def collect(run: dict[str, Any], r: dict[str, Any]) -> None:
    """A finished run: its answer, and the story's draft, sources, claims and charts read from the workspace."""
    answer = final_message(r)
    m = REPORT_RE.search(answer)
    report: dict[str, Any] = {}
    if m:
        try:
            report = json.loads(m.group(1))
        except json.JSONDecodeError:
            report = {}
        answer = (answer[:m.start()] + answer[m.end():]).strip()
    error = "" if r["status"] == "completed" else ((r.get("error") or {}).get("message") or r["status"])
    with db() as conn:
        s = story(conn, run["story_id"])
    update: dict[str, Any] = {}
    folder = str(report.get("folder") or s["folder"] or "").strip("/").removeprefix("workspace/")
    if r["status"] == "completed" and folder and s["session_id"]:
        hg.settle(s["session_id"])
        files = hg.folder(s["session_id"], "/workspace/" + folder)
        draft = hg.read_text(s["session_id"], files, "draft.md")
        try:
            sources = json.loads(hg.read_text(s["session_id"], files, "sources.json") or "[]")
        except json.JSONDecodeError:
            sources = []
        old = {c["claim"]: c for c in s["claims"]}
        claims = [c | {"checked": old.get(c["claim"], {}).get("checked", False)}
                  for c in parse_claims(hg.read_text(s["session_id"], files, "verify.md"))]
        headline = str(report.get("headline") or "") or next(
            (ln.lstrip("# ").strip() for ln in draft.splitlines() if ln.startswith("# ")), s["title"])
        update = {"folder": folder, "draft": draft, "sources": json.dumps(sources if isinstance(sources, list) else []),
                  "claims": json.dumps(claims), "files": json.dumps(files), "headline": headline,
                  "summary": str(report.get("summary") or "")}
    if r["status"] == "completed" and update.get("draft"):
        status = "review"
    elif r["status"] == "cancelled" and s["headline"]:      # a stopped revision: the last draft stands
        status = "review"
    else:
        status = "failed"
        if r["status"] == "completed":
            error = "The agent finished without a draft.md in a desk-report folder."
    with db() as conn:
        conn.execute("UPDATE runs SET status = ?, answer = ?, error = ?, steps = ?, usage = ?, ended_at = ? WHERE id = ?",
                     (r["status"], answer, error, json.dumps(hg.steps(r)), json.dumps(r.get("usage") or {}), time.time(), run["id"]))
        sets = {**update, "status": status, "updated_at": time.time()}
        conn.execute(f"UPDATE stories SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), run["story_id"]])
        log(conn, run["story_id"], "agent", {"review": "filed the draft", "failed": f"could not file: {error}"}.get(status, status))


WATCHING: set[str] = set()


def watch(row_id: int, response_id: str) -> None:
    """The agent's steps, live: a stream watcher per running turn writes them as they finish."""
    if response_id in WATCHING:
        return
    WATCHING.add(response_id)

    def on_items(items: list[dict[str, Any]]) -> None:
        with db() as conn:
            conn.execute("UPDATE runs SET steps = ? WHERE id = ? AND status IN ('queued', 'in_progress')",
                         (json.dumps(hg.steps({"output": items})), row_id))
    hg.watch(response_id, on_items)


def follow() -> None:
    while True:
        with db() as conn:
            pending = [dict(r) for r in conn.execute("SELECT * FROM runs WHERE status IN ('queued', 'in_progress')")]
        for run in pending:
            try:
                r = hg.response(run["response_id"])
                if r["status"] in FINAL:
                    collect(run, r)
                else:
                    watch(run["id"], run["response_id"])
                    with db() as conn:
                        conn.execute("UPDATE runs SET status = ? WHERE id = ?", (r["status"], run["id"]))
            except Exception as e:                       # the platform is down or the story vanished: next round
                print(f"follow run {run['id']}: {e}", flush=True)
        time.sleep(3)


def calendar(days: int = 14) -> list[dict[str, Any]]:
    """The scheduled assignments of the next `days` days, each with the story already made for it, if any."""
    start = now_et().date()
    with db() as conn:
        made = {(r["title"], r["desk"], dt.datetime.fromtimestamp(r["created_at"], ET).date().isoformat()): r["id"]
                for r in conn.execute("SELECT id, title, desk, created_at FROM stories")}
    out = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        for c in CALENDAR:
            if d.weekday() in c["days"]:
                out.append(c | {"date": d.isoformat(), "story_id": made.get((c["title"], c["desk"], d.isoformat()))})
    return out


# ── HTTP ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def send(self, status: int, data: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, obj: Any, status: int = 200) -> None:
        self.send(status, json.dumps(obj).encode(), "application/json")

    def body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n)) if n else {}
        except json.JSONDecodeError:
            return {}

    def dispatch(self, method: str) -> None:
        p = [x for x in urllib.parse.urlparse(self.path).path.split("/") if x]
        try:
            getattr(self, "on_" + method)(p)
        except ApiError as e:
            self.json({"error": f"HarnessGateway {e.status}: {e.body[:300]}"}, 502)
        except LookupError:
            self.json({"error": "not found"}, 404)
        except (RuntimeError, ValueError) as e:
            self.json({"error": str(e)}, 400)

    def do_GET(self) -> None:
        self.dispatch("get")

    def do_POST(self) -> None:
        self.dispatch("post")

    def do_PUT(self) -> None:
        self.dispatch("put")

    def on_get(self, p: list[str]) -> None:
        if not p:
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == ["api", "meta"]:
            return self.json({"desks": DESKS, "kinds": KINDS, "statuses": STATUSES, "model": hg.model, "api": hg.api,
                              "monthly": MONTHLY, "now": now_et().isoformat()})
        if p == ["api", "calendar"]:
            return self.json(calendar())
        if p == ["api", "stories"]:
            with db() as conn:
                return self.json([story(conn, r["id"]) for r in conn.execute("SELECT id FROM stories ORDER BY updated_at DESC")])
        if len(p) == 3 and p[:2] == ["api", "stories"]:
            with db() as conn:
                return self.json(story(conn, int(p[2]), full=True))
        if len(p) == 4 and p[0] == "ws":                     # /ws/<story>/<file id>/<name>: a workspace file, relayed
            with db() as conn:
                s = story(conn, int(p[1]))
            f = next((f for f in s["files"] if f["id"] == p[2]), None)
            if not f:
                raise LookupError
            return self.send(200, hg.read(s["session_id"], f["id"]),
                             KINDS_BY_EXT.get(Path(f["rel"]).suffix.lower(), "application/octet-stream"))
        raise LookupError

    def on_post(self, p: list[str]) -> None:
        b = self.body()
        if p == ["api", "stories"]:
            return self.json(assign(str(b.get("desk")), str(b.get("kind")), str(b.get("title") or ""), str(b.get("brief") or "")))
        if len(p) == 4 and p[:2] == ["api", "stories"] and p[3] == "revise":
            return self.json(revise(int(p[2]), str(b.get("note") or "")))
        if len(p) == 4 and p[:2] == ["api", "stories"] and p[3] == "retry":
            with db() as conn:
                s = story(conn, int(p[2]))
                if s["status"] != "failed":
                    raise RuntimeError("only a story the agent could not file is tried again")
                start_run(conn, s["id"], "draft", prompt_for(s["desk"], s["kind"], s["brief"]), "", None, s["desk"], s["kind"])
                conn.execute("UPDATE stories SET status = 'drafting' WHERE id = ?", (s["id"],))
                log(conn, s["id"], "editor", "tried again")
                return self.json(story(conn, s["id"]))
        if len(p) == 4 and p[:2] == ["api", "stories"] and p[3] == "decide":
            decision = str(b.get("status"))
            if decision not in ("approved", "spiked", "review"):
                raise RuntimeError("status is approved, spiked or review")
            with db() as conn:
                s = story(conn, int(p[2]))
                if s["status"] in ("drafting", "revising"):
                    raise RuntimeError("the agent is still working on it")
                conn.execute("UPDATE stories SET status = ?, updated_at = ? WHERE id = ?", (decision, time.time(), s["id"]))
                log(conn, s["id"], "editor", {"approved": f"approved ({s['verified']}/{len(s['claims'])} claims verified)",
                                              "spiked": "spiked", "review": "reopened"}[decision])
                return self.json(story(conn, s["id"]))
        if len(p) == 4 and p[:2] == ["api", "stories"] and p[3] == "cancel":
            with db() as conn:
                run = conn.execute("SELECT response_id FROM runs WHERE story_id = ? AND status IN ('queued', 'in_progress')"
                                   " ORDER BY id DESC LIMIT 1", (p[2],)).fetchone()
            if not run:
                raise RuntimeError("nothing is running")
            hg.cancel(run["response_id"])
            return self.json({"ok": True})
        raise LookupError

    def on_put(self, p: list[str]) -> None:
        b = self.body()
        if len(p) == 4 and p[:2] == ["api", "stories"] and p[3] == "claims":
            with db() as conn:
                s = story(conn, int(p[2]))
                i = int(b.get("index", -1))
                if not 0 <= i < len(s["claims"]):
                    raise RuntimeError("no such claim")
                s["claims"][i]["checked"] = bool(b.get("checked"))
                if "note" in b:
                    s["claims"][i]["editor_note"] = str(b["note"])[:500]
                conn.execute("UPDATE stories SET claims = ? WHERE id = ?", (json.dumps(s["claims"]), s["id"]))
                return self.json(story(conn, s["id"]))
        raise LookupError


def main() -> None:
    global hg, ENV
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8910)
    a = ap.parse_args()
    ENV = dotenv(HERE)
    hg = HG.from_env(HERE, DEFAULT_MODEL)
    with db() as conn:
        conn.executescript(SCHEMA)
    threading.Thread(target=follow, daemon=True).start()
    print(f"http://127.0.0.1:{a.port}  (API {hg.api}, model {hg.model})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
