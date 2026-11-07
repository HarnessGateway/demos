#!/usr/bin/env python3
"""PreToolUse guard for the social-claude-code harness.

Refuses, by printing a Claude Code PreToolUse deny decision, exactly what the agent may never do:

  * Bash commands that send anything (POST/PUT/PATCH/DELETE via curl, wget, httpie, or an inline
    python/node HTTP client), or that name a social platform's API host, or that name a URL whose
    path starts with /api/ (the shape of a Mastodon instance's API);
  * WebFetch of a social platform's API host, or of a URL whose path starts with /api/;
  * Write/Edit of a path outside the workspace.

Prints nothing (and exits 0) to allow. A guard error denies, with the reason in the message, so the
fence fails closed rather than open.
"""
import json
import os
import re
import sys
from urllib.parse import urlsplit

WORKSPACE = os.path.realpath((os.environ.get("HG_WORKSPACE") or "").rstrip("/") or "/workspace")

# The social platforms' API hosts. The web UI (x.com, bsky.app, linkedin.com, ...) is fine to read;
# these API hosts are never to be called.
SOCIAL_HOSTS = (
    "api.twitter.com",
    "api.x.com",
    "graph.facebook.com",
    "api.linkedin.com",
    "api.threads.net",
    "bsky.social",
)

# A Bash command that would send data: a data/upload flag on curl/wget/httpie, an explicit write method
# (-X/--request), an inline requests/httpx/aiohttp write call, or fetch(...{method: ...}).
POST = re.compile(
    r"(?i)"
    r"(?:"
    r"\bcurl\b[^\n]*(?:--data(?:-raw|-binary|-urlencode)?\b|-d\b|-F\b|--form\b|-T\b|--upload-file\b|--request\s+(?:POST|PUT|PATCH|DELETE)\b|-X\s*(?:POST|PUT|PATCH|DELETE)\b)"
    r"|\bwget\b[^\n]*(?:--post-data\b|--post-file\b)"
    r"|\bhttps?\s+(?:POST|PUT|PATCH|DELETE)\b"
    r"|\b(?:requests|httpx|aiohttp)\.(?:post|put|patch|delete)\s*\("
    r"|\brequests\.Session\(\)[^\n]*\.(?:post|put|patch|delete)\s*\("
    r"|method\s*[:=]\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]"
    r"|\b(?:curl|wget)\b[^\n]*(?:-X\s*|\b--request\s+)(?:POST|PUT|PATCH|DELETE)\b"
    r")"
)

URL = re.compile(r"https?://[^\s\"'`<>)\]]+")


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def social_host(text: str) -> str | None:
    low = text.lower()
    for host in SOCIAL_HOSTS:
        if host in low:
            return host
    return None


def api_path(text: str) -> str | None:
    for u in URL.findall(text):
        try:
            path = urlsplit(u.rstrip(".,;:!")).path
        except ValueError:
            continue
        if path.startswith("/api/"):
            return u
    return None


def outside_workspace(path: str) -> str | None:
    p = str(path or "").strip()
    if not p or p.startswith("~"):
        return p or "(empty path)"
    real = os.path.realpath(os.path.join(WORKSPACE, p))
    if real != WORKSPACE and not real.startswith(WORKSPACE + "/"):
        return p
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        deny(f"guard could not read the tool call: {e}")
        return
    tool = str(data.get("tool_name") or "")
    inp = data.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    try:
        if tool == "Bash":
            cmd = str(inp.get("command") or "")
            host = social_host(cmd)
            if host:
                deny(f"names {host}, a social platform's API host; this agent never calls it")
                return
            api = api_path(cmd)
            if api:
                deny(f"names a URL under /api/ ({api}); that is the shape of a Mastodon instance's API")
                return
            if POST.search(cmd):
                deny("would send data (POST/PUT/PATCH/DELETE); this agent never posts or sends anything")
                return
        elif tool in ("WebFetch",):
            url = str(inp.get("url") or "")
            host = social_host(url)
            if host:
                deny(f"fetches {host}, a social platform's API host; this agent never calls it")
                return
            api = api_path(url)
            if api:
                deny(f"fetches a URL under /api/ ({api}); that is the shape of a Mastodon instance's API")
                return
        elif tool in ("Write", "Edit", "MultiEdit"):
            bad = outside_workspace(inp.get("file_path"))
            if bad:
                deny(f"writes {bad!r}, outside the workspace ({WORKSPACE}); this agent writes only under the workspace")
                return
    except Exception as e:
        deny(f"guard error refusing the call: {type(e).__name__}: {e}")
        return
    sys.exit(0)


if __name__ == "__main__":
    main()
