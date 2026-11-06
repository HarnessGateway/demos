#!/usr/bin/env python3
"""PreToolUse deny hook for the sales agent: the hard control that backs the AGENTS.md rules.

Codex calls this with a hook request on stdin ({"tool_name": "Bash", "tool_input": {"command": ...}})
and expects a PreToolUse decision on stdout. Allow by default (empty output, exit 0); deny the
operations this agent must never perform, with a reason the turn records. Read-only web GETs,
writing inside the workspace, and ordinary file work all pass.
"""
import json
import re
import sys

REDIRECT = re.compile(r">>?\s*([^\s;|&<>`]+)")


def forbidden(command: str) -> str:
    low = command.lower()

    # Never touch a git remote.
    if "git" in low and any(w in low for w in ("push", "pull", "fetch", "remote", "clone")):
        return "git remote operations are not allowed"

    # Never send data to an external service: curl/wget with a body, a non-GET method, or a form/upload.
    if any(w in low for w in ("curl", "wget", "httpie", "http ")):
        if any(w in low for w in ("-d ", "-d\"", "-d'", "--data", "--data-raw", "--json", "--data-binary",
                                  "--form", "--form-string", "--upload-file", "--post-data",
                                  "-x post", "-x put", "-x patch", "-x delete",
                                  "--request post", "--request put", "--request patch", "--request delete")):
            return "sending data to an external service is not allowed"

    # Never open a remote shell or copy channel.
    if any(w in low for w in ("ssh ", "scp ", "sftp ", "rsync ", "nc ", "ncat ", "socat ", "telnet ")):
        return "remote shells and copies are not allowed"

    # Never install software at runtime.
    if any(w in low for w in ("npm install", "npm i ", "pip install", "pip3 install", "apt-get install",
                              "apt install", "yum install", "dnf install", "brew install", "cargo install",
                              "go install", "gem install", "cpan install")):
        return "installing software is not allowed"
    if re.search(r"\|\s*(sh|bash|zsh|dash)(\s|$)", command):
        return "installing software is not allowed"

    # Never run destructive commands.
    if any(w in low for w in ("rm -rf", "rm -fr", "rm -r -f", "rm --recursive --force", "mkfs", "dd if=",
                              "shutdown", "reboot", "halt", "poweroff", ":(){ :|:& };:", "> /dev/sd")):
        return "destructive commands are not allowed"

    # Never write outside the workspace via a shell redirection or tee.
    for target in REDIRECT.findall(command):
        if target.startswith("/") and target != "/workspace" and not target.startswith("/workspace/"):
            return "writing outside the workspace is not allowed"
    if "tee " in low:
        for target in re.findall(r"\btee\s+([^\s;|&<>`]+)", command):
            if target.startswith("/") and target != "/workspace" and not target.startswith("/workspace/"):
                return "writing outside the workspace is not allowed"

    return ""


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return  # not a hook request we can judge: allow
    if not isinstance(data, dict) or data.get("tool_name") != "Bash":
        return
    ti = data.get("tool_input") or {}
    command = ti.get("command") if isinstance(ti, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return
    reason = forbidden(command)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": f"blocked: {reason} ({command!r})"}}))


if __name__ == "__main__":
    main()
