"""A social media manager: campaigns that promote a piece of content across platforms, drafted by the
`social-claude-code` harness package on HarnessGateway. The agent reads the source and writes a post per platform in
its idiom, a cross-posting plan with backlinks (UTM parameters per platform) and cross-links, and a strategy note; a
person edits, approves and schedules each post here. Nothing is posted anywhere: the schedule is this demo's calendar.

One session per campaign (its workspace holds /workspace/campaigns/<slug>/ with plan.json, one file per platform and
strategy.md), so a revision by note works on the same drafts; the manager's name goes with every request as `user`.

    python3 server.py [--port 8920]        # HG_API, HG_KEY, HG_MODEL from ./.env (scripts/setup.py writes it)
"""
from __future__ import annotations

import argparse
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

DEFAULT_MODEL = "social-claude-code/deepseek/deepseek-v4-pro"
PLATFORMS = ["x", "linkedin", "instagram", "threads", "bluesky", "mastodon", "facebook"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "campaign"


def plan_of(text: str) -> list[dict[str, Any]]:
    """plan.json's posts, each with its platform; anything unreadable is no plan."""
    try:
        doc = json.loads(text)
    except ValueError:
        return []
    posts = doc.get("posts", []) if isinstance(doc, dict) else doc
    return [{"platform": str(p.get("platform", "")).lower(), "when": str(p.get("when", "")), "text": str(p.get("text", "")),
             "hashtags": p.get("hashtags") or [], "link": str(p.get("link", "")), "alt_text": str(p.get("alt_text", "")),
             "cross_links": p.get("cross_links") or [], "notes": str(p.get("notes", ""))}
            for p in posts if isinstance(p, dict) and p.get("platform")]


class Handler(web.App):
    here = HERE
    ROUTES = {"GET /app/state": "state", "POST /app/campaign": "new_campaign", "POST /app/revise": "revise",
              "POST /app/approve": "approve", "POST /app/edit": "edit", "POST /app/manager": "manager"}

    def camp(self, b: dict[str, Any]) -> dict[str, Any]:
        return next(c for c in self.store.data["campaigns"] if c["id"] == b["campaign"])

    def state(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            return {"campaigns": self.store.data["campaigns"], "manager": self.store.data["manager"], "model": self.hg.model,
                    "platforms": PLATFORMS}

    def manager(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            self.store.data["manager"] = str(b.get("manager") or "manager")[:60]
            self.store.save()
        return {"manager": self.store.data["manager"]}

    def turn(self, c: dict[str, Any], kind: str, prompt: str) -> dict[str, Any]:
        r = self.hg.start(prompt, user=self.store.data["manager"], previous=c["last_response"],
                          metadata={"campaign": c["slug"], "platforms": ",".join(c["platforms"]), "step": kind})
        t = {"id": "turn_" + uuid.uuid4().hex[:8], "kind": kind, "prompt": prompt, "at": time.time(), "response_id": r["id"],
             "status": "working", "reply": "", "steps": [], "error": None}
        c["session_id"], c["last_response"], c["status"] = r["metadata"]["session_id"], r["id"], "working"
        c["turns"].append(t)
        self.store.save()
        return c

    def new_campaign(self, b: dict[str, Any]) -> dict[str, Any]:
        platforms = [p for p in b.get("platforms", PLATFORMS) if p in PLATFORMS] or PLATFORMS
        source = str(b.get("source", "")).strip()
        if not source:
            raise ValueError("source is a URL or the text to promote")
        title = str(b.get("title") or source[:60])[:120]
        c = {"id": "camp_" + uuid.uuid4().hex[:8], "title": title, "slug": slug(title), "source": source,
             "goal": str(b.get("goal") or "engagement")[:400], "audience": str(b.get("audience") or "")[:400],
             "platforms": platforms, "created": time.time(), "status": "new", "session_id": None, "last_response": None,
             "turns": [], "files": [], "posts": [], "strategy": "", "approved": {}, "edits": {}}
        with self.store.lock:
            self.store.data["campaigns"].insert(0, c)
            is_url = source.startswith(("http://", "https://"))
            what = (f"Source to promote: {source} (read it first; it is the canonical URL)." if is_url else
                    f"Content to promote (there is no URL; link to the brand's site as the canonical link):\n\n{source}\n\n")
            return self.turn(c, "draft", (
                f"Campaign '{c['title']}' (slug {c['slug']}). {what} Goal: {c['goal']}."
                + (f" Audience: {c['audience']}." if c["audience"] else "")
                + f" Platforms: {', '.join(platforms)}.\n\nWrite the drafts, the cross-posting plan with backlinks and "
                f"cross-links, and strategy.md under /workspace/campaigns/{c['slug']}/, with plan.json as specified. "
                f"Answer with a short summary."))

    def revise(self, b: dict[str, Any]) -> dict[str, Any]:
        with self.store.lock:
            c = self.camp(b)
            platform, note = str(b.get("platform") or ""), str(b["note"]).strip()
            what = f"the {platform} draft" if platform in PLATFORMS else "the drafts"
            prompt = (f"Revise {what} of campaign {c['slug']} with this note from the manager: {note}\n\nUpdate plan.json and "
                      f"the platform file(s) in place, keep the rest as they are, and say what changed.")
            return self.turn(c, "revise", prompt)

    def edit(self, b: dict[str, Any]) -> dict[str, Any]:
        """The manager's own edit of a draft's text, kept beside the agent's."""
        with self.store.lock:
            c = self.camp(b)
            c["edits"][str(b["platform"])] = str(b.get("text", ""))[:10000]
            self.store.save()
        return c

    def approve(self, b: dict[str, Any]) -> dict[str, Any]:
        """A person approves a platform's post: it goes on the calendar as the app's own record; nothing is posted."""
        with self.store.lock:
            c = self.camp(b)
            platform = str(b["platform"])
            post = next((p for p in c["posts"] if p["platform"] == platform), None)
            if not post:
                raise ValueError("no draft for that platform")
            c["approved"][platform] = {"at": time.time(), "by": self.store.data["manager"],
                                       "when": str(b.get("when") or post["when"]),
                                       "text": c["edits"].get(platform) or post["text"], "link": post["link"]}
            self.store.save()
        return c


def ended(turn: dict[str, Any], r: dict[str, Any], hg: HG, campaigns: list[dict[str, Any]]) -> None:
    c = next(x for x in campaigns if any(t is turn for t in x["turns"]))
    turn["status"] = "done" if r["status"] == "completed" else "failed"
    turn["reply"], turn["steps"] = hg.text(r), hg.steps(r)
    turn["error"] = (r.get("error") or {}).get("message") if r["status"] != "completed" else None
    turn["seconds"] = int(time.time() - turn["at"])
    hg.settle(c["session_id"])
    c["files"] = hg.folder(c["session_id"], f"/workspace/campaigns/{c['slug']}")
    c["posts"] = plan_of(hg.read_text(c["session_id"], c["files"], "plan.json")) or c["posts"]
    c["strategy"] = hg.read_text(c["session_id"], c["files"], "strategy.md")
    c["status"] = "failed" if turn["status"] == "failed" else "drafted" if c["posts"] else "done"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8920)
    args = ap.parse_args()
    Handler.hg = HG.from_env(HERE, DEFAULT_MODEL)
    Handler.store = web.Store(HERE / "data.json", {"campaigns": [], "manager": "manager"})
    campaigns = Handler.store.data["campaigns"]
    web.follow(Handler.hg, Handler.store, lambda: [t for c in campaigns for t in c["turns"] if t["status"] == "working"],
               lambda turn, r: ended(turn, r, Handler.hg, campaigns))
    web.serve(Handler, args.port)


if __name__ == "__main__":
    main()
