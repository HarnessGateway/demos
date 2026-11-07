#!/usr/bin/env python3
"""A small business's CRM with a sales agent in it: customers, a pipeline, an activity log, a map, and an assistant
that reads the whole CRM and drafts emails and texts for a person to review and send.

The agent is the `sales-codex` harness package on HarnessGateway. Each question goes to the platform as a background
OpenAI Responses request with the CRM's current state attached as customers.json; follow-up questions continue the same
session with previous_response_id. The agent answers in prose and, when it proposes reaching out, ends with one fenced
`crm-drafts` block of JSON that the CRM turns into Outbox drafts. Nothing leaves the CRM until a person presses Send.

    python3 server.py [--port 8900]    # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)

Data lives in crm.db (SQLite) beside this file; on first start it is seeded from seed.json (made-up people at real
Austin addresses). Email and SMS are optional: set CRM_SMTP_* or CRM_TWILIO_* in .env (see README.md); without them a
draft can still be approved and logged, which is what the demo does. Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import os
import re
import smtplib
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from hg import FINAL, HG, ApiError, dotenv  # noqa: E402

DB_PATH = HERE / "crm.db"
DEFAULT_MODEL = "sales-codex/deepseek-openai/deepseek-v4-pro"
STAGES = ["Lead", "Contacted", "Qualified", "Proposal", "Won", "Lost"]
SOURCES = ["Walk-in", "Website", "Referral", "Google Ads", "Facebook", "Home show", "Repeat customer", "Other"]
CONTACT_FIELDS = ["name", "company", "email", "phone", "address", "stage", "value", "source", "tags", "next_follow_up",
                  "notes"]
USER_AGENT = "HarnessGateway-demo-CRM/1.0"
DRAFTS_RE = re.compile(r"```crm-drafts[ \t]*\n(.*?)```", re.S)

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, company TEXT DEFAULT '', email TEXT DEFAULT '',
    phone TEXT DEFAULT '', address TEXT DEFAULT '', lat REAL, lon REAL, stage TEXT DEFAULT 'Lead', value REAL DEFAULT 0,
    source TEXT DEFAULT '', tags TEXT DEFAULT '', next_follow_up TEXT DEFAULT '', notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')), updated_at TEXT DEFAULT (datetime('now', 'localtime')));
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    kind TEXT DEFAULT 'Note', body TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now', 'localtime')));
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    channel TEXT NOT NULL, subject TEXT DEFAULT '', body TEXT NOT NULL,
    status TEXT DEFAULT 'draft',              -- draft | sent | approved | failed | discarded
    error TEXT DEFAULT '', sent_to TEXT DEFAULT '', response_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')), sent_at TEXT);
CREATE TABLE IF NOT EXISTS asks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat TEXT NOT NULL, question TEXT NOT NULL, response_id TEXT DEFAULT '',
    session_id TEXT DEFAULT '', status TEXT DEFAULT 'queued', answer TEXT DEFAULT '', error TEXT DEFAULT '',
    steps TEXT DEFAULT '[]', drafts TEXT DEFAULT '[]', usage TEXT DEFAULT '{}',
    created_at REAL NOT NULL, ended_at REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

BRIEFING = """Today is {today} ({weekday}), {time} in Austin. The business: {store}, {address}.
customers.json is attached: the CRM as of now, every customer with their recent activity and miles_from_store.

