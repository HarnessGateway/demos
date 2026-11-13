#!/usr/bin/env python3
"""Social Studio: a small business's social media calendar with a social media manager agent in it. A campaign promotes
one piece of content (a page to read, or pasted text); the agent reads it and writes a post per platform in that
platform's idiom and limits, plans the sequence and timing across platforms, tags every link with UTM parameters per
platform and cross-links the posts. A person edits, approves and schedules each post here. Nothing is posted anywhere:
the calendar is this demo's stand-in for a scheduler.

The agent is the `social-claude-code` harness package on HarnessGateway. Each campaign is one session; a revision (of
one post, or of the whole plan) continues it with previous_response_id. The agent ends each answer with one fenced
`social-plan` block holding the plan as JSON (the same document as campaigns/<slug>/plan.json in its workspace).

    python3 server.py [--port 8920]    # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)

Data lives in social.db (SQLite) beside this file. Standard library only.
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

DB_PATH = HERE / "social.db"
DEFAULT_MODEL = "web:social-claude-code/deepseek"
PLATFORMS = {"x": ("X", 280), "linkedin": ("LinkedIn", 1300), "instagram": ("Instagram", 2200), "threads": ("Threads", 500),
             "bluesky": ("Bluesky", 300), "mastodon": ("Mastodon", 500), "facebook": ("Facebook", 2000)}
PLAN_RE = re.compile(r"```social-plan[ \t]*\n(.*?)```", re.S)
URL_RE = re.compile(r"https?://\S+")
LINK_COST = {"x": 23, "mastodon": 23}           # these platforms count every link as 23 characters, whatever its length
DAY_RE = re.compile(r"day\s*(\d+)\D+(\d{1,2}):(\d{2})", re.I)
DEFAULT_BRAND = {"brand_name": "Showroom", "brand_site": "https://showroom.example",
                 "brand_voice": "A family-owned home-improvement showroom in Austin. Warm, plain-spoken and practical; "
                                "talks like a neighbor who knows remodeling. Never pushy, no hype, no fake urgency, no "
                                "prices or promises the source does not state.",
                 "timezone": "America/Chicago"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, link TEXT DEFAULT '',
    source TEXT NOT NULL, goal TEXT DEFAULT '', audience TEXT DEFAULT '', platforms TEXT NOT NULL, launch TEXT NOT NULL,
    status TEXT DEFAULT 'drafting', session_id TEXT DEFAULT '', strategy TEXT DEFAULT '', canonical_url TEXT DEFAULT '',
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    platform TEXT NOT NULL, seq INTEGER DEFAULT 0, when_text TEXT DEFAULT '', at TEXT DEFAULT '', text TEXT NOT NULL,
    hashtags TEXT DEFAULT '[]', link TEXT DEFAULT '', alt_text TEXT DEFAULT '', cross_links TEXT DEFAULT '[]',
    notes TEXT DEFAULT '', status TEXT DEFAULT 'draft', updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, note TEXT DEFAULT '', response_id TEXT NOT NULL, status TEXT DEFAULT 'queued',
    answer TEXT DEFAULT '', error TEXT DEFAULT '', steps TEXT DEFAULT '[]', usage TEXT DEFAULT '{}',
    created_at REAL NOT NULL, ended_at REAL);
"""

