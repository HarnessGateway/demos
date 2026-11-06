#!/usr/bin/env python3
"""PreToolUse hook for the social media manager agent.

The agent drafts posts and never sends anything, so this hook is the inside fence: it refuses the network
operations a social manager must never make and the writes it must never do, before the tool runs. It reads one
PreToolUse JSON event on stdin and answers with a decision on stdout. Anything it does not refuse is allowed here;
the permission deny list in settings.json is the backstop for the rest.
"""
import json
import os
import re
import sys

# The social platforms' APIs, by name. Never reachable by any tool.
SOCIAL_HOSTS = (
    "api.twitter.com",
    "api.x.com",
    "graph.facebook.com",
    "api.linkedin.com",
    "api.threads.net",
    "bsky.social",
)
# Any Mastodon instance's API (and, in practice, any /api/ endpoint): the agent reads pages, it never calls APIs.
API_URL = re.compile(r"https?://[a-z0-9.-]+/api/", re.I)

# A command that sends data: curl/wget's request verbs and data flags, fetch/axios style methods, and the common
# HTTP client calls. "POST" is the thing the agent must never do.
SEND_MARKERS = [
    re.compile(r"(?i)(?:^|\s)-x\s*(?:post|put|patch|delete)\b"),
    re.compile(r"(?i)--request(?:=|\s+)(?:post|put|patch|delete)\b"),
    re.compile(r"(?i)(?:^|\s)(?:--data|--data-raw|--data-binary|--data-urlencode|--form|--form-string|"
               r"--upload-file|--post-data|--post-file)\b"),
    re.compile(r"(?i)method\s*[:=]\s*['\"]?(?:post|put|patch|delete)\b"),
    re.compile(r"(?i)\b(?:requests|axios|httpx|urllib)\.(?:post|put|patch|delete)\b"),
    re.compile(r"(?i)\bfetch\s*\([^)]*\b(?:post|put|patch)\b"),
]
# curl/wget short flags that only mean "send data" on those tools.
CURL_DATA = re.compile(r"(?i)(?:^|\s)(?:-d|-f|-t)\b")
CURL_TOOL = re.compile(r"(?i)(?:^|\s)(?:curl|wget)\b")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def allow() -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "ok",
    }}))
    sys.exit(0)


def check_hosts(text: str) -> str | None:
    low = text.lower()
    for host in SOCIAL_HOSTS:
        if host in low:
            return f"never reach a social platform's API: '{host}' appears"
    m = API_URL.search(text)
    if m:
        return f"never call a /api/ endpoint (the agent reads pages, it does not post): '{m.group(0)}'"
    return None


def check_send(cmd: str) -> str | None:
    for rx in SEND_MARKERS:
        if rx.search(cmd):
            return "never send data: the command would POST/PUT/PATCH or upload"
    if CURL_TOOL.search(cmd) and CURL_DATA.search(cmd):
        return "never send data: the command would POST/PUT/PATCH or upload"
    return None


def resolve(p: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(p or "")))


def workspace() -> str:
    return os.environ.get("HG_WORKSPACE", "/workspace")


def main() -> None:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        allow()                                  # unreadable input: let the permission deny list decide
        return
    if not isinstance(ev, dict):
        allow()
        return
    tool = ev.get("tool_name", "")
    inp = ev.get("tool_input")
    inp = inp if isinstance(inp, dict) else {}

    if tool == "Bash":
        cmd = inp.get("command", "") or ""
        reason = check_hosts(cmd) or check_send(cmd)
        if reason is None:
            # Nothing may be written outside /workspace through a shell redirect either.
            for m in re.finditer(r">>?\s*([^\s;&|]+)", cmd):
                if m.group(1).startswith(("/", "~")) and not resolve(m.group(1)).startswith(workspace()):
                    reason = f"never write outside /workspace: redirect to '{m.group(1)}'"
                    break
        deny(reason) if reason else allow()
        return

    if tool in ("Write", "Edit", "MultiEdit"):
        paths = []
        if "file_path" in inp:
            paths.append(inp["file_path"])
        for edit in inp.get("edits") or []:
            if isinstance(edit, dict) and "file_path" in edit:
                paths.append(edit["file_path"])
        for p in paths:
            if not resolve(p).startswith(workspace()):
                deny(f"never write outside /workspace: '{p}'")
                return
        allow()
        return

    if tool == "WebFetch":
        reason = check_hosts(inp.get("url", "") or "")
        deny(reason) if reason else allow()
        return

    allow()


if __name__ == "__main__":
    main()