{question}"""

ENV: dict[str, str] = {}
hg: HG


# ── the database ──────────────────────────────────────────────────────────────────────────────────────────────────
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT count(*) FROM contacts").fetchone()[0]:
            return
    seed()


def seed() -> None:
    """The demo customers from seed.json, with every date moved so the seed reads as if made today."""
    doc = json.loads((HERE / "seed.json").read_text())
    today = dt.date.today()

    def at(days_time: list[Any]) -> str:
        return f"{(today - dt.timedelta(days=days_time[0])).isoformat()} {days_time[1]}"

    with db() as conn:
        for k, v in (("store_name", doc["store"]["name"]), ("store_address", doc["store"]["address"]),
                     ("store_lat", str(doc["store"]["lat"])), ("store_lon", str(doc["store"]["lon"]))):
            put_setting(conn, k, v)
        for c in doc["customers"]:
            follow = (today + dt.timedelta(days=c["next_follow_up"])).isoformat() if c["next_follow_up"] is not None else ""
            cur = conn.execute(
                "INSERT INTO contacts (name, company, email, phone, address, lat, lon, stage, value, source, tags,"
                " next_follow_up, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c["name"], c["company"], c["email"], c["phone"], c["address"], c["lat"], c["lon"], c["stage"], c["value"],
                 c["source"], c["tags"], follow, c["notes"], at(c["created"]), at(c["updated"])))
            for a in c["activities"]:
                conn.execute("INSERT INTO activities (contact_id, kind, body, created_at) VALUES (?,?,?,?)",
                             (cur.lastrowid, a["kind"], a["body"], at(a["at"])))
    print(f"seeded {len(doc['customers'])} demo customers", flush=True)


def settings() -> dict[str, str]:
    with db() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def put_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def clean_contact(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in CONTACT_FIELDS:
        if k not in data:
            continue
        if k == "value":
            try:
                out[k] = float(data[k] or 0)
            except (TypeError, ValueError):
                out[k] = 0.0
        else:
            out[k] = str(data[k] or "").strip()
    if "stage" in out and out["stage"] not in STAGES:
        out["stage"] = "Lead"
    return out


# ── places ───────────────────────────────────────────────────────────────────────────────────────────────────────
_nominatim = threading.Lock()


def http_json(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=10) as r:
        return json.load(r)


def geocode(address: str) -> tuple[float, float] | None:
    """(lat, lon) for an address: the US Census geocoder, then OpenStreetMap's (at most one request a second)."""
    if not address:
        return None
    q = urllib.parse.quote(address)
    try:
        m = http_json("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
                      f"?address={q}&benchmark=Public_AR_Current&format=json")["result"]["addressMatches"]
        if m:
            return float(m[0]["coordinates"]["y"]), float(m[0]["coordinates"]["x"])
    except Exception:
        pass
    with _nominatim:
        time.sleep(1.1)
        try:
            d = http_json(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1")
            if d:
                return float(d[0]["lat"]), float(d[0]["lon"])
        except Exception:
            pass
    return None


def miles(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Straight-line (great-circle) miles."""
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def store_location(s: dict[str, str]) -> tuple[float, float] | None:
    try:
        return float(s["store_lat"]), float(s["store_lon"])
    except (KeyError, ValueError):
        return None


def contacts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    store = store_location(settings())
    rows = conn.execute("SELECT c.*, (SELECT MAX(created_at) FROM activities a WHERE a.contact_id = c.id) AS last_activity"
                        " FROM contacts c ORDER BY c.updated_at DESC").fetchall()
    out = []
    for r in rows:
        c = dict(r)
        c["miles_from_store"] = round(miles(*store, c["lat"], c["lon"]), 1) if store and c["lat"] is not None else None
        out.append(c)
    return out


# ── the agent ────────────────────────────────────────────────────────────────────────────────────────────────────
def snapshot() -> bytes:
    """customers.json: the CRM as the agent reads it (the shape its package's instructions describe)."""
    s = settings()
    store = store_location(s)
    with db() as conn:
        people = contacts(conn)
        acts: dict[int, list[dict[str, str]]] = {}
        for a in conn.execute("SELECT contact_id, kind, body, created_at FROM activities ORDER BY created_at DESC, id DESC"):
            acts.setdefault(a["contact_id"], []).append({"kind": a["kind"], "body": a["body"], "created_at": a["created_at"]})
    keys = ["id", "name", "company", "email", "phone", "address", "lat", "lon", "miles_from_store", "stage", "value",
            "source", "tags", "next_follow_up", "notes", "created_at", "updated_at"]
    return json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "store": {"name": s.get("store_name", "Store"), "address": s.get("store_address", ""),
                  "lat": store[0] if store else None, "lon": store[1] if store else None},
        "stages": STAGES,
        "customers": [{k: c[k] for k in keys} | {"activities": acts.get(c["id"], [])} for c in people],
    }, indent=1).encode()


def ask(question: str, chat: str, previous: str | None) -> dict[str, Any]:
    s = settings()
    now = dt.datetime.now()
    prompt = BRIEFING.format(today=now.date().isoformat(), weekday=now.strftime("%A"), time=now.strftime("%H:%M"),
                             store=s.get("store_name", "Store"), address=s.get("store_address", ""), question=question)
    turn = hg.start(prompt, user=ENV.get("CRM_USER", "showroom"), previous=previous,
                    metadata={"app": "crm", "chat": chat}, files={"customers.json": ("application/json", snapshot())})
    with db() as conn:
        cur = conn.execute("INSERT INTO asks (chat, question, response_id, session_id, status, created_at) VALUES (?,?,?,?,?,?)",
                           (chat, question, turn["id"], turn["metadata"].get("session_id", ""), turn["status"], time.time()))
        return ask_row(conn, cur.lastrowid)


def ask_row(conn: sqlite3.Connection, ask_id: int) -> dict[str, Any]:
    r = dict(conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone())
    for k in ("steps", "drafts", "usage"):
        r[k] = json.loads(r[k])
    if r["drafts"]:
        r["drafts"] = outbox_rows(f"o.id IN ({','.join('?' * len(r['drafts']))})", r["drafts"])
    return r


def follow() -> None:
    """A thread: every unfinished question's response, polled until it ends; its answer and drafts stored then."""
    while True:
        with db() as conn:
            pending = [dict(r) for r in conn.execute("SELECT id, response_id FROM asks WHERE status IN ('queued', 'in_progress')")]
        for a in pending:
            try:
                r = hg.response(a["response_id"])
            except Exception:
                continue
            steps = hg.steps(r)
            if r["status"] not in FINAL:
                with db() as conn:
                    conn.execute("UPDATE asks SET status = ?, steps = ? WHERE id = ?", (r["status"], json.dumps(steps), a["id"]))
                continue
            answer = final_message(r)
            answer, draft_ids, note = extract_drafts(answer, r["id"])
            error = (r.get("error") or {}).get("message", "") if r["status"] != "completed" else ""
            with db() as conn:
                conn.execute("UPDATE asks SET status = ?, answer = ?, error = ?, steps = ?, drafts = ?, usage = ?, ended_at = ?"
                             " WHERE id = ?", (r["status"], answer + note, error, json.dumps(steps), json.dumps(draft_ids),
                                               json.dumps(r.get("usage") or {}), time.time(), a["id"]))
        time.sleep(3)


def final_message(r: dict[str, Any]) -> str:
    """The agent's last message: earlier ones are its progress notes."""
    for item in reversed(r.get("output") or []):
        if item.get("type") == "message":
            text = "\n\n".join(c.get("text", "") for c in item.get("content") or [] if c.get("type") == "output_text").strip()
            if text:
                return text
    return ""


def extract_drafts(text: str, response_id: str) -> tuple[str, list[int], str]:
    """The answer without its crm-drafts block, the Outbox ids made from the block, and a note on what was skipped."""
    m = DRAFTS_RE.search(text)
    if not m:
        return text, [], ""
    clean = (text[:m.start()] + text[m.end():]).strip()
    try:
        items = json.loads(m.group(1))
    except json.JSONDecodeError:
        return clean, [], "\n\n_(The agent's drafts could not be read; ask it to write them again.)_"
    items = items if isinstance(items, list) else []
    ids = []
    with db() as conn:
        for d in items:
            if not isinstance(d, dict):
                continue
            channel, body = d.get("channel"), str(d.get("body") or "").strip()
            c = conn.execute("SELECT email, phone FROM contacts WHERE id = ?", (d.get("contact_id"),)).fetchone()
            if channel not in ("email", "sms") or not body or not c or not (c["email"] if channel == "email" else c["phone"]):
                continue
            cur = conn.execute("INSERT INTO outbox (contact_id, channel, subject, body, response_id) VALUES (?,?,?,?,?)",
                               (d["contact_id"], channel, str(d.get("subject") or "").strip() if channel == "email" else "",
                                body, response_id))
            ids.append(cur.lastrowid)
    skipped = len(items) - len(ids)
    return clean, ids, f"\n\n_({skipped} draft(s) skipped: unknown customer or no email/phone on file.)_" if skipped else ""


# ── the Outbox ───────────────────────────────────────────────────────────────────────────────────────────────────
def email_ready() -> bool:
    return all(ENV.get(k) for k in ("CRM_SMTP_HOST", "CRM_SMTP_USER", "CRM_SMTP_PASSWORD", "CRM_EMAIL_FROM"))


def sms_ready() -> bool:
    return all(ENV.get(k) for k in ("CRM_TWILIO_SID", "CRM_TWILIO_TOKEN", "CRM_TWILIO_FROM"))


def test_mode() -> bool:
    return ENV.get("CRM_TEST_MODE", "1") != "0"


def outbox_rows(where: str = "1", args: Any = ()) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT o.*, c.name AS contact_name, c.email AS contact_email, c.phone AS contact_phone"
                            f" FROM outbox o LEFT JOIN contacts c ON c.id = o.contact_id WHERE {where}"
                            " ORDER BY CASE o.status WHEN 'draft' THEN 0 ELSE 1 END, o.id DESC", args).fetchall()
    return [dict(r) for r in rows]


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = ENV["CRM_EMAIL_FROM"], to, subject or "(no subject)"
    msg.set_content(body)
    port = int(ENV.get("CRM_SMTP_PORT") or 587)
    ctx = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(ENV["CRM_SMTP_HOST"], port, context=ctx, timeout=30) if port == 465 else \
        smtplib.SMTP(ENV["CRM_SMTP_HOST"], port, timeout=30)
    with smtp:
        if port != 465:
            smtp.starttls(context=ctx)
        smtp.login(ENV["CRM_SMTP_USER"], ENV["CRM_SMTP_PASSWORD"])
        smtp.send_message(msg)