ENV: dict[str, str] = {}
hg: HG


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def brand() -> dict[str, str]:
    with db() as conn:
        return DEFAULT_BRAND | {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(brand()["timezone"])
    except Exception:
        return ZoneInfo("America/Chicago")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "campaign"


def campaign(conn: sqlite3.Connection, cid: int, full: bool = False) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    if not row:
        raise LookupError
    c = dict(row)
    c["platforms"] = json.loads(c["platforms"])
    c["posts"] = [post_doc(r) for r in conn.execute("SELECT * FROM posts WHERE campaign_id = ? ORDER BY at, seq, id", (cid,))]
    c["approved"] = sum(1 for p in c["posts"] if p["status"] == "approved")
    if full:
        c["runs"] = [dict(r) | {"steps": json.loads(r["steps"]), "usage": json.loads(r["usage"])}
                     for r in conn.execute("SELECT * FROM runs WHERE campaign_id = ? ORDER BY id", (cid,))]
    else:
        c.pop("strategy")
    return c


def length(platform: str, text: str) -> int:
    """The length the platform counts: links at their fixed cost where it shortens them."""
    cost = LINK_COST.get(platform)
    return len(URL_RE.sub("x" * cost, text) if cost else text)


def post_doc(r: sqlite3.Row) -> dict[str, Any]:
    p = dict(r)
    p["hashtags"], p["cross_links"] = json.loads(p["hashtags"]), json.loads(p["cross_links"])
    p["label"], p["limit"] = PLATFORMS.get(p["platform"], (p["platform"], 0))
    return p


# ── the agent ────────────────────────────────────────────────────────────────────────────────────────────────────
def first_prompt(c: dict[str, Any]) -> str:
    b = brand()
    source = c["source"].strip()
    read = f"Read this page in full first: {source}" if re.fullmatch(r"https?://\S+", source) else \
        f"The content to promote, pasted by the manager:\n\n<<<\n{source}\n>>>"
    return (f"New campaign `{c['slug']}`: {c['title']}.\n\n"
            f"Brand: {b['brand_name']} ({b['brand_site']}). Voice for this campaign: {b['brand_voice']}\n"
            f"Canonical URL every post links to (add the UTM parameters per platform): {c['link'] or source}\n"
            f"Goal: {c['goal'] or 'drive visits to the canonical URL'}\nAudience: {c['audience'] or 'our customers and neighbors'}\n"
            f"Platforms: {', '.join(c['platforms'])}\n"
            f"Day 1 is {c['launch']} ({b['timezone']}); schedule times are local.\n\n{read}")


def start_run(conn: sqlite3.Connection, c: dict[str, Any], kind: str, text: str, note: str, previous: str | None) -> None:
    turn = hg.start(text, user=ENV.get("SOCIAL_MANAGER", "social-manager"), previous=previous,
                    metadata={"app": "social", "campaign": c["slug"], "platforms": ",".join(c["platforms"])})
    conn.execute("INSERT INTO runs (campaign_id, kind, note, response_id, status, created_at) VALUES (?,?,?,?,?,?)",
                 (c["id"], kind, note, turn["id"], turn["status"], time.time()))
    conn.execute("UPDATE campaigns SET session_id = ?, status = ?, updated_at = ? WHERE id = ?",
                 (hg.session(turn), "drafting" if kind == "plan" else "revising", time.time(), c["id"]))


def create(b: dict[str, Any]) -> dict[str, Any]:
    title, source = str(b.get("title") or "").strip(), str(b.get("source") or "").strip()
    platforms = [p for p in b.get("platforms") or [] if p in PLATFORMS]
    if not title or not source or not platforms:
        raise RuntimeError("a title, the content (a URL or pasted text) and at least one platform are required")
    launch = str(b.get("launch") or "") or (dt.datetime.now(tz()).date() + dt.timedelta(days=1)).isoformat()
    dt.date.fromisoformat(launch)
    with db() as conn:
        slug, n = slugify(title), 1
        while conn.execute("SELECT 1 FROM campaigns WHERE slug = ?", (slug,)).fetchone():
            n += 1
            slug = f"{slugify(title)}-{n}"
        t = time.time()
        cur = conn.execute("INSERT INTO campaigns (slug, title, link, source, goal, audience, platforms, launch, created_at,"
                           " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (slug, title, str(b.get("link") or "").strip(), source, str(b.get("goal") or "").strip(),
                            str(b.get("audience") or "").strip(), json.dumps(platforms), launch, t, t))
        c = campaign(conn, int(cur.lastrowid or 0))
        start_run(conn, c, "plan", first_prompt(c), "", None)
        return campaign(conn, c["id"])


