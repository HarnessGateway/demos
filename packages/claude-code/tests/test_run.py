#!/usr/bin/env python3
"""Runs `run` against a stub `claude` that replays recorded stream-json fixtures, and checks the mapped output
with hgkit.check — the same validator the platform runs. No live provider is used.

    python3 tests/test_run.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
FIX = ROOT / "tests" / "fixtures"

# hgkit ships on the sandbox image at /opt/hg/lib.
if "/opt/hg/lib" not in sys.path:
    sys.path.insert(0, "/opt/hg/lib")
from hgkit import check  # noqa: E402

FAKE = """#!/usr/bin/env bash
# Replays recorded claude stream-json; FAKE_FIXTURES is colon-separated, one per invocation.
idx_file="${FAKE_IDX_FILE:-/tmp/fake-idx.txt}"
n=0; [ -f "$idx_file" ] && n=$(cat "$idx_file")
IFS=':' read -ra fxs <<< "${FAKE_FIXTURES}"
fx="${fxs[$n]}"; [ -z "$fx" ] && fx="${fxs[0]}"
echo $((n+1)) > "$idx_file"
printf '%s\\n' "$@" > "${FAKE_ARGS_FILE:-/tmp/fake-args.txt}"
cat "$fx"
cat "${FAKE_STDERR:-/dev/null}" >&2
exit "${FAKE_EXIT:-0}"
"""


def scenario(name, fixtures, request, exit_code=0, state_session=None, history=None, expect_status="completed"):
    tmp = Path(tempfile.mkdtemp(prefix="hgpkg-"))
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    (tmp / "ws").mkdir()
    (tmp / "state").mkdir()
    (tmp / "home").mkdir()
    (tmp / "files").mkdir()
    fake = bin_dir / "claude"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    args_file = tmp / "fake-args.txt"
    idx_file = tmp / "fake-idx.txt"
    env = dict(os.environ)
    env.update({
        "HG_REQUEST": str(tmp / "request.json"),
        "HG_MODEL": "deepseek-v4-pro",
        "HG_PROVIDER_URL": "http://hg-door:8080",
        "HG_PROVIDER_TOKEN": "test-token",
        "HG_PROVIDER_API": "anthropic",
        "HG_WORKSPACE": str(tmp / "ws"),
        "HG_STATE": str(tmp / "state"),
        "HG_HISTORY": str(tmp / "history.json"),
        "HG_FILES": str(tmp / "files"),
        "HG_MCP": str(tmp / "mcp.json"),
        "HG_TOOLS": str(tmp),
        "HG_PACKAGE_VERSION": "2.1.318-1",
        "HG_SESSION": "sess_" + name,
        "HG_RESPONSE": "resp_" + name,
        "HG_TURN": "1",
        "HOME": str(tmp / "home"),
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "FAKE_FIXTURES": ":".join(str(FIX / f) for f in fixtures),
        "FAKE_EXIT": str(exit_code),
        "FAKE_ARGS_FILE": str(args_file),
        "FAKE_IDX_FILE": str(idx_file),
    })
    (tmp / "request.json").write_text(json.dumps(request))
    if state_session is not None:
        (tmp / "state" / "session").write_text(state_session)
    if history is not None:
        (tmp / "history.json").write_text(json.dumps(history))
    proc = subprocess.run([str(RUN)], env=env, capture_output=True, text=True, timeout=120)
    return proc, args_file, tmp


def main():
    cases = [
        ("text", ["claude-text.jsonl"], {"input": "Reply with exactly: pong"}, 0, None, None, "completed"),
        ("tools", ["claude-tools.jsonl"], {"input": "create hello.txt then cat it"}, 0, None, None, "completed"),
        ("error", ["claude-error.jsonl"], {"input": "hi"}, 1, None, None, "failed"),
        ("killed", ["claude-killed.jsonl"], {"input": "slow command"}, 143, None, None, "failed"),
        ("resume", ["claude-text.jsonl"], {"input": "what did we do?"}, 0, "abc-123", None, "completed"),
        ("history", ["claude-text.jsonl"], {"input": "what did we do?"}, 0, None,
         [{"id": "r1", "status": "completed", "input": [{"type": "message", "role": "user",
                                                        "content": "make a file pear.txt"}],
           "output": [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": "made pear.txt"}]}]}], "completed"),
        ("stale-resume", ["claude-session-missing.jsonl", "claude-text.jsonl"], {"input": "what did we do?"}, 1,
         "00000000-0000-0000-0000-000000000000",
         [{"id": "r1", "status": "completed", "input": [{"type": "message", "role": "user",
                                                        "content": "make a file pear.txt"}],
           "output": [{"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": "made pear.txt"}]}]}], "completed"),
    ]
    failures = 0
    for name, fixtures, request, exit_code, state_session, history, status in cases:
        proc, args_file, tmp = scenario(name, fixtures, request, exit_code, state_session, history, status)
        try:
            events, outcome = check(proc.stdout)
        except Exception as e:  # hgkit.OutputError
            print(f"FAIL {name}: hgkit.check raised {e}")
            failures += 1
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        ok = outcome.status == status
        args = args_file.read_text().strip() if args_file.exists() else ""
        if name == "resume" and not ("--resume" in args and "abc-123" in args):
            ok = False
            print(f"FAIL {name}: expected --resume abc-123 in argv, got: {args[:200]}")
        if name == "history" and "--resume" in args:
            ok = False
            print(f"FAIL {name}: expected a fresh session (no --resume), got: {args[:200]}")
        if name == "history" and "[Earlier in this conversation]" not in args:
            ok = False
            print(f"FAIL {name}: expected history text in the prompt")
        if name == "stale-resume" and "[Earlier in this conversation]" not in args:
            ok = False
            print(f"FAIL {name}: expected fallback to history after the stale resume")
        if not ok:
            print(f"FAIL {name}: status={outcome.status} (wanted {status})")
            failures += 1
        else:
            print(f"ok   {name}: {outcome.status} ({len(events)} events)")
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(cases) - failures}/{len(cases)} scenarios passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
