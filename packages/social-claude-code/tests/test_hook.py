#!/usr/bin/env python3
"""Hermetic unit test for the PreToolUse fence hook.

Feeds one PreToolUse JSON event at a time to seeds/home/.claude/hooks/pre-tool-use.py and asserts the
permissionDecision it prints. No live CLI or provider is used.

    python3 tests/test_hook.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "seeds" / "home" / ".claude" / "hooks" / "pre-tool-use.py"


def decision(tool, tool_input, workspace):
    env = dict(os.environ)
    env["HG_WORKSPACE"] = workspace
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
        {"tool_name": tool, "tool_input": tool_input}), capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    return out["hookSpecificOutput"]["permissionDecision"], out["hookSpecificOutput"]["permissionDecisionReason"]


def main():
    ws = tempfile.mkdtemp(prefix="hook-ws-")
    cases = [
        # (name, tool, tool_input, expected)
        ("bash-read-only", "Bash", {"command": "grep -r coffee " + ws}, "allow"),
        ("bash-redirect-in-ws", "Bash", {"command": "echo hi > " + ws + "/campaigns/x.md"}, "allow"),
        ("bash-curl-host", "Bash", {"command": "curl https://api.twitter.com/2/tweets"}, "deny"),
        ("bash-api-url", "Bash", {"command": "curl https://social.example.com/api/v1/statuses"}, "deny"),
        ("bash-curl-data", "Bash", {"command": "curl -d 'x=1' https://example.com"}, "deny"),
        ("bash-curl-post", "Bash", {"command": "curl --request POST https://example.com"}, "deny"),
        ("bash-requests-post", "Bash", {"command": "python3 -c \"import requests; requests.post('https://example.com')\""}, "deny"),
        ("bash-redirect-outside", "Bash", {"command": "echo hi > /tmp/leak.md"}, "deny"),
        ("bash-bluesky", "Bash", {"command": "curl https://bsky.social/xrpc/app.bsky.feed.getTimeline"}, "deny"),
        ("write-in-ws", "Write", {"file_path": ws + "/campaigns/x.md", "content": "post"}, "allow"),
        ("write-outside", "Write", {"file_path": "/etc/hosts", "content": "x"}, "deny"),
        ("edit-outside", "Edit", {"file_path": "/root/.profile", "old_string": "a", "new_string": "b"}, "deny"),
        ("multiedit-in-ws", "MultiEdit", {"edits": [{"file_path": ws + "/campaigns/a.md", "old_string": "a", "new_string": "b"}]}, "allow"),
        ("webfetch-ok", "WebFetch", {"url": "https://en.wikipedia.org/wiki/Coffee"}, "allow"),
        ("webfetch-social", "WebFetch", {"url": "https://api.threads.net/v1.0/me"}, "deny"),
    ]
    failures = 0
    for name, tool, tool_input, expected in cases:
        try:
            got, reason = decision(tool, tool_input, ws)
        except Exception as e:
            print(f"FAIL {name}: {e}")
            failures += 1
            continue
        if got != expected:
            print(f"FAIL {name}: {got} (wanted {expected}): {reason}")
            failures += 1
        else:
            print(f"ok   {name}: {got}")
    print(f"{len(cases) - failures}/{len(cases)} hook cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