def revise(cid: int, note: str, platform: str = "") -> dict[str, Any]:
    if not note.strip():
        raise RuntimeError("say what to change")
    with db() as conn:
        c = campaign(conn, cid)
        prev = conn.execute("SELECT response_id FROM runs WHERE campaign_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                            (cid,)).fetchone()
        if not prev:
            raise RuntimeError("there is no finished plan to revise yet")
        edits = [f"- {p['platform']} ({p['status']}): {p['text']}" for p in c["posts"] if p["status"] == "approved"]
        keep = ("\n\nThe manager has approved these posts as they stand; keep them unless the note is about them:\n"
                + "\n".join(edits)) if edits else ""
        what = f"Revise the {PLATFORMS[platform][0]} post" if platform in PLATFORMS else "Revise the plan"
        text = (f"{what}. The manager's note: {note.strip()}{keep}\n\nUpdate the files and answer with what changed and the "
                "full social-plan block.")
        start_run(conn, c, "revision", text, (f"{PLATFORMS[platform][0]}: " if platform in PLATFORMS else "") + note.strip(),
                  prev["response_id"])
        return campaign(conn, cid)


def final_message(r: dict[str, Any]) -> str:
    for item in reversed(r.get("output") or []):
        if item.get("type") == "message":
            text = "\n\n".join(c.get("text", "") for c in item.get("content") or [] if c.get("type") == "output_text").strip()
            if text:
                return text
    return ""


def resolve_when(when: str, launch: str) -> str:
    """'day 2 09:00' or an ISO date-time -> local 'YYYY-MM-DDTHH:MM' ('' if neither)."""
    m = DAY_RE.search(when or "")
    if m:
        d = dt.date.fromisoformat(launch) + dt.timedelta(days=int(m.group(1)) - 1)
        return f"{d.isoformat()}T{int(m.group(2)):02d}:{m.group(3)}"
    try:
        t = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
        return (t.astimezone(tz()) if t.tzinfo else t).strftime("%Y-%m-%dT%H:%M")
    except (ValueError, AttributeError):
        return ""


def as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    return [s.strip() for s in str(v or "").replace(",", " ").split() if s.strip()]


def collect(run: dict[str, Any], r: dict[str, Any]) -> None:
    answer = final_message(r)
    m = PLAN_RE.search(answer)
    plan: dict[str, Any] = {}
    if m:
        answer = (answer[:m.start()] + answer[m.end():]).strip()
        try:
            plan = json.loads(m.group(1))
        except json.JSONDecodeError:
            plan = {}
    with db() as conn:
        c = campaign(conn, run["campaign_id"])
    strategy = ""
    if r["status"] == "completed" and c["session_id"]:
        files = hg.folder(c["session_id"], f"campaigns/{c['slug']}")
        if not plan.get("posts"):
            try:
                plan = json.loads(hg.read_text(c["session_id"], files, "plan.json") or "{}")
            except json.JSONDecodeError:
                plan = {}
        strategy = hg.read_text(c["session_id"], files, "strategy.md")
    posts = [p for p in plan.get("posts") or [] if isinstance(p, dict) and str(p.get("platform", "")).lower() in PLATFORMS]
    error = "" if r["status"] == "completed" else ((r.get("error") or {}).get("message") or r["status"])
    if r["status"] == "completed" and not posts:
        error = "The agent finished without a plan of posts."
    with db() as conn:
        conn.execute("UPDATE runs SET status = ?, answer = ?, error = ?, steps = ?, usage = ?, ended_at = ? WHERE id = ?",
                     (r["status"], answer, error, json.dumps(hg.steps(r)), json.dumps(r.get("usage") or {}), time.time(), run["id"]))
        if posts:
            old = {(p["platform"], p["text"]): p["status"] for p in c["posts"]}
            conn.execute("DELETE FROM posts WHERE campaign_id = ?", (c["id"],))
            for i, p in enumerate(posts):
                platform, text = str(p["platform"]).lower(), str(p.get("text") or "").strip()
                when = str(p.get("when") or "")
                conn.execute("INSERT INTO posts (campaign_id, platform, seq, when_text, at, text, hashtags, link, alt_text, cross_links,"
                             " notes, status, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (c["id"], platform, i, when, resolve_when(when, c["launch"]), text, json.dumps(as_list(p.get("hashtags"))),
                              str(p.get("link") or ""), str(p.get("alt_text") or ""), json.dumps(as_list(p.get("cross_links"))),
                              str(p.get("notes") or ""), old.get((platform, text), "draft"), time.time()))
        status = "review" if posts or c["posts"] else "failed"     # a failed revision leaves the last plan standing
        conn.execute("UPDATE campaigns SET status = ?, strategy = CASE WHEN ? != '' THEN ? ELSE strategy END,"
                     " canonical_url = CASE WHEN ? != '' THEN ? ELSE canonical_url END, updated_at = ? WHERE id = ?",
                     (status, strategy, strategy, str(plan.get("canonical_url") or ""), str(plan.get("canonical_url") or ""),
                      time.time(), c["id"]))
        settle_status(conn, c["id"])