def send_sms(to: str, body: str) -> None:
    sid = ENV["CRM_TWILIO_SID"]
    auth = base64.b64encode(f"{sid}:{ENV['CRM_TWILIO_TOKEN']}".encode()).decode()
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                                 data=urllib.parse.urlencode({"To": to, "From": ENV["CRM_TWILIO_FROM"], "Body": body}).encode(),
                                 headers={"Authorization": f"Basic {auth}", "User-Agent": USER_AGENT})
    try:
        urllib.request.urlopen(req, timeout=30).close()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Twilio {e.code}") from None


def e164(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "+" + digits if phone.strip().startswith("+") else ("+1" + digits if len(digits) == 10 else "+" + digits)


def send_outbox(outbox_id: str, subject: str | None, body: str | None) -> dict[str, Any]:
    """Send a draft, or, when its channel is not set up, approve it: logged on the customer, delivered by no one."""
    rows = outbox_rows("o.id = ?", (outbox_id,))
    if not rows:
        raise LookupError("not found")
    o = rows[0]
    if o["status"] in ("sent", "approved"):
        raise RuntimeError("Already done.")
    subject = (o["subject"] if subject is None else subject).strip()
    body = (o["body"] if body is None else body).strip()
    if not body:
        raise RuntimeError("The message is empty.")
    email = o["channel"] == "email"
    ready = email_ready() if email else sms_ready()
    status, to = "approved", ""
    if ready:
        test = test_mode()
        to = (ENV.get("CRM_TEST_EMAIL") if email else ENV.get("CRM_TEST_PHONE")) if test else \
            (o["contact_email"] if email else o["contact_phone"])
        if not to:
            raise RuntimeError("Test mode is on and CRM_TEST_EMAIL / CRM_TEST_PHONE is not set." if test else "No address on file.")
        tag = f"[TEST to {o['contact_email'] if email else o['contact_phone']}] " if test else ""
        try:
            send_email(to, tag + subject, body) if email else send_sms(e164(to), tag + body)
        except Exception as e:
            with db() as conn:
                conn.execute("UPDATE outbox SET status = 'failed', error = ?, subject = ?, body = ? WHERE id = ?",
                             (str(e), subject, body, outbox_id))
            raise RuntimeError(f"Sending failed: {e}") from None
        status = "sent"
    with db() as conn:
        conn.execute("UPDATE outbox SET status = ?, error = '', subject = ?, body = ?, sent_to = ?, "
                     "sent_at = datetime('now', 'localtime') WHERE id = ?", (status, subject, body, to, outbox_id))
        verb = "Sent" if status == "sent" else "Approved to send"
        kind = "Email" if email else "SMS"
        conn.execute("INSERT INTO activities (contact_id, kind, body) VALUES (?, ?, ?)",
                     (o["contact_id"], kind, f"{verb}: {subject}\n\n{body}" if subject else f"{verb}: {body}"))
        conn.execute("UPDATE contacts SET updated_at = datetime('now', 'localtime') WHERE id = ?", (o["contact_id"],))
    return outbox_rows("o.id = ?", (outbox_id,))[0]


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

    def parts(self) -> list[str]:
        return [p for p in urllib.parse.urlparse(self.path).path.split("/") if p]

    def handle_one(self, method: str) -> None:
        try:
            getattr(self, "on_" + method)(self.parts())
        except ApiError as e:
            self.json({"error": f"HarnessGateway {e.status}: {e.body[:300]}"}, 502)
        except LookupError:
            self.json({"error": "not found"}, 404)
        except RuntimeError as e:
            self.json({"error": str(e)}, 400)

    def do_GET(self) -> None:
        self.handle_one("get")

    def do_POST(self) -> None:
        self.handle_one("post")

    def do_PUT(self) -> None:
        self.handle_one("put")

    def do_DELETE(self) -> None:
        self.handle_one("delete")

    def on_get(self, p: list[str]) -> None:
        if not p:
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == ["api", "meta"]:
            s = settings()
            return self.json({"stages": STAGES, "sources": SOURCES, "model": hg.model, "api": hg.api,
                              "store": {"name": s.get("store_name", ""), "address": s.get("store_address", ""),
                                        "lat": s.get("store_lat"), "lon": s.get("store_lon")},
                              "email_ready": email_ready(), "sms_ready": sms_ready(), "test_mode": test_mode()})
        if p == ["api", "contacts"]:
            with db() as conn:
                return self.json(contacts(conn))
        if len(p) == 4 and p[:2] == ["api", "contacts"] and p[3] == "activities":
            with db() as conn:
                rows = conn.execute("SELECT * FROM activities WHERE contact_id = ? ORDER BY created_at DESC, id DESC", (p[2],))
                return self.json([dict(r) for r in rows])
        if p == ["api", "outbox"]:
            return self.json(outbox_rows())
        if p == ["api", "chat"]:                            # the latest conversation, so a reload picks it up
            with db() as conn:
                last = conn.execute("SELECT chat FROM asks ORDER BY id DESC LIMIT 1").fetchone()
                ids = [r["id"] for r in conn.execute("SELECT id FROM asks WHERE chat = ? ORDER BY id", (last["chat"],))] if last else []
                return self.json([ask_row(conn, i) for i in ids])
        if len(p) == 3 and p[:2] == ["api", "ask"]:
            with db() as conn:
                if not conn.execute("SELECT 1 FROM asks WHERE id = ?", (p[2],)).fetchone():
                    raise LookupError
                return self.json(ask_row(conn, int(p[2])))
        raise LookupError

    def on_post(self, p: list[str]) -> None:
        data = self.body()
        if p == ["api", "contacts"]:
            c = clean_contact(data)
            if not c.get("name"):
                raise RuntimeError("name is required")
            c["lat"], c["lon"] = geocode(c.get("address", "")) or (None, None)
            with db() as conn:
                cur = conn.execute(f"INSERT INTO contacts ({', '.join(c)}) VALUES ({', '.join('?' * len(c))})", list(c.values()))
                return self.json(dict(conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone()), 201)
        if len(p) == 4 and p[:2] == ["api", "contacts"] and p[3] == "activities":
            body = str(data.get("body") or "").strip()
            if not body:
                raise RuntimeError("body is required")
            with db() as conn:
                cur = conn.execute("INSERT INTO activities (contact_id, kind, body) VALUES (?, ?, ?)",
                                   (p[2], str(data.get("kind") or "Note"), body))
                conn.execute("UPDATE contacts SET updated_at = datetime('now', 'localtime') WHERE id = ?", (p[2],))
                return self.json(dict(conn.execute("SELECT * FROM activities WHERE id = ?", (cur.lastrowid,)).fetchone()), 201)
        if p == ["api", "ask"]:
            question = str(data.get("question") or "").strip()
            if not question:
                raise RuntimeError("question is required")
            chat = str(data.get("chat") or "") or f"chat-{int(time.time() * 1000)}"
            with db() as conn:
                prev = conn.execute("SELECT response_id FROM asks WHERE chat = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                                    (chat,)).fetchone()
            return self.json(ask(question, chat, prev["response_id"] if prev else None))
        if len(p) == 4 and p[:2] == ["api", "ask"] and p[3] == "cancel":
            with db() as conn:
                row = conn.execute("SELECT response_id FROM asks WHERE id = ?", (p[2],)).fetchone()
            if not row:
                raise LookupError
            hg.cancel(row["response_id"])
            return self.json({"ok": True})
        if len(p) == 4 and p[:2] == ["api", "outbox"] and p[3] == "send":
            return self.json(send_outbox(p[2], data.get("subject"), data.get("body")))
        raise LookupError

    def on_put(self, p: list[str]) -> None:
        data = self.body()
        if len(p) == 3 and p[:2] == ["api", "contacts"]:
            c = clean_contact(data)
            if not c or ("name" in c and not c["name"]):
                raise RuntimeError("name is required")
            with db() as conn:
                old = conn.execute("SELECT address, lat FROM contacts WHERE id = ?", (p[2],)).fetchone()
            if not old:
                raise LookupError
            if "address" in c and (c["address"] != old["address"] or old["lat"] is None):
                c["lat"], c["lon"] = geocode(c["address"]) or (None, None)
            with db() as conn:
                conn.execute(f"UPDATE contacts SET {', '.join(f'{k} = ?' for k in c)}, updated_at = datetime('now', 'localtime')"
                             " WHERE id = ?", [*c.values(), p[2]])
                return self.json(dict(conn.execute("SELECT * FROM contacts WHERE id = ?", (p[2],)).fetchone()))
        if p == ["api", "store"]:
            name, address = str(data.get("name") or "").strip(), str(data.get("address") or "").strip()
            loc = geocode(address) if address != settings().get("store_address") else store_location(settings())
            with db() as conn:
                put_setting(conn, "store_name", name or "Store")
                put_setting(conn, "store_address", address)
                put_setting(conn, "store_lat", str(loc[0]) if loc else "")
                put_setting(conn, "store_lon", str(loc[1]) if loc else "")
            return self.json({"located": bool(loc)})
        if len(p) == 3 and p[:2] == ["api", "outbox"]:
            fields = {k: str(data[k]) for k in ("subject", "body") if k in data}
            if data.get("status") == "discarded":
                fields["status"] = "discarded"
            if not fields:
                raise RuntimeError("nothing to update")
            with db() as conn:
                conn.execute(f"UPDATE outbox SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ? AND status = 'draft'",
                             [*fields.values(), p[2]])
            rows = outbox_rows("o.id = ?", (p[2],))
            if not rows:
                raise LookupError
            return self.json(rows[0])
        raise LookupError

    def on_delete(self, p: list[str]) -> None:
        table = {"contacts": "contacts", "activities": "activities"}.get(p[1] if len(p) == 3 and p[0] == "api" else "")
        if not table:
            raise LookupError
        with db() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (p[2],))
        self.json({"ok": True})


def main() -> None:
    global hg, ENV
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8900)
    a = ap.parse_args()
    ENV = dotenv(HERE) | {k: v for k, v in os.environ.items() if k.startswith("CRM_")}
    hg = HG.from_env(HERE, DEFAULT_MODEL)
    init_db()
    threading.Thread(target=follow, daemon=True).start()
    print(f"http://127.0.0.1:{a.port}  (API {hg.api}, model {hg.model})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