def settle_status(conn: sqlite3.Connection, cid: int) -> None:
    """review -> scheduled when every post is approved, and back."""
    c = campaign(conn, cid)
    if c["status"] in ("review", "scheduled") and c["posts"]:
        conn.execute("UPDATE campaigns SET status = ? WHERE id = ?",
                     ("scheduled" if c["approved"] == len(c["posts"]) else "review", cid))


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
            except Exception as e:
                print(f"follow run {run['id']}: {e}", flush=True)
        time.sleep(3)


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
            getattr(self, "on_" + method)(p, self.body() if method in ("post", "put") else {})
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

    def do_DELETE(self) -> None:
        self.dispatch("delete")

    def on_get(self, p: list[str], b: dict[str, Any]) -> None:
        if not p:
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == ["api", "meta"]:
            return self.json({"platforms": {k: {"label": v[0], "limit": v[1]} for k, v in PLATFORMS.items()}, "brand": brand(),
                              "model": hg.model, "api": hg.api, "today": dt.datetime.now(tz()).date().isoformat()})
        if p == ["api", "campaigns"]:
            with db() as conn:
                return self.json([campaign(conn, r["id"]) for r in conn.execute("SELECT id FROM campaigns ORDER BY updated_at DESC")])
        if len(p) == 3 and p[:2] == ["api", "campaigns"]:
            with db() as conn:
                return self.json(campaign(conn, int(p[2]), full=True))
        raise LookupError

    def on_post(self, p: list[str], b: dict[str, Any]) -> None:
        if p == ["api", "campaigns"]:
            return self.json(create(b))
        if len(p) == 4 and p[:2] == ["api", "campaigns"] and p[3] == "revise":
            return self.json(revise(int(p[2]), str(b.get("note") or ""), str(b.get("platform") or "")))
        if len(p) == 4 and p[:2] == ["api", "campaigns"] and p[3] == "retry":
            with db() as conn:
                c = campaign(conn, int(p[2]))
                if c["status"] != "failed" or c["posts"]:
                    raise RuntimeError("only a campaign the agent could not plan is tried again")
                start_run(conn, c, "plan", first_prompt(c), "", None)
                return self.json(campaign(conn, c["id"]))
        if len(p) == 4 and p[:2] == ["api", "campaigns"] and p[3] == "cancel":
            with db() as conn:
                run = conn.execute("SELECT response_id FROM runs WHERE campaign_id = ? AND status IN ('queued', 'in_progress')"
                                   " ORDER BY id DESC LIMIT 1", (p[2],)).fetchone()
            if not run:
                raise RuntimeError("nothing is running")
            hg.cancel(run["response_id"])
            return self.json({"ok": True})
        raise LookupError

    def on_put(self, p: list[str], b: dict[str, Any]) -> None:
        if len(p) == 3 and p[:2] == ["api", "posts"]:
            with db() as conn:
                row = conn.execute("SELECT * FROM posts WHERE id = ?", (p[2],)).fetchone()
                if not row:
                    raise LookupError
                fields: dict[str, Any] = {}
                for k in ("text", "alt_text"):
                    if k in b:
                        fields[k] = str(b[k])
                if "at" in b:
                    at = str(b["at"] or "")
                    if at:
                        dt.datetime.fromisoformat(at)
                    fields["at"] = at[:16]
                if b.get("status") in ("draft", "approved"):
                    if b["status"] == "approved" and not (fields.get("at") or row["at"]):
                        raise RuntimeError("give the post a date and time before approving it")
                    limit = PLATFORMS.get(row["platform"], ("", 0))[1]
                    if b["status"] == "approved" and limit and length(row["platform"], fields.get("text", row["text"])) > limit:
                        raise RuntimeError(f"the post is over {PLATFORMS[row['platform']][0]}'s {limit} characters")
                    fields["status"] = b["status"]
                elif fields and row["status"] == "approved" and fields.get("text", row["text"]) != row["text"]:
                    fields["status"] = "draft"                      # an edited post needs approving again
                fields["updated_at"] = time.time()
                conn.execute(f"UPDATE posts SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", [*fields.values(), p[2]])
                settle_status(conn, row["campaign_id"])
                return self.json(campaign(conn, row["campaign_id"], full=True))
        if p == ["api", "brand"]:
            with db() as conn:
                for k in DEFAULT_BRAND:
                    if k in b:
                        if k == "timezone":
                            ZoneInfo(str(b[k]))
                        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)"
                                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(b[k]).strip()))
            return self.json(brand())
        raise LookupError

    def on_delete(self, p: list[str], b: dict[str, Any]) -> None:
        if len(p) == 3 and p[:2] == ["api", "campaigns"]:
            with db() as conn:
                conn.execute("DELETE FROM campaigns WHERE id = ?", (p[2],))
            return self.json({"ok": True})
        raise LookupError


def main() -> None:
    global hg, ENV
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8920)
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
